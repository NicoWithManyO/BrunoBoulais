from unittest import mock

import pytest
from django.core import mail
from django.core.cache import cache
from django.test import Client

from apps.contact import forms as contact_forms
from apps.contact.forms import ContactForm
from apps.contact.models import (
    PRODUIT_INTEGRALE,
    PRODUIT_LIVRE,
    PRODUIT_PACK,
    PRODUIT_VOLUMES,
    Message,
    montant_total_cents,
)

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


def _contact_data(**overrides):
    data = {
        "nom": "Alice",
        "sujet": Message.SUJET_QUESTION,
        "email": "alice@example.com",
        "telephone": "",
        "contenu": "Bonjour Bruno, juste une question.",
        "website": "",
    }
    data.update(overrides)
    return data


@pytest.mark.django_db
class TestContactIpUnresolved:
    """Régression check sur le fail-closed introduit par f2ccab8.

    Quand `_client_ip` retourne "" (IP indéterminée), la vue doit retourner
    503 + Cache-Control: no-store — pas 200, pas 302, pas un succès silencieux
    qui aurait permis à l'attaquant de bypasser le rate-limit par IP.
    """

    def test_post_with_unresolved_ip_returns_503(self):
        client = Client()
        response = client.post("/contact/", data=_contact_data(), REMOTE_ADDR="")
        assert response.status_code == 503
        assert response["Cache-Control"] == "no-store"


@pytest.mark.django_db
class TestContactForm:
    """Le formulaire public ne propose plus la commande et n'exige que l'essentiel."""

    def test_sujet_commande_absent_des_choix(self):
        choices = dict(ContactForm().fields["sujet"].choices)
        assert Message.SUJET_COMMANDE not in choices
        assert Message.SUJET_QUESTION in choices
        assert Message.SUJET_PRESSE in choices
        assert Message.SUJET_AUTRE in choices

    def test_message_simple_valide(self):
        form = ContactForm(data=_contact_data())
        assert form.is_valid(), form.errors

    def test_telephone_optionnel(self):
        form = ContactForm(data=_contact_data(telephone=""))
        assert form.is_valid(), form.errors


@pytest.mark.django_db
class TestContactFlow:
    """POST valide → message enregistré + notifié + redirection /merci/."""

    def test_message_saves_notifies_and_redirects(self):
        client = Client()
        response = client.post("/contact/", data=_contact_data(), REMOTE_ADDR="1.2.3.4")
        assert response.status_code == 302
        assert response["Location"] == "/contact/merci/"
        assert Message.objects.count() == 1
        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == ["boulaisbruno@free.fr"]

    def test_honeypot_redirige_sans_message(self):
        client = Client()
        response = client.post(
            "/contact/",
            data=_contact_data(website="http://spam.example"),
            REMOTE_ADDR="1.2.3.4",
        )
        assert response.status_code == 302
        assert response["Location"] == "/contact/merci/"
        assert Message.objects.count() == 0
        assert len(mail.outbox) == 0


@pytest.mark.django_db
class TestContactNotificationHardening:
    """Un échec d'envoi du mail ne doit pas perdre le message."""

    def test_save_succeeds_and_logs_when_email_fails(self):
        form = ContactForm(data=_contact_data())
        assert form.is_valid(), form.errors
        with mock.patch(
            "apps.contact.forms.EmailMessage.send", side_effect=Exception("smtp down")
        ) as send, mock.patch.object(forms_logger, "error") as log_error:
            msg = form.save_and_notify()
        assert send.called
        assert msg.pk is not None
        # notified=False est persisté (visible/filtrable dans l'admin).
        assert Message.objects.get(pk=msg.pk).notified is False
        assert log_error.called

    def test_notified_true_when_email_succeeds(self):
        form = ContactForm(data=_contact_data())
        assert form.is_valid(), form.errors
        with mock.patch("apps.contact.forms.EmailMessage.send"):
            msg = form.save_and_notify()
        assert Message.objects.get(pk=msg.pk).notified is True


class TestMontantTotal:
    """Tarif total = articles (livre/volume 20 € pièce, intégrale/pack fixes) + port.

    Helpers legacy conservés pour la lisibilité des anciennes commandes en gestion.
    """

    @pytest.mark.parametrize(
        "produit, quantite, mode, attendu",
        [
            (PRODUIT_LIVRE, 1, Message.LIVRAISON_POINT_RELAIS, 2415),
            (PRODUIT_LIVRE, 1, Message.LIVRAISON_DOMICILE, 2749),
            (PRODUIT_LIVRE, 2, Message.LIVRAISON_POINT_RELAIS, 4599),
            (PRODUIT_LIVRE, 2, Message.LIVRAISON_DOMICILE, 4949),
            (PRODUIT_VOLUMES, 1, Message.LIVRAISON_POINT_RELAIS, 2415),
            (PRODUIT_VOLUMES, 1, Message.LIVRAISON_DOMICILE, 2749),
            (PRODUIT_VOLUMES, 2, Message.LIVRAISON_POINT_RELAIS, 4415),
            (PRODUIT_VOLUMES, 2, Message.LIVRAISON_DOMICILE, 4749),
            (PRODUIT_INTEGRALE, None, Message.LIVRAISON_POINT_RELAIS, 6415),
            (PRODUIT_INTEGRALE, None, Message.LIVRAISON_DOMICILE, 6749),
            (PRODUIT_PACK, None, Message.LIVRAISON_POINT_RELAIS, 8099),
            (PRODUIT_PACK, None, Message.LIVRAISON_DOMICILE, 8449),
        ],
    )
    def test_combinaisons_tarifees(self, produit, quantite, mode, attendu):
        assert montant_total_cents(produit, quantite, mode) == attendu

    def test_combinaison_inconnue_renvoie_none(self):
        assert montant_total_cents(PRODUIT_LIVRE, None, Message.LIVRAISON_DOMICILE) is None
        assert montant_total_cents(PRODUIT_LIVRE, 1, "") is None
