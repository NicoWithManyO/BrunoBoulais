from unittest import mock

import pytest
import stripe
from django.core.cache import cache
from django.test import Client

from apps.contact import forms as contact_forms
from apps.contact.forms import CommandeForm, ContactForm
from apps.contact.models import Message

forms_logger = contact_forms.logger


@pytest.fixture(autouse=True)
def clear_cache():
    # Le rate-limit et le dédup log s'appuient sur LocMemCache global :
    # nettoyer avant/après pour ne pas polluer un autre test.
    cache.clear()
    yield
    cache.clear()


@pytest.fixture(autouse=True)
def disable_manifest_storage(settings):
    # Le rendu du template de /contact/ appelle `static(...)` côté context
    # processor, ce qui exige un `manifest.json` produit par `collectstatic` —
    # pas voulu en suite de tests.
    settings.STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }


@pytest.mark.django_db
class TestContactIpUnresolved:
    """Régression check sur le fail-closed introduit par f2ccab8.

    Quand `_client_ip` retourne "" (IP indéterminée), la vue doit retourner
    503 + Cache-Control: no-store — pas 200, pas 302, pas un succès silencieux
    qui aurait permis à l'attaquant de bypasser le rate-limit par IP.
    """

    def test_post_with_unresolved_ip_returns_503(self):
        client = Client()
        response = client.post(
            "/contact/",
            data={
                "nom": "Alice",
                "sujet": "question",
                "email": "alice@example.com",
                "telephone": "",
                "adresse_postale": "",
                "contenu": "Bonjour Bruno, juste une question.",
                "website": "",
            },
            REMOTE_ADDR="",
        )
        assert response.status_code == 503
        assert response["Cache-Control"] == "no-store"


@pytest.mark.django_db
class TestContactPaiementValidation:
    """Le mode de paiement est requis uniquement pour une commande dédicacée."""

    def _data(self, **overrides):
        data = {
            "nom": "Alice",
            "sujet": Message.SUJET_COMMANDE,
            "email": "alice@example.com",
            "telephone": "0612345678",
            "adresse_postale": "1 rue du Livre, 40000 Mont-de-Marsan",
            "mode_paiement": Message.PAIEMENT_CB,
            "contenu": "Je commande un exemplaire dédicacé.",
            "website": "",
        }
        data.update(overrides)
        return data

    def test_commande_requires_mode_paiement(self):
        form = ContactForm(data=self._data(mode_paiement=""))
        assert not form.is_valid()
        assert "mode_paiement" in form.errors

    def test_commande_with_mode_paiement_is_valid(self):
        form = ContactForm(data=self._data())
        assert form.is_valid(), form.errors

    def test_mode_paiement_optional_for_non_commande(self):
        form = ContactForm(
            data=self._data(
                sujet=Message.SUJET_QUESTION,
                mode_paiement="",
                telephone="",
                adresse_postale="",
            )
        )
        assert form.is_valid(), form.errors


@pytest.mark.django_db
class TestContactPaiementFlow:
    """La commande est capturée d'abord, le paiement vient ensuite sur /merci/.

    Régression check sur la refonte : un POST commande valide enregistre le
    Message et redirige vers /merci/ en passant le mode de paiement en session
    (pas de paiement déclenché depuis le formulaire).
    """

    def _data(self, **overrides):
        data = {
            "nom": "Alice",
            "sujet": Message.SUJET_COMMANDE,
            "email": "alice@example.com",
            "telephone": "0612345678",
            "adresse_postale": "1 rue du Livre, 40000 Mont-de-Marsan",
            "mode_paiement": Message.PAIEMENT_CB,
            "contenu": "Je commande un exemplaire dédicacé.",
            "website": "",
        }
        data.update(overrides)
        return data

    def test_commande_saves_then_redirects_with_session(self):
        client = Client()
        response = client.post("/contact/", data=self._data(), REMOTE_ADDR="1.2.3.4")
        assert response.status_code == 302
        assert response["Location"] == "/contact/merci/"
        assert Message.objects.count() == 1
        assert client.session["order_paiement"]["mode"] == Message.PAIEMENT_CB

    def test_non_commande_clears_payment_session(self):
        client = Client()
        # Une session contenant un ancien paiement ne doit pas survivre à un
        # message non-commande.
        session = client.session
        session["order_paiement"] = {"mode": Message.PAIEMENT_CB, "ref": 1}
        session.save()
        response = client.post(
            "/contact/",
            data=self._data(
                sujet=Message.SUJET_QUESTION,
                mode_paiement="",
                telephone="",
                adresse_postale="",
            ),
            REMOTE_ADDR="1.2.3.4",
        )
        assert response.status_code == 302
        assert "order_paiement" not in client.session

    def test_merci_renders_stripe_buttons_for_cb(self):
        client = Client()
        session = client.session
        session["order_paiement"] = {"mode": Message.PAIEMENT_CB, "ref": 42}
        session.save()
        response = client.get("/contact/merci/")
        assert response.status_code == 200
        assert b"buy.stripe.com" in response.content
        # Consommé à l'affichage : un rechargement ne repropose plus de payer.
        reload = client.get("/contact/merci/")
        assert b"buy.stripe.com" not in reload.content

    def test_merci_without_session_has_no_stripe(self):
        client = Client()
        response = client.get("/contact/merci/")
        assert response.status_code == 200
        assert b"buy.stripe.com" not in response.content


@pytest.mark.django_db
class TestContactNotificationHardening:
    """Finding 9 : un échec d'envoi du mail ne doit pas perdre la commande."""

    def test_save_succeeds_and_logs_when_email_fails(self):
        form = ContactForm(
            data={
                "nom": "Alice",
                "sujet": Message.SUJET_COMMANDE,
                "email": "alice@example.com",
                "telephone": "0612345678",
                "adresse_postale": "1 rue du Livre, 40000 Mont-de-Marsan",
                "mode_paiement": Message.PAIEMENT_CB,
                "contenu": "Je commande un exemplaire dédicacé.",
                "website": "",
            }
        )
        assert form.is_valid(), form.errors
        with mock.patch(
            "apps.contact.forms.EmailMessage.send", side_effect=Exception("smtp down")
        ) as send, mock.patch.object(forms_logger, "error") as log_error:
            msg = form.save_and_notify()
        # La commande est sauvegardée malgré l'échec d'envoi, l'échec est signalé.
        assert send.called
        assert msg.pk is not None
        # notified=False est persisté (visible/filtrable dans l'admin).
        assert Message.objects.get(pk=msg.pk).notified is False
        assert log_error.called

    def test_notified_true_when_email_succeeds(self):
        form = ContactForm(
            data={
                "nom": "Alice",
                "sujet": Message.SUJET_COMMANDE,
                "email": "alice@example.com",
                "telephone": "0612345678",
                "adresse_postale": "1 rue du Livre, 40000 Mont-de-Marsan",
                "mode_paiement": Message.PAIEMENT_CB,
                "contenu": "Je commande un exemplaire dédicacé.",
                "website": "",
            }
        )
        assert form.is_valid(), form.errors
        with mock.patch("apps.contact.forms.EmailMessage.send"):
            msg = form.save_and_notify()
        assert Message.objects.get(pk=msg.pk).notified is True


def _commande_data(**overrides):
    data = {
        "nom": "Alice",
        "sujet": Message.SUJET_COMMANDE,
        "email": "alice@example.com",
        "telephone": "0612345678",
        "adresse_postale": "1 rue du Livre, 40000 Mont-de-Marsan",
        "mode_paiement": Message.PAIEMENT_CB,
        "nb_exemplaires": 1,
        "contenu": "Je commande un exemplaire dédicacé.",
        "website": "",
    }
    data.update(overrides)
    return data


@pytest.mark.django_db
class TestCommandeForm:
    """Le nombre d'exemplaires est requis pour une commande (nouveau champ)."""

    def test_commande_requires_nb_exemplaires(self):
        form = CommandeForm(data=_commande_data(nb_exemplaires=""))
        assert not form.is_valid()
        assert "nb_exemplaires" in form.errors

    def test_commande_with_nb_exemplaires_is_valid(self):
        form = CommandeForm(data=_commande_data())
        assert form.is_valid(), form.errors


@pytest.mark.django_db
class TestCommandeFlow:
    """Page de travail /contact/v2/ : la commande est capturée puis le paiement suit."""

    def test_commande_saves_then_redirects_with_session(self):
        client = Client()
        with mock.patch("apps.contact.forms.EmailMessage.send"):
            response = client.post("/contact/v2/", data=_commande_data(), REMOTE_ADDR="1.2.3.4")
        assert response.status_code == 302
        assert response["Location"] == "/contact/v2/merci/"
        assert Message.objects.count() == 1
        assert client.session["order_ref"] == Message.objects.get().pk

    def test_non_commande_clears_session(self):
        client = Client()
        session = client.session
        session["order_ref"] = 1
        session.save()
        with mock.patch("apps.contact.forms.EmailMessage.send"):
            response = client.post(
                "/contact/v2/",
                data=_commande_data(
                    sujet=Message.SUJET_QUESTION,
                    mode_paiement="",
                    nb_exemplaires="",
                    telephone="",
                    adresse_postale="",
                ),
                REMOTE_ADDR="1.2.3.4",
            )
        assert response.status_code == 302
        assert "order_ref" not in client.session


@pytest.mark.django_db
class TestCommandeMerci:
    """La page /merci/ propose le règlement CB tant que la commande n'est pas payée."""

    def _order(self, **overrides):
        defaults = {
            "nom": "Alice",
            "email": "alice@example.com",
            "sujet": Message.SUJET_COMMANDE,
            "mode_paiement": Message.PAIEMENT_CB,
            "nb_exemplaires": 1,
            "contenu": "Commande",
        }
        defaults.update(overrides)
        return Message.objects.create(**defaults)

    def test_cb_unpaid_shows_pay_form(self):
        order = self._order()
        client = Client()
        session = client.session
        session["order_ref"] = order.pk
        session.save()
        response = client.get("/contact/v2/merci/")
        assert response.status_code == 200
        assert b'action="/contact/paiement/"' in response.content
        assert b"buy.stripe.com" not in response.content

    def test_paid_hides_pay_form(self):
        order = self._order(paye=True)
        client = Client()
        session = client.session
        session["order_ref"] = order.pk
        session.save()
        response = client.get("/contact/v2/merci/")
        assert response.status_code == 200
        assert b'action="/contact/paiement/"' not in response.content


@pytest.mark.django_db
class TestPaiementCheckout:
    """Création de la Checkout Session Stripe (lib mickée, aucune clé requise)."""

    def _order(self, **overrides):
        defaults = {
            "nom": "Alice",
            "email": "alice@example.com",
            "sujet": Message.SUJET_COMMANDE,
            "mode_paiement": Message.PAIEMENT_CB,
            "nb_exemplaires": 1,
            "contenu": "Commande",
        }
        defaults.update(overrides)
        return Message.objects.create(**defaults)

    def _client_with_order(self, order):
        client = Client()
        session = client.session
        session["order_ref"] = order.pk
        session.save()
        return client

    def test_creates_session_and_redirects(self):
        order = self._order()
        client = self._client_with_order(order)
        fake = mock.Mock(id="cs_test_123", url="https://checkout.stripe.com/c/pay/cs_test_123")
        with mock.patch(
            "apps.contact.views.stripe.checkout.Session.create", return_value=fake
        ) as create:
            response = client.post("/contact/paiement/")
        assert create.called
        assert response.status_code == 302
        assert response["Location"] == "https://checkout.stripe.com/c/pay/cs_test_123"
        order.refresh_from_db()
        assert order.stripe_session_id == "cs_test_123"

    def test_no_order_in_session_skips_stripe(self):
        client = Client()
        with mock.patch("apps.contact.views.stripe.checkout.Session.create") as create:
            response = client.post("/contact/paiement/")
        assert not create.called
        assert response.status_code == 302
        assert response["Location"] == "/contact/v2/merci/"

    def test_already_paid_skips_stripe(self):
        order = self._order(paye=True)
        client = self._client_with_order(order)
        with mock.patch("apps.contact.views.stripe.checkout.Session.create") as create:
            response = client.post("/contact/paiement/")
        assert not create.called
        assert response.status_code == 302


@pytest.mark.django_db
class TestPaiementWebhook:
    """Webhook Stripe : confirme le paiement, idempotent, rejette une signature invalide."""

    def _order(self, **overrides):
        defaults = {
            "nom": "Alice",
            "email": "alice@example.com",
            "sujet": Message.SUJET_COMMANDE,
            "mode_paiement": Message.PAIEMENT_CB,
            "nb_exemplaires": 1,
            "contenu": "Commande",
        }
        defaults.update(overrides)
        return Message.objects.create(**defaults)

    def _post(self, client):
        return client.post(
            "/contact/paiement/webhook/",
            data="{}",
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="t=1,v1=deadbeef",
        )

    def test_completed_marks_paid_and_notifies(self):
        order = self._order()
        event = {
            "type": "checkout.session.completed",
            "data": {"object": {"client_reference_id": str(order.pk), "payment_status": "paid"}},
        }
        with mock.patch(
            "apps.contact.views.stripe.Webhook.construct_event", return_value=event
        ), mock.patch("apps.contact.views.send_mail") as send:
            response = self._post(Client())
        assert response.status_code == 200
        order.refresh_from_db()
        assert order.paye is True
        assert send.called

    def test_bad_signature_returns_400(self):
        order = self._order()
        with mock.patch(
            "apps.contact.views.stripe.Webhook.construct_event",
            side_effect=stripe.error.SignatureVerificationError("bad sig", "sig"),
        ):
            response = self._post(Client())
        assert response.status_code == 400
        order.refresh_from_db()
        assert order.paye is False

    def test_completed_but_unpaid_does_not_mark_paid(self):
        order = self._order()
        event = {
            "type": "checkout.session.completed",
            "data": {"object": {"client_reference_id": str(order.pk), "payment_status": "unpaid"}},
        }
        with mock.patch(
            "apps.contact.views.stripe.Webhook.construct_event", return_value=event
        ), mock.patch("apps.contact.views.send_mail") as send:
            response = self._post(Client())
        assert response.status_code == 200
        order.refresh_from_db()
        assert order.paye is False
        assert not send.called

    def test_idempotent_no_double_notify(self):
        # Commande déjà payée : un re-delivery ne doit pas renotifier.
        order = self._order(paye=True)
        event = {
            "type": "checkout.session.completed",
            "data": {"object": {"client_reference_id": str(order.pk), "payment_status": "paid"}},
        }
        with mock.patch(
            "apps.contact.views.stripe.Webhook.construct_event", return_value=event
        ), mock.patch("apps.contact.views.send_mail") as send:
            response = self._post(Client())
        assert response.status_code == 200
        assert not send.called
