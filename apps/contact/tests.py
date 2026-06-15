from unittest import mock

import pytest
from django.core.cache import cache
from django.test import Client

from apps.contact import forms as contact_forms
from apps.contact.forms import ContactForm
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
