import ipaddress
import logging
import math

import stripe
from django.conf import settings
from django.core.cache import cache
from django.core.mail import send_mail
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django_ratelimit.core import get_usage

from apps.core.middleware import _client_ip
from apps.core.seo import seo

from .forms import CommandeForm, ContactForm
from .models import PRODUITS, ContactPage, Message, montant_euros

logger = logging.getLogger(__name__)

# Rate-limit : 5 POST/heure par bucket IP.
# Implémentation : cache LocMem par défaut (per-worker). Pour que la limite
# soit respectée, gunicorn doit tourner avec UN seul worker. Sinon le cap
# effectif devient 5/h × N workers. Switch vers Redis si on a besoin de scaler.


def _ratelimit_bucket(request):
    """Bucket de rate-limit : IP client masquée /32 (IPv4) ou /64 (IPv6).

    IPv6 est masqué à /64 pour empêcher la rotation des bits bas
    (un /64 résidentiel donne 2^64 adresses sinon). IPv4-mapped IPv6
    a déjà été normalisé en IPv4 par ``_client_ip`` (sinon le mask /64
    sur ``::ffff:x.x.x.x`` retombe sur ``::`` et tous les attaquants
    partagent un bucket unique).

    Retourne ``None`` si l'IP est absente — le caller doit fail closed
    dans ce cas. La string retournée par ``_client_ip`` est garantie
    canoniquement parseable (cf docstring), donc pas de try/except ici.
    """
    ip_str = _client_ip(request)
    if not ip_str:
        return None
    ip = ipaddress.ip_address(ip_str)
    mask = 32 if isinstance(ip, ipaddress.IPv4Address) else 64
    return str(ipaddress.ip_network(f"{ip}/{mask}", strict=False).network_address)


def _bucket_usage(request, bucket, *, increment):
    """Wrapper get_usage avec config view-spécifique (5/h, group).

    ``increment=False`` lit le compteur sans bump (gating pré-save).
    ``increment=True`` bump (post-save success, ou honeypot trip).

    Retourne le dict {count, limit, should_limit, time_left} ou ``None``
    si le rate-limit est désactivé / non applicable. Le caller compare
    ``count >= limit`` (NB : ``should_limit = count > limit`` côté
    django-ratelimit, donc pas utilisable avec le pattern check-then-bump
    sans off-by-one).
    """
    return get_usage(
        request=request,
        group="contact:contact",
        key=lambda g, r: bucket,
        rate="5/h",
        method="POST",
        increment=increment,
    )


def _log_ip_unresolved_dedup(request):
    """Log warning IP indéterminée, dédupliqué 5 min via cache.

    Sans dédup, chaque POST sur ce path part en Sentry/PagerDuty : un
    attaquant qui force REMOTE_ADDR vide peut spam la pile d'alerting.
    Clé courte (pas par path) car on a une seule vue concernée.
    """
    # Clé namespacée par module pour éviter une collision si un autre helper
    # (tests, autre vue) réutilise le préfixe "contact:" dans le futur.
    log_key = "apps.contact.views:ip-unresolved-logged"
    if cache.add(log_key, True, 300):
        # %r (repr) échappe CR/LF dans request.path — Django décode les
        # %-encoded chars de l'URL, donc %0A devient un newline littéral
        # qui injecterait une fausse ligne dans la sortie console/SIEM.
        logger.warning(
            "Contact: IP client indéterminée, POST bloqué (path=%r)",
            request.path,
        )


def contact(request):
    rate_limited = False
    ip_unresolved = False
    retry_after = None
    if request.method == "POST":
        form = ContactForm(request.POST)
        # Honeypot trip = bot. On burn le bucket (pénaliser) puis on
        # redirect /merci/ pour ne pas révéler qu'on a détecté le piège
        # (anti-fingerprint). Check sur request.POST brut pour éviter de
        # déclencher form.full_clean() avant la décision.
        if (request.POST.get("website") or "").strip():
            bucket = _ratelimit_bucket(request)
            if bucket is None:
                # Même path forensique que la branche fail-closed : un bot
                # qui combine honeypot trip + IP strippée doit laisser une
                # trace (dédupliquée), sinon il passe sous radar.
                _log_ip_unresolved_dedup(request)
            else:
                _bucket_usage(request, bucket, increment=True)
            return redirect(reverse("contact:merci"))
        # Vraie validation : champs requis, cohérence commande, etc. Le
        # quota n'est PAS consommé sur erreur de validation (typo user)
        # ni sur fail save (DB/email transitoire) — uniquement sur
        # succès complet (bump après save_and_notify).
        if form.is_valid():
            bucket = _ratelimit_bucket(request)
            if bucket is None:
                # Fail closed : on ne peut pas bucket-er, on bloque. Pas de
                # Retry-After (attendre ne résout pas une IP absente) et
                # 503 plutôt que 429 (ce n'est pas une rate limit, c'est
                # une indisponibilité).
                _log_ip_unresolved_dedup(request)
                ip_unresolved = True
            else:
                usage = _bucket_usage(request, bucket, increment=False)
                if usage is not None and usage["count"] >= usage["limit"]:
                    rate_limited = True
                    # max(1, ceil(...)) borne Retry-After à ≥ 1s :
                    # - boundary (time_left=0, requête pile au tick de reset)
                    #   sans floor donne "Retry-After: 0" = retry immédiat ;
                    # - sentinel cache-fail de django-ratelimit (time_left=-1
                    #   quand count=0/limit=0/should_limit=True) donnerait un
                    #   Retry-After négatif, invalide RFC 7231.
                    retry_after = max(1, math.ceil(usage["time_left"]))
                else:
                    msg = form.save_and_notify()
                    _bucket_usage(request, bucket, increment=True)
                    # Le paiement se règle à l'étape suivante (/merci/) : on
                    # transmet le mode choisi via la session pour afficher la
                    # bonne consigne (boutons Stripe pour CB, etc.).
                    if msg.sujet == Message.SUJET_COMMANDE and msg.mode_paiement:
                        request.session["order_paiement"] = {
                            "mode": msg.mode_paiement,
                            "ref": msg.pk,
                        }
                    else:
                        request.session.pop("order_paiement", None)
                    return redirect(reverse("contact:merci"))
    else:
        form = ContactForm()
    response = render(
        request,
        "contact/form.html",
        {
            "form": form,
            "page": ContactPage.get_solo(),
            "commande_value": Message.SUJET_COMMANDE,
            "paiement_cb": Message.PAIEMENT_CB,
            "paiement_cheque": Message.PAIEMENT_CHEQUE,
            "paiement_virement": Message.PAIEMENT_VIREMENT,
            "rate_limited": rate_limited,
            "ip_unresolved": ip_unresolved,
            **seo(
                request,
                title="Contact & commande dédicacée · Bruno Boulais",
                description=(
                    "Commander le livre avec une dédicace personnalisée ou écrire"
                    " à Bruno Boulais."
                ),
            ),
        },
    )
    # Priorité ip_unresolved > rate_limited : fail-closed (503) prime sur
    # rate-limit (429) si un refactor futur rend les deux flags True en
    # même temps. Aujourd'hui ils s'excluent par control flow, mais on
    # cadre la priorité pour ne pas dépendre de cet invariant implicite.
    if ip_unresolved:
        # 503 sans Retry-After (attendre ne résout pas l'IP absente) + no-store
        # pour empêcher Cloudflare/CDN de cacher l'erreur au edge (RFC 7234 :
        # 503 est cacheable par heuristique sans Cache-Control explicite).
        response.status_code = 503
        response["Cache-Control"] = "no-store"
    elif rate_limited:
        # HTTP 429 + Retry-After : non cacheable par les CDN, et bots/scripts
        # voient l'erreur explicitement (au lieu d'un 200 qui ressemble à un
        # succès et déclenche un re-submit qui ré-incrémente).
        response.status_code = 429
        response["Retry-After"] = str(retry_after)
        response["Cache-Control"] = "no-store"
    return response


def merci(request):
    # Consommé à l'affichage : la consigne de paiement ne s'affiche qu'une fois,
    # pour ne pas reproposer de payer une commande déjà réglée (les liens Stripe
    # statiques rechargeraient un paiement). Un rechargement de /merci/ retombe
    # donc sur le simple remerciement.
    order_paiement = request.session.pop("order_paiement", None)
    return render(
        request,
        "contact/merci.html",
        {
            "page": ContactPage.get_solo(),
            "order_paiement": order_paiement,
            "paiement_cb": Message.PAIEMENT_CB,
            "paiement_cheque": Message.PAIEMENT_CHEQUE,
            "paiement_virement": Message.PAIEMENT_VIREMENT,
            **seo(request, title="Message envoyé · Bruno Boulais"),
        },
    )


# --- Nouvelle page de commande (page de travail /contact/v2/, swap à venir) ---
# Réutilise les helpers de rate-limit ci-dessus. La similarité d'orchestration
# avec `contact` est temporaire : l'ancienne page disparaît au swap.


def commande(request):
    rate_limited = False
    ip_unresolved = False
    retry_after = None
    if request.method == "POST":
        form = CommandeForm(request.POST)
        if (request.POST.get("website") or "").strip():
            bucket = _ratelimit_bucket(request)
            if bucket is None:
                _log_ip_unresolved_dedup(request)
            else:
                _bucket_usage(request, bucket, increment=True)
            return redirect(reverse("contact:commande_merci"))
        if form.is_valid():
            bucket = _ratelimit_bucket(request)
            if bucket is None:
                _log_ip_unresolved_dedup(request)
                ip_unresolved = True
            else:
                usage = _bucket_usage(request, bucket, increment=False)
                if usage is not None and usage["count"] >= usage["limit"]:
                    rate_limited = True
                    retry_after = max(1, math.ceil(usage["time_left"]))
                else:
                    msg = form.save_and_notify()
                    _bucket_usage(request, bucket, increment=True)
                    # On ne garde que la référence : mode et quantité se relisent
                    # depuis le Message (pas de duplication en session).
                    if msg.sujet == Message.SUJET_COMMANDE and msg.mode_paiement:
                        request.session["order_ref"] = msg.pk
                    else:
                        request.session.pop("order_ref", None)
                    return redirect(reverse("contact:commande_merci"))
    else:
        form = CommandeForm()
    response = render(
        request,
        "contact/commande.html",
        {
            "form": form,
            "page": ContactPage.get_solo(),
            "commande_value": Message.SUJET_COMMANDE,
            "paiement_cb": Message.PAIEMENT_CB,
            "paiement_cheque": Message.PAIEMENT_CHEQUE,
            "paiement_virement": Message.PAIEMENT_VIREMENT,
            "rate_limited": rate_limited,
            "ip_unresolved": ip_unresolved,
            **seo(
                request,
                title="Contact & commande dédicacée · Bruno Boulais",
                description=(
                    "Commander le livre avec une dédicace personnalisée ou écrire"
                    " à Bruno Boulais."
                ),
            ),
        },
    )
    if ip_unresolved:
        response.status_code = 503
        response["Cache-Control"] = "no-store"
    elif rate_limited:
        response.status_code = 429
        response["Retry-After"] = str(retry_after)
        response["Cache-Control"] = "no-store"
    return response


def commande_merci(request):
    # On garde `order_ref` en session tant que la commande n'est pas réglée :
    # le client doit pouvoir relancer un paiement annulé. On le purge dès que
    # la commande est payée (ou au retour « succès » de Stripe).
    ref = request.session.get("order_ref")
    order = Message.objects.filter(pk=ref).first() if ref else None
    paiement = request.GET.get("paiement")  # succes | annule | erreur

    if order and (order.paye or paiement == "succes"):
        request.session.pop("order_ref", None)

    produit = PRODUITS.get(order.nb_exemplaires) if order else None
    return render(
        request,
        "contact/commande_merci.html",
        {
            "page": ContactPage.get_solo(),
            "order": order,
            "montant": montant_euros(produit["montant_cents"]) if produit else "",
            "paiement": paiement,
            "paiement_cb": Message.PAIEMENT_CB,
            "paiement_cheque": Message.PAIEMENT_CHEQUE,
            "paiement_virement": Message.PAIEMENT_VIREMENT,
            **seo(request, title="Message envoyé · Bruno Boulais"),
        },
    )


@require_POST
def paiement_checkout(request):
    """Crée une Checkout Session Stripe pour la commande CB en cours de session."""
    ref = request.session.get("order_ref")
    order = Message.objects.filter(pk=ref).first() if ref else None
    # Garde : commande CB non encore payée. Sinon, rien à payer → retour /merci/.
    if not order or order.mode_paiement != Message.PAIEMENT_CB or order.paye:
        return redirect(reverse("contact:commande_merci"))

    produit = PRODUITS.get(order.nb_exemplaires)
    merci_url = request.build_absolute_uri(reverse("contact:commande_merci"))
    if produit is None:
        # Quantité absente/incohérente (donnée legacy, admin) : pas de montant
        # à facturer, on ne lance pas Stripe et on retourne proprement.
        logger.error(
            "Stripe: commande #%s sans quantité valide (nb_exemplaires=%r).",
            order.pk,
            order.nb_exemplaires,
        )
        return redirect(f"{merci_url}?paiement=erreur")
    stripe.api_key = settings.STRIPE_SECRET_KEY
    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            line_items=[
                {
                    "price_data": {
                        "currency": "eur",
                        "product_data": {"name": produit["label"]},
                        "unit_amount": produit["montant_cents"],
                    },
                    "quantity": 1,
                }
            ],
            customer_email=order.email,
            client_reference_id=str(order.pk),
            success_url=f"{merci_url}?paiement=succes",
            cancel_url=f"{merci_url}?paiement=annule",
        )
    except stripe.error.StripeError:
        logger.error(
            "Stripe: échec de création de la Checkout Session pour la commande #%s.",
            order.pk,
            exc_info=True,
        )
        return redirect(f"{merci_url}?paiement=erreur")

    order.stripe_session_id = session.id
    order.save(update_fields=["stripe_session_id"])
    return redirect(session.url)


@csrf_exempt
@require_POST
def paiement_webhook(request):
    """Webhook Stripe : confirme le paiement d'une commande (checkout.session.completed)."""
    try:
        event = stripe.Webhook.construct_event(
            request.body,
            request.META.get("HTTP_STRIPE_SIGNATURE", ""),
            settings.STRIPE_WEBHOOK_SECRET,
        )
    except (ValueError, stripe.error.SignatureVerificationError):
        return HttpResponse(status=400)

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        # On ne marque payé que si le paiement est réellement abouti : pour une
        # méthode asynchrone, `completed` peut arriver avec payment_status != paid.
        if session.get("payment_status") != "paid":
            return HttpResponse(status=200)
        ref = session.get("client_reference_id")
        # filter(paye=False) = idempotent : un re-delivery Stripe ne renotifie pas.
        updated = Message.objects.filter(pk=ref, paye=False).update(paye=True)
        if updated:
            send_mail(
                subject=f"[jacques-bertin.manyo.dev] Paiement reçu — commande #{ref}",
                message=f"Le paiement par carte de la commande #{ref} a bien été reçu.\n",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[settings.CONTACT_EMAIL],
                fail_silently=True,
            )
    return HttpResponse(status=200)
