from unittest import mock

import pytest
from django.core.cache import cache
from django.test import Client

from apps.contact import forms as contact_forms
from apps.contact.forms import CommandeForm, ContactForm
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
    """Le mode de paiement (chèque/virement) est requis uniquement pour une commande."""

    def _data(self, **overrides):
        data = {
            "nom": "Alice",
            "sujet": Message.SUJET_COMMANDE,
            "email": "alice@example.com",
            "telephone": "0612345678",
            "adresse_postale": "1 rue du Livre, 40000 Mont-de-Marsan",
            "mode_paiement": Message.PAIEMENT_CHEQUE,
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
class TestContactNotificationHardening:
    """Un échec d'envoi du mail ne doit pas perdre la commande."""

    def test_save_succeeds_and_logs_when_email_fails(self):
        form = ContactForm(
            data={
                "nom": "Alice",
                "sujet": Message.SUJET_COMMANDE,
                "email": "alice@example.com",
                "telephone": "0612345678",
                "adresse_postale": "1 rue du Livre, 40000 Mont-de-Marsan",
                "mode_paiement": Message.PAIEMENT_CHEQUE,
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
                "mode_paiement": Message.PAIEMENT_CHEQUE,
                "contenu": "Je commande un exemplaire dédicacé.",
                "website": "",
            }
        )
        assert form.is_valid(), form.errors
        with mock.patch("apps.contact.forms.EmailMessage.send"):
            msg = form.save_and_notify()
        assert Message.objects.get(pk=msg.pk).notified is True


class TestMontantTotal:
    """Tarif total = articles (livre/volume 20 € pièce, intégrale/pack fixes) + port."""

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


def _commande_data(**overrides):
    # Commande « Le livre, 1 ex, point relais » par défaut (point via le widget).
    data = {
        "nom": "Alice",
        "sujet": Message.SUJET_COMMANDE,
        "email": "alice@example.com",
        "telephone": "0612345678",
        "mode_paiement": Message.PAIEMENT_CHEQUE,
        "produit": PRODUIT_LIVRE,
        "nb_exemplaires": 1,
        "mode_livraison": Message.LIVRAISON_POINT_RELAIS,
        "point_relais_id": "FR-12345",
        "point_relais_libelle": "Tabac de la Poste, 40000 Mont-de-Marsan",
        "adresse_postale": "Alice Martin, 1 rue du Livre, 40000 Mont-de-Marsan",
        "contenu": "Je commande un exemplaire.",
        "website": "",
    }
    data.update(overrides)
    return data


@pytest.mark.django_db
class TestCommandeForm:
    """Offre, quantité/volumes, mode de livraison, point relais et adresse selon l'offre."""

    def test_commande_requires_produit(self):
        form = CommandeForm(data=_commande_data(produit=""))
        assert not form.is_valid()
        assert "produit" in form.errors

    def test_livre_requires_nb_exemplaires(self):
        form = CommandeForm(data=_commande_data(nb_exemplaires=""))
        assert not form.is_valid()
        assert "nb_exemplaires" in form.errors

    def test_volumes_requires_one_or_two(self):
        # 0 volume → invalide.
        form = CommandeForm(data=_commande_data(produit=PRODUIT_VOLUMES, volumes=[]))
        assert not form.is_valid()
        assert "volumes" in form.errors
        # 3 volumes (= Intégrale) → invalide.
        form = CommandeForm(data=_commande_data(produit=PRODUIT_VOLUMES, volumes=["1", "2", "3"]))
        assert not form.is_valid()
        assert "volumes" in form.errors

    def test_volumes_one_or_two_is_valid(self):
        form = CommandeForm(data=_commande_data(produit=PRODUIT_VOLUMES, volumes=["1", "3"]))
        assert form.is_valid(), form.errors

    def test_integrale_valide_sans_sous_controle(self):
        # Intégrale / pack : pas d'exemplaires ni de volumes à fournir.
        form = CommandeForm(data=_commande_data(produit=PRODUIT_INTEGRALE, nb_exemplaires="", volumes=[]))
        assert form.is_valid(), form.errors

    def test_pack_valide_sans_sous_controle(self):
        form = CommandeForm(data=_commande_data(produit=PRODUIT_PACK, nb_exemplaires="", volumes=[]))
        assert form.is_valid(), form.errors

    def test_offre_sans_sous_controle_purge_les_residus(self):
        # Bascule livre/volumes → intégrale : ni exemplaires ni volumes ne subsistent.
        form = CommandeForm(
            data=_commande_data(produit=PRODUIT_INTEGRALE, nb_exemplaires=2, volumes=["1", "2"])
        )
        assert form.is_valid(), form.errors
        assert form.cleaned_data["nb_exemplaires"] is None
        assert form.cleaned_data["volumes"] == []

    def test_offre_sans_livre_purge_la_dedicace(self):
        # CD seuls (intégrale, volumes) : pas de dédicace de livre à conserver.
        form = CommandeForm(
            data=_commande_data(
                produit=PRODUIT_INTEGRALE, nb_exemplaires="", volumes=[],
                dedicace=True, prenom_dedicace="Léa",
            )
        )
        assert form.is_valid(), form.errors
        assert form.cleaned_data["dedicace"] is False
        assert form.cleaned_data["prenom_dedicace"] == ""

    def test_pack_conserve_la_dedicace(self):
        # Le pack inclut le livre : la dédicace reste possible.
        form = CommandeForm(
            data=_commande_data(
                produit=PRODUIT_PACK, nb_exemplaires="", volumes=[],
                dedicace=True, prenom_dedicace="Léa",
            )
        )
        assert form.is_valid(), form.errors
        assert form.cleaned_data["dedicace"] is True
        assert form.cleaned_data["prenom_dedicace"] == "Léa"

    def test_sujet_non_commande_purge_les_champs_offre(self):
        # Le formulaire sert tous les sujets : un POST forgé portant offre/volumes/
        # dédicace sur un simple message ne doit rien persister de tout ça.
        form = CommandeForm(
            data=_commande_data(
                sujet=Message.SUJET_QUESTION,
                produit=PRODUIT_INTEGRALE, nb_exemplaires=2, volumes=["1", "2"],
                dedicace=True, prenom_dedicace="Léa",
            )
        )
        assert form.is_valid(), form.errors
        assert form.cleaned_data["produit"] == ""
        assert form.cleaned_data["nb_exemplaires"] is None
        assert form.cleaned_data["volumes"] == []
        assert form.cleaned_data["mode_livraison"] == ""
        assert form.cleaned_data["point_relais_id"] == ""
        assert form.cleaned_data["point_relais_libelle"] == ""
        assert form.cleaned_data["dedicace"] is False
        assert form.cleaned_data["prenom_dedicace"] == ""

    def test_commande_requires_mode_livraison(self):
        form = CommandeForm(data=_commande_data(mode_livraison=""))
        assert not form.is_valid()
        assert "mode_livraison" in form.errors

    def test_relais_without_point_is_valid(self):
        # Point relais non sélectionné : autorisé (Bruno le règle en direct avec le client).
        form = CommandeForm(data=_commande_data(point_relais_id="", point_relais_libelle=""))
        assert form.is_valid(), form.errors

    def test_relais_requires_adresse(self):
        # Mondial Relay exige une adresse destinataire même en point relais.
        form = CommandeForm(data=_commande_data(adresse_postale=""))
        assert not form.is_valid()
        assert "adresse_postale" in form.errors

    def test_domicile_requires_adresse(self):
        form = CommandeForm(
            data=_commande_data(
                mode_livraison=Message.LIVRAISON_DOMICILE,
                point_relais_id="",
                point_relais_libelle="",
                adresse_postale="",
            )
        )
        assert not form.is_valid()
        assert "adresse_postale" in form.errors

    def test_domicile_strips_leftover_point_relais(self):
        # Bascule relais → domicile : aucun point fantôme ne doit subsister.
        form = CommandeForm(
            data=_commande_data(
                mode_livraison=Message.LIVRAISON_DOMICILE,
                adresse_postale="1 rue du Livre, 40000 Mont-de-Marsan",
                point_relais_id="FR-99999",
                point_relais_libelle="Ancien point relais",
            )
        )
        assert form.is_valid(), form.errors
        assert form.cleaned_data["point_relais_id"] == ""
        assert form.cleaned_data["point_relais_libelle"] == ""

    def test_domicile_with_adresse_is_valid(self):
        form = CommandeForm(
            data=_commande_data(
                mode_livraison=Message.LIVRAISON_DOMICILE,
                point_relais_id="",
                point_relais_libelle="",
                adresse_postale="1 rue du Livre, 40000 Mont-de-Marsan",
            )
        )
        assert form.is_valid(), form.errors

    def test_relais_complete_is_valid(self):
        form = CommandeForm(data=_commande_data())
        assert form.is_valid(), form.errors


@pytest.mark.django_db
class TestCommandeFlow:
    """Page principale /contact/ : la commande est capturée puis redirige vers /merci/."""

    def test_commande_saves_then_redirects_with_session(self):
        client = Client()
        with mock.patch("apps.contact.forms.EmailMessage.send"):
            response = client.post("/contact/", data=_commande_data(), REMOTE_ADDR="1.2.3.4")
        assert response.status_code == 302
        assert response["Location"] == "/contact/merci/"
        assert Message.objects.count() == 1
        assert client.session["order_ref"] == Message.objects.get().pk

    def test_honeypot_clears_stale_order_ref(self):
        # Piège déclenché : redirige vers /merci/ sans réafficher une commande résiduelle.
        client = Client()
        session = client.session
        session["order_ref"] = 1
        session.save()
        response = client.post(
            "/contact/",
            data=_commande_data(website="http://spam.example"),
            REMOTE_ADDR="1.2.3.4",
        )
        assert response.status_code == 302
        assert response["Location"] == "/contact/merci/"
        assert "order_ref" not in client.session
        assert Message.objects.count() == 0

    def test_non_commande_clears_session(self):
        client = Client()
        session = client.session
        session["order_ref"] = 1
        session.save()
        with mock.patch("apps.contact.forms.EmailMessage.send"):
            response = client.post(
                "/contact/",
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
    """La page /merci/ récapitule la commande et la consigne de paiement, une seule fois."""

    def _order(self, **overrides):
        defaults = {
            "nom": "Alice",
            "email": "alice@example.com",
            "sujet": Message.SUJET_COMMANDE,
            "mode_paiement": Message.PAIEMENT_CHEQUE,
            "produit": PRODUIT_LIVRE,
            "nb_exemplaires": 1,
            "mode_livraison": Message.LIVRAISON_POINT_RELAIS,
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

    def test_shows_recap_and_cheque_instructions(self):
        order = self._order()
        response = self._client_with_order(order).get("/contact/merci/")
        assert response.status_code == 200
        body = response.content.decode()
        assert str(order.pk) in body
        assert "Chemin Orossen" in body  # consigne chèque
        assert "24,15" in body  # total 1 ex point relais

    def test_reference_consumed_after_display(self):
        order = self._order()
        client = self._client_with_order(order)
        first = client.get("/contact/merci/")
        assert "Chemin Orossen" in first.content.decode()
        # La référence est consommée : un rechargement ne réaffiche plus la commande.
        reloaded = client.get("/contact/merci/")
        assert "Chemin Orossen" not in reloaded.content.decode()

    def test_without_session_is_plain_thanks(self):
        response = Client().get("/contact/merci/")
        assert response.status_code == 200
        assert "Chemin Orossen" not in response.content.decode()
