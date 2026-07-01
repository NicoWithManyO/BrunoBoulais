import logging
import uuid

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.mail import EmailMessage
from django.db import models
from django.db.models import Case, IntegerField, Value, When

from apps.core.fields import RichTextField
from apps.core.models import TimestampedModel
from apps.core.uploads import boutique_upload_to
from apps.core.validators import IMAGE_VALIDATORS

logger = logging.getLogger(__name__)

CACHE_KEY_BOUTIQUE_PAGE = "boutique_page"

# Volumes de l'intégrale rattachables à un produit : si renseigné, la fiche
# affiche la modale « voir le contenu » depuis VOLUMES_CONTENU (integrale.py).
VOLUME_CHOICES = [(1, "Volume 1"), (2, "Volume 2"), (3, "Volume 3")]


class Produit(TimestampedModel):
    """Article vendu dans la boutique. Édité depuis /gestion/, illustré par Bruno."""

    nom = models.CharField("Nom", max_length=200)
    slug = models.SlugField("Slug", max_length=210, unique=True)
    reference = models.CharField("Référence", max_length=50, blank=True)
    prix_cents = models.PositiveIntegerField("Prix (centimes)")
    description = RichTextField("Description", blank=True)
    illustration = models.ImageField(
        "Illustration",
        upload_to=boutique_upload_to,
        validators=IMAGE_VALIDATORS,
        blank=True,
    )
    volume_integrale = models.PositiveSmallIntegerField(
        "Volume de l'intégrale", choices=VOLUME_CHOICES, null=True, blank=True,
        help_text="Si renseigné, la fiche affiche le contenu du volume.",
    )
    dedicacable = models.BooleanField("Dédicaçable", default=False)
    position = models.PositiveIntegerField("Position", default=0)
    publie = models.BooleanField("Publié", default=True)

    class Meta:
        # Position > 0 prime (ordre manuel ascendant) ; position = 0 (défaut) =
        # « pas d'ordre choisi » → relégué derrière, plus récent d'abord.
        ordering = [
            Case(
                When(position=0, then=Value(1)),
                default=Value(0),
                output_field=IntegerField(),
            ),
            "position",
            "-created_at",
        ]
        verbose_name = "Produit"
        verbose_name_plural = "Produits"

    def __str__(self):
        return self.nom

    @property
    def prix_euros(self):
        """Prix formaté FR pour l'affichage : 2000 → "20,00 €"."""
        return f"{self.prix_cents / 100:.2f}".replace(".", ",") + " €"


class BoutiquePage(TimestampedModel):
    """Singleton holding the editable header of the public /boutique/ page."""

    eyebrow = models.CharField("Surtitre", max_length=80, blank=True)
    titre = models.CharField("Titre", max_length=120, blank=True)
    intro = RichTextField("Texte d'introduction", blank=True)

    class Meta:
        verbose_name = "En-tête /boutique/"
        verbose_name_plural = "En-tête /boutique/"

    def __str__(self):
        return "En-tête /boutique/"

    def clean(self):
        if not self.pk and BoutiquePage.objects.exists():
            raise ValidationError("Un seul en-tête peut exister (singleton).")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
        cache.delete(CACHE_KEY_BOUTIQUE_PAGE)

    @classmethod
    def get_solo(cls):
        obj = cache.get(CACHE_KEY_BOUTIQUE_PAGE)
        if obj is None:
            obj, _ = cls.objects.get_or_create(pk=1)
            cache.set(CACHE_KEY_BOUTIQUE_PAGE, obj, 300)
        return obj


class Commande(TimestampedModel):
    """Une commande passée depuis le chapeau (panier). Persistée au checkout."""

    LIVRAISON_POINT_RELAIS = "point_relais"
    LIVRAISON_DOMICILE = "domicile"
    LIVRAISON_CHOICES = [
        (LIVRAISON_POINT_RELAIS, "Point Relais ou Locker"),
        (LIVRAISON_DOMICILE, "Domicile"),
    ]

    PAIEMENT_CB = "cb"
    PAIEMENT_CHEQUE = "cheque"
    PAIEMENT_VIREMENT = "virement"
    PAIEMENT_CHOICES = [
        (PAIEMENT_CB, "Carte bancaire"),
        (PAIEMENT_CHEQUE, "Chèque"),
        (PAIEMENT_VIREMENT, "Virement"),
    ]

    STATUT_EN_ATTENTE_PAIEMENT = "en_attente_paiement"
    STATUT_EN_ATTENTE_REGLEMENT = "en_attente_reglement"
    STATUT_PAYE = "paye"
    STATUT_ANNULE = "annule"
    STATUT_CHOICES = [
        (STATUT_EN_ATTENTE_PAIEMENT, "En attente de paiement (CB lancée)"),
        (STATUT_EN_ATTENTE_REGLEMENT, "En attente de règlement (chèque/virement)"),
        (STATUT_PAYE, "Payé"),
        (STATUT_ANNULE, "Annulé"),
    ]

    reference_commande = models.CharField(
        "Référence", max_length=12, unique=True, editable=False
    )
    # Coordonnées client (sémantique reprise de contact.Message).
    nom = models.CharField("Nom", max_length=120)
    email = models.EmailField("Email")
    telephone = models.CharField("Téléphone", max_length=30, blank=True)
    adresse_postale = models.TextField("Adresse postale", blank=True)
    # Livraison.
    mode_livraison = models.CharField(
        "Mode de livraison", max_length=20, choices=LIVRAISON_CHOICES, blank=True
    )
    point_relais_id = models.CharField("ID point relais", max_length=20, blank=True)
    point_relais_libelle = models.CharField("Point relais choisi", max_length=255, blank=True)
    # Dédicace au niveau commande (un seul prénom pour la commande).
    dedicace = models.BooleanField("Dédicace souhaitée", default=False)
    prenom_dedicace = models.CharField("Prénom pour la dédicace", max_length=100, blank=True)
    # Paiement & montants figés à la commande (indépendants des prix futurs).
    mode_paiement = models.CharField("Mode de paiement", max_length=20, choices=PAIEMENT_CHOICES)
    montant_articles_cents = models.PositiveIntegerField("Articles (centimes)", default=0)
    frais_port_cents = models.PositiveIntegerField("Frais de port (centimes)", default=0)
    montant_total_cents = models.PositiveIntegerField("Total (centimes)", default=0)
    statut = models.CharField("Statut", max_length=30, choices=STATUT_CHOICES)
    stripe_session_id = models.CharField("Session Stripe", max_length=255, blank=True)
    # Suivi back-office (pattern repris de Message).
    notified = models.BooleanField("Notifié", default=True)
    lu = models.BooleanField("Lu", default=False)
    archive = models.BooleanField("Archivé", default=False)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Commande"
        verbose_name_plural = "Commandes"

    def __str__(self):
        return f"Commande {self.reference_commande} — {self.nom}"

    def save(self, *args, **kwargs):
        if not self.reference_commande:
            self.reference_commande = uuid.uuid4().hex[:8].upper()
        super().save(*args, **kwargs)

    @property
    def paye(self):
        return self.statut == self.STATUT_PAYE

    def notify(self):
        """Envoie le récapitulatif de la commande à Bruno (lui seul).

        Sur tout échec (construction du récap ou envoi), on persiste
        ``notified=False`` pour que la commande remonte « à traiter » en gestion :
        la commande est déjà enregistrée (source de vérité), on n'échoue jamais
        la requête pour un mail. C'est vital côté webhook Stripe : lever ici
        remonterait en 500, le rejeu verrait la commande déjà « payée » et
        n'aurait plus rien à notifier — Bruno resterait sans nouvelle.
        """
        # Import différé : pricing importe Commande (montant_euros vit là-bas).
        from .pricing import montant_euros

        try:
            lines = [
                f"Réf. commande : {self.reference_commande}",
                f"De : {self.nom} <{self.email}>",
                f"Téléphone : {self.telephone or '—'}",
                f"Adresse : {self.adresse_postale or '—'}",
                "",
                "Articles :",
            ]
            for ligne in self.lignes.all():
                lines.append(
                    f"  {ligne.quantite} × {ligne.libelle} — {montant_euros(ligne.sous_total_cents)}"
                )
            lines += [
                "",
                f"Sous-total articles : {montant_euros(self.montant_articles_cents)}",
                f"Frais de port ({self.get_mode_livraison_display() or '—'}) : "
                f"{montant_euros(self.frais_port_cents)}",
                f"Montant total : {montant_euros(self.montant_total_cents)}",
                f"Paiement : {self.get_mode_paiement_display()}",
                f"État : {self.get_statut_display()}",
            ]
            if self.mode_livraison == self.LIVRAISON_DOMICILE:
                lines.append(f"Livraison : Domicile — {self.adresse_postale or '—'}")
            elif self.mode_livraison:
                point = self.point_relais_libelle or "(non précisé)"
                lines.append(
                    f"Livraison : {self.get_mode_livraison_display()} — "
                    f"{point} (ID {self.point_relais_id or '—'})"
                )
            if self.dedicace:
                prenom = f" (prénom : {self.prenom_dedicace})" if self.prenom_dedicace else ""
                lines.append(f"Dédicace : oui{prenom}")
            else:
                lines.append("Dédicace : non")
            email = EmailMessage(
                subject=f"[jacques-bertin.manyo.dev] Commande {self.reference_commande} — {self.nom}",
                body="\n".join(lines) + "\n",
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[settings.CONTACT_EMAIL],
                reply_to=[self.email],
            )
            email.send(fail_silently=False)
        except Exception:
            self.notified = False
            self.save(update_fields=["notified"])
            logger.error(
                "Boutique: commande %s de %s <%s> enregistrée mais notification "
                "non envoyée — à traiter manuellement.",
                self.reference_commande,
                self.nom,
                self.email,
                exc_info=True,
            )


class LigneCommande(TimestampedModel):
    """Un article d'une commande, avec snapshot du nom et du prix au moment de l'achat."""

    commande = models.ForeignKey(Commande, on_delete=models.CASCADE, related_name="lignes")
    # SET_NULL : Bruno peut supprimer un produit de son catalogue sans casser
    # l'historique — le snapshot (libelle + prix_unitaire) garde la ligne lisible.
    produit = models.ForeignKey(Produit, on_delete=models.SET_NULL, null=True, blank=True)
    libelle = models.CharField("Libellé", max_length=200)
    prix_unitaire_cents = models.PositiveIntegerField("Prix unitaire (centimes)")
    quantite = models.PositiveSmallIntegerField("Quantité")

    class Meta:
        verbose_name = "Ligne de commande"
        verbose_name_plural = "Lignes de commande"

    def __str__(self):
        return f"{self.quantite} × {self.libelle}"

    @property
    def sous_total_cents(self):
        return self.prix_unitaire_cents * self.quantite
