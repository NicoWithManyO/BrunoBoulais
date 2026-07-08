from unittest.mock import patch

import stripe
from django.contrib.sessions.backends.cache import SessionStore
from django.core import mail
from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse

from apps.parametres.models import Parametres

from .cart import Chapeau
from .models import BoutiquePage, Commande, LigneCommande, Produit, TranchePort

# Grille de tranches connue, réutilisée par les tests de calcul et de checkout.
GRILLE_TEST = [(500, 415, 749), (1000, 599, 949), (30000, 799, 1099)]


def _seed_grille(grille=GRILLE_TEST):
    """Remet une grille de tranches déterministe (indépendante du seed de migration)."""
    TranchePort.objects.all().delete()
    TranchePort.objects.bulk_create(
        TranchePort(poids_max_g=p, prix_relais_cents=r, prix_domicile_cents=d)
        for p, r, d in grille
    )


class _FakeRequest:
    """Requête minimale porteuse d'une session, suffisante pour Chapeau."""

    def __init__(self):
        self.session = SessionStore()


class ChapeauTests(TestCase):
    def setUp(self):
        self.livre = Produit.objects.create(nom="Livre", slug="livre", prix_cents=2000)
        self.cd = Produit.objects.create(nom="CD", slug="cd", prix_cents=1500)
        self.chapeau = Chapeau(_FakeRequest())

    def test_add_incremente_et_len(self):
        self.chapeau.add(self.livre)
        self.chapeau.add(self.livre)
        self.chapeau.add(self.cd)
        self.assertEqual(len(self.chapeau), 3)
        self.assertEqual(self.chapeau.montant_articles_cents, 2 * 2000 + 1500)

    def test_set_quantite_zero_retire(self):
        self.chapeau.add(self.livre)
        self.chapeau.set_quantite(self.livre.pk, 0)
        self.assertEqual(len(self.chapeau), 0)

    def test_remove_et_clear(self):
        self.chapeau.add(self.livre)
        self.chapeau.add(self.cd)
        self.chapeau.remove(self.livre.pk)
        self.assertEqual(len(self.chapeau), 1)
        self.chapeau.clear()
        self.assertFalse(self.chapeau)

    def test_produit_depublie_auto_nettoye(self):
        self.chapeau.add(self.livre)
        self.chapeau.add(self.cd)
        self.cd.publie = False
        self.cd.save()
        lignes = self.chapeau.lignes  # déclenche l'hydratation + nettoyage
        self.assertEqual([l["produit"] for l in lignes], [self.livre])
        self.assertEqual(self.chapeau.montant_articles_cents, 2000)


class ProduitContenuTests(TestCase):
    """Property contenu_volumes : quels volumes une fiche affiche selon le champ contenu."""

    def _produit(self, contenu):
        return Produit.objects.create(
            nom="P", slug=f"p-{contenu or 'none'}", prix_cents=6000, contenu=contenu
        )

    def test_integrale_developpe_les_trois_volumes(self):
        volumes = self._produit("integrale").contenu_volumes
        self.assertEqual([num for num, _ in volumes], [1, 2, 3])
        # Chaque volume porte bien ses CD (donnée VOLUMES_CONTENU).
        self.assertTrue(all(data["cds"] for _, data in volumes))

    def test_volume_unique(self):
        volumes = self._produit("2").contenu_volumes
        self.assertEqual([num for num, _ in volumes], [2])

    def test_aucun_contenu_vide(self):
        self.assertEqual(self._produit("").contenu_volumes, [])


class BoutiqueListeContenuTests(TestCase):
    """La grille /boutique/ montre bouton + modale seulement pour un produit ayant du contenu."""

    def setUp(self):
        cache.clear()
        self.client = Client()

    def test_bouton_et_modale_selon_contenu(self):
        integrale = Produit.objects.create(
            nom="L'Intégrale", slug="integrale", prix_cents=6000, contenu="integrale"
        )
        livre = Produit.objects.create(nom="Le livre", slug="livre", prix_cents=2500)
        html = self.client.get(reverse("boutique:liste")).content.decode()
        self.assertIn(f'data-voir-contenu="{integrale.pk}"', html)
        self.assertIn(f'data-contenu-modal="{integrale.pk}"', html)
        # Le livre (sans contenu) n'a ni bouton ni modale.
        self.assertNotIn(f'data-voir-contenu="{livre.pk}"', html)
        self.assertNotIn(f'data-contenu-modal="{livre.pk}"', html)


class ProduitOrderingTests(TestCase):
    """Ordering : position > 0 d'abord (ascendant), position = 0 relégué (récent d'abord)."""

    def test_position_zero_releguee_derriere(self):
        sans_ordre = Produit.objects.create(nom="Sans ordre", slug="sans", prix_cents=1000)
        premier = Produit.objects.create(nom="Premier", slug="premier", prix_cents=1000, position=1)
        deuxieme = Produit.objects.create(nom="Deuxième", slug="deuxieme", prix_cents=1000, position=2)
        self.assertEqual(
            list(Produit.objects.all()),
            [premier, deuxieme, sans_ordre],
        )


class PricingTests(TestCase):
    """Port = tranche du poids total du chapeau, colonne selon le mode."""

    def setUp(self):
        _seed_grille()
        # Emballage neutralisé : ces tests portent sur les bornes de tranches au
        # poids brut. L'ajout de l'emballage a son propre test dédié.
        p = Parametres.get_solo()
        p.poids_emballage_g = 0
        p.save()
        self.livre = Produit.objects.create(nom="Livre", slug="livre", prix_cents=2000, poids_g=500)
        self.volume = Produit.objects.create(nom="Volume", slug="volume", prix_cents=2000, poids_g=200)

    def _port(self, mode, *couples):
        """Résout la tranche du panier puis lit le port du mode (comme la vue)."""
        from .pricing import frais_port_cents, tranche_applicable
        lignes = [{"produit": p, "quantite": q} for p, q in couples]
        return frais_port_cents(tranche_applicable(lignes), mode)

    def test_mode_inconnu_ou_vide_none(self):
        self.assertIsNone(self._port("", (self.livre, 1)))
        self.assertIsNone(self._port("inconnu", (self.livre, 1)))

    def test_tranche_basse(self):
        # 500 g → tranche ≤ 500.
        self.assertEqual(self._port(Commande.LIVRAISON_POINT_RELAIS, (self.livre, 1)), 415)
        self.assertEqual(self._port(Commande.LIVRAISON_DOMICILE, (self.livre, 1)), 749)

    def test_franchit_un_palier(self):
        # 1000 g → tranche ≤ 1000.
        self.assertEqual(self._port(Commande.LIVRAISON_POINT_RELAIS, (self.livre, 2)), 599)
        self.assertEqual(self._port(Commande.LIVRAISON_DOMICILE, (self.livre, 2)), 949)

    def test_panier_mixte_somme_des_poids(self):
        # 1 livre (500) + 2 volumes (400) = 900 g → tranche ≤ 1000.
        self.assertEqual(self._port(Commande.LIVRAISON_DOMICILE, (self.livre, 1), (self.volume, 2)), 949)

    def test_depassement_clampe_sur_la_plus_lourde(self):
        self.livre.poids_g = 40000  # au-delà de la plus lourde tranche (30000)
        self.assertEqual(self._port(Commande.LIVRAISON_DOMICILE, (self.livre, 1)), 1099)

    def test_aucune_tranche_none(self):
        TranchePort.objects.all().delete()
        self.assertIsNone(self._port(Commande.LIVRAISON_DOMICILE, (self.livre, 1)))

    def test_emballage_ajoute_une_fois_par_commande(self):
        p = Parametres.get_solo()
        p.poids_emballage_g = 50
        p.save()
        # L'emballage décale la tranche : livre 500 g seul → ≤ 500 (415) ;
        # avec 50 g → 550 g → ≤ 1000 (599).
        self.assertEqual(self._port(Commande.LIVRAISON_POINT_RELAIS, (self.livre, 1)), 599)
        # Compté une seule fois, pas par article : 2 × 220 g = 440 g de
        # marchandise → 490 g avec l'emballage → ≤ 500 (415). Par article
        # (2 × 50) on aurait 540 g → ≤ 1000 (599). Le 415 prouve le « une fois ».
        petit = Produit.objects.create(nom="Petit", slug="petit", prix_cents=1000, poids_g=220)
        self.assertEqual(self._port(Commande.LIVRAISON_POINT_RELAIS, (petit, 2)), 415)


class BoutiquePageSingletonTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_get_solo_cree_un_seul_singleton(self):
        page1 = BoutiquePage.get_solo()
        page2 = BoutiquePage.get_solo()
        self.assertEqual(page1.pk, page2.pk)
        self.assertEqual(BoutiquePage.objects.count(), 1)


class CommandeCheckoutTests(TestCase):
    def setUp(self):
        cache.clear()  # rate-limit en cache LocMem : isole les tests
        self.client = Client()
        _seed_grille()
        self.livre = Produit.objects.create(nom="Livre", slug="livre", prix_cents=2000, poids_g=500)
        self.cd = Produit.objects.create(nom="CD", slug="cd", prix_cents=1500, poids_g=200)

    def _remplir_chapeau(self):
        self.client.post(reverse("boutique:chapeau_ajouter", args=[self.livre.pk]))
        self.client.post(reverse("boutique:chapeau_ajouter", args=[self.livre.pk]))
        self.client.post(reverse("boutique:chapeau_ajouter", args=[self.cd.pk]))

    def _data(self, **overrides):
        data = {
            "nom": "Alice",
            "email": "alice@example.com",
            "telephone": "0600000000",
            "adresse_postale": "1 rue des Lilas, 40000 Mont-de-Marsan",
            "mode_livraison": Commande.LIVRAISON_DOMICILE,
            "mode_paiement": Commande.PAIEMENT_CHEQUE,
            "website": "",
        }
        data.update(overrides)
        return data

    def test_chapeau_vide_redirige(self):
        response = self.client.get(reverse("boutique:commande"))
        self.assertRedirects(response, reverse("boutique:chapeau"))

    def test_page_commande_expose_port_par_mode_selon_chapeau(self):
        # Chapeau : livre ×2 (1000 g) + CD ×1 (200 g) = 1200 g → tranche ≤ 30000.
        self._remplir_chapeau()
        frais_port = self.client.get(reverse("boutique:commande")).context["frais_port"]
        self.assertEqual(frais_port[Commande.LIVRAISON_POINT_RELAIS], 799)
        self.assertEqual(frais_port[Commande.LIVRAISON_DOMICILE], 1099)

    def test_grille_vide_refuse_la_commande(self):
        # Sans tranche configurée, le port est indéterminé : on refuse au lieu de
        # créer une commande à port nul (facturation CB de l'article seul).
        TranchePort.objects.all().delete()
        self._remplir_chapeau()
        response = self.client.post(reverse("boutique:commande"), data=self._data())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Commande.objects.count(), 0)

    def test_commande_valide_cree_commande_lignes_et_notifie(self):
        self._remplir_chapeau()
        response = self.client.post(reverse("boutique:commande"), data=self._data())
        self.assertRedirects(response, reverse("boutique:merci"))

        self.assertEqual(Commande.objects.count(), 1)
        commande = Commande.objects.get()
        self.assertEqual(commande.statut, Commande.STATUT_EN_ATTENTE_REGLEMENT)
        # Articles : 2×2000 + 1×1500 = 5500. Poids 1200 g → tranche ≤ 30000,
        # port domicile = 1099.
        self.assertEqual(commande.montant_articles_cents, 5500)
        self.assertEqual(commande.frais_port_cents, 1099)
        self.assertEqual(commande.montant_total_cents, 6599)

        # Snapshots des lignes (libellé + prix figés).
        lignes = {l.libelle: l for l in commande.lignes.all()}
        self.assertEqual(set(lignes), {"Livre", "CD"})
        self.assertEqual(lignes["Livre"].quantite, 2)
        self.assertEqual(lignes["Livre"].prix_unitaire_cents, 2000)
        self.assertEqual(lignes["CD"].quantite, 1)

        # Mail à Bruno uniquement.
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["boulaisbruno@free.fr"])
        self.assertIn(commande.reference_commande, mail.outbox[0].body)

        # Chapeau vidé après commande.
        self.assertEqual(self.client.session.get("chapeau"), {})

    def test_telephone_requis(self):
        self._remplir_chapeau()
        response = self.client.post(reverse("boutique:commande"), data=self._data(telephone=""))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Commande.objects.count(), 0)

    def test_honeypot_redirige_merci_sans_commande(self):
        self._remplir_chapeau()
        response = self.client.post(
            reverse("boutique:commande"),
            data=self._data(website="http://spam.example"),
        )
        self.assertRedirects(response, reverse("boutique:merci"))
        self.assertEqual(Commande.objects.count(), 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_commande_cb_cree_commande_et_redirige_vers_paiement(self):
        self._remplir_chapeau()
        response = self.client.post(
            reverse("boutique:commande"),
            data=self._data(mode_paiement=Commande.PAIEMENT_CB),
        )
        commande = Commande.objects.get()
        # Commande en attente de paiement, chapeau conservé, aucun mail avant Stripe.
        self.assertEqual(commande.statut, Commande.STATUT_EN_ATTENTE_PAIEMENT)
        self.assertRedirects(
            response,
            reverse("boutique:paiement_cb", args=[commande.pk]),
            fetch_redirect_response=False,
        )
        self.assertEqual(len(mail.outbox), 0)
        self.assertNotEqual(self.client.session.get("chapeau"), {})


class StripePaiementTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client()
        self.commande = Commande.objects.create(
            nom="Alice",
            email="alice@example.com",
            mode_paiement=Commande.PAIEMENT_CB,
            montant_articles_cents=2000,
            frais_port_cents=749,
            montant_total_cents=2749,
            statut=Commande.STATUT_EN_ATTENTE_PAIEMENT,
        )
        LigneCommande.objects.create(
            commande=self.commande, libelle="Livre", prix_unitaire_cents=2000, quantite=1
        )

    def _bind_session(self, pk=None):
        """Lie une réf de commande à la session navigateur (posée au checkout)."""
        session = self.client.session
        session["commande_ref"] = pk if pk is not None else self.commande.pk
        session.save()

    def test_paiement_cb_cree_session_et_redirige_303(self):
        self._bind_session()
        session = type("S", (), {"id": "cs_test_123", "url": "https://checkout.stripe.com/pay/cs_test_123"})()
        with patch("apps.boutique.views.creer_session_checkout", return_value=session) as mock:
            response = self.client.get(reverse("boutique:paiement_cb", args=[self.commande.pk]))
        mock.assert_called_once()
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response["Location"], session.url)
        self.commande.refresh_from_db()
        self.assertEqual(self.commande.stripe_session_id, "cs_test_123")

    def test_paiement_cb_deja_paye_redirige_merci(self):
        self._bind_session()
        self.commande.statut = Commande.STATUT_PAYE
        self.commande.save()
        response = self.client.get(reverse("boutique:paiement_cb", args=[self.commande.pk]))
        self.assertRedirects(response, reverse("boutique:merci"), fetch_redirect_response=False)

    def test_paiement_cb_refuse_commande_non_liee(self):
        # Session liée à une autre commande : on refuse (anti-énumération IDOR).
        self._bind_session(pk=self.commande.pk + 999)
        with patch("apps.boutique.views.creer_session_checkout") as mock:
            response = self.client.get(reverse("boutique:paiement_cb", args=[self.commande.pk]))
        mock.assert_not_called()
        self.assertRedirects(response, reverse("boutique:chapeau"), fetch_redirect_response=False)

    def test_paiement_cb_refuse_commande_non_cb(self):
        # Réf liée mais commande en mode chèque : pas d'ouverture Stripe (pas de
        # mélange de canaux via une réf commande_ref résiduelle).
        self.commande.mode_paiement = Commande.PAIEMENT_CHEQUE
        self.commande.statut = Commande.STATUT_EN_ATTENTE_REGLEMENT
        self.commande.save()
        self._bind_session()
        with patch("apps.boutique.views.creer_session_checkout") as mock:
            response = self.client.get(reverse("boutique:paiement_cb", args=[self.commande.pk]))
        mock.assert_not_called()
        self.assertRedirects(response, reverse("boutique:chapeau"), fetch_redirect_response=False)

    def test_paiement_cb_echec_stripe_conserve_ref_pour_reessai(self):
        self._bind_session()
        with patch("apps.boutique.views.creer_session_checkout", side_effect=Exception("boom")):
            response = self.client.get(reverse("boutique:paiement_cb", args=[self.commande.pk]))
        self.assertRedirects(response, reverse("boutique:paiement_annule"), fetch_redirect_response=False)
        # La réf reste en session : l'écran d'annulation peut proposer un réessai.
        self.assertEqual(self.client.session.get("commande_ref"), self.commande.pk)

    def test_paiement_annule_ignore_ref_deja_payee(self):
        # Réf résiduelle d'une commande déjà réglée : l'écran d'annulation ne
        # doit rien afficher (pas de réessai trompeur).
        self.commande.statut = Commande.STATUT_PAYE
        self.commande.save()
        self._bind_session()
        response = self.client.get(reverse("boutique:paiement_annule"))
        self.assertIsNone(response.context["commande"])

    def test_paiement_success_sans_session_id_ne_vide_pas(self):
        produit = Produit.objects.create(nom="Livre", slug="l", prix_cents=2000)
        session = self.client.session
        session["chapeau"] = {str(produit.pk): 1}
        session.save()
        response = self.client.get(reverse("boutique:paiement_success"))
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["commande"])
        # GET nu (prefetch, favori) : chapeau intact, rien validé.
        self.assertEqual(self.client.session.get("chapeau"), {str(produit.pk): 1})

    def test_paiement_success_paye_vide_et_affiche(self):
        self._bind_session()
        produit = Produit.objects.create(nom="Livre", slug="l", prix_cents=2000)
        session = self.client.session
        session["chapeau"] = {str(produit.pk): 1}
        session.save()
        stripe_session = {"payment_status": "paid", "metadata": {"commande_id": str(self.commande.pk)}}
        with patch("apps.boutique.views.stripe.checkout.Session.retrieve", return_value=stripe_session):
            response = self.client.get(reverse("boutique:paiement_success") + "?session_id=cs_test_1")
        self.assertEqual(response.context["commande"], self.commande)
        self.assertEqual(self.client.session.get("chapeau"), {})

    def test_paiement_success_session_autrui_ne_revele_rien(self):
        # session_id payé d'une commande qui n'est PAS celle liée à la session
        # navigateur : rien n'est révélé, le chapeau du visiteur n'est pas vidé.
        produit = Produit.objects.create(nom="Livre", slug="l", prix_cents=2000)
        session = self.client.session
        session["chapeau"] = {str(produit.pk): 1}
        session["commande_ref"] = self.commande.pk + 999  # autre commande
        session.save()
        stripe_session = {"payment_status": "paid", "metadata": {"commande_id": str(self.commande.pk)}}
        with patch("apps.boutique.views.stripe.checkout.Session.retrieve", return_value=stripe_session):
            response = self.client.get(reverse("boutique:paiement_success") + "?session_id=cs_test_1")
        self.assertIsNone(response.context["commande"])
        self.assertEqual(self.client.session.get("chapeau"), {str(produit.pk): 1})

    def test_paiement_success_non_paye_ne_vide_pas(self):
        produit = Produit.objects.create(nom="Livre", slug="l", prix_cents=2000)
        session = self.client.session
        session["chapeau"] = {str(produit.pk): 1}
        session.save()
        stripe_session = {"payment_status": "unpaid", "metadata": {"commande_id": str(self.commande.pk)}}
        with patch("apps.boutique.views.stripe.checkout.Session.retrieve", return_value=stripe_session):
            response = self.client.get(reverse("boutique:paiement_success") + "?session_id=cs_test_1")
        self.assertIsNone(response.context["commande"])
        self.assertEqual(self.client.session.get("chapeau"), {str(produit.pk): 1})

    def _event(self, **session_overrides):
        session = {"payment_status": "paid", "metadata": {"commande_id": str(self.commande.pk)}}
        session.update(session_overrides)
        return {"type": "checkout.session.completed", "data": {"object": session}}

    def _post_webhook(self, event):
        with patch("apps.boutique.views.stripe.Webhook.construct_event", return_value=event):
            return self.client.post(
                reverse("boutique:webhook_stripe"),
                data=b"{}",
                content_type="application/json",
                HTTP_STRIPE_SIGNATURE="sig",
            )

    def test_webhook_completed_passe_paye_et_notifie(self):
        response = self._post_webhook(self._event())
        self.assertEqual(response.status_code, 200)
        self.commande.refresh_from_db()
        self.assertEqual(self.commande.statut, Commande.STATUT_PAYE)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["boulaisbruno@free.fr"])
        self.assertIn(self.commande.reference_commande, mail.outbox[0].body)

    def test_webhook_idempotent_ne_renotifie_pas(self):
        self._post_webhook(self._event())
        self._post_webhook(self._event())
        self.commande.refresh_from_db()
        self.assertEqual(self.commande.statut, Commande.STATUT_PAYE)
        self.assertEqual(len(mail.outbox), 1)

    def test_webhook_notify_defaillant_ne_500_pas(self):
        # Un plantage dans notify() (ici construction du récap) ne doit pas
        # remonter en 500 : sinon Stripe rejouerait, trouverait la commande déjà
        # « payée » et n'aurait plus rien à notifier. On absorbe et on marque
        # notified=False pour que la commande remonte « à traiter » en gestion.
        with patch("apps.boutique.pricing.montant_euros", side_effect=Exception("boom")):
            response = self._post_webhook(self._event())
        self.assertEqual(response.status_code, 200)
        self.commande.refresh_from_db()
        self.assertEqual(self.commande.statut, Commande.STATUT_PAYE)
        self.assertFalse(self.commande.notified)
        self.assertEqual(len(mail.outbox), 0)

    def test_webhook_n_exhume_pas_commande_annulee(self):
        # Un webhook payé tardif/rejoué ne doit pas repasser une commande annulée
        # à « payé » : seule une CB en attente bascule.
        self.commande.statut = Commande.STATUT_ANNULE
        self.commande.save()
        response = self._post_webhook(self._event())
        self.assertEqual(response.status_code, 200)
        self.commande.refresh_from_db()
        self.assertEqual(self.commande.statut, Commande.STATUT_ANNULE)
        self.assertEqual(len(mail.outbox), 0)

    def test_webhook_commande_introuvable_loggue(self):
        # Paiement confirmé mais commande absente : on log une alerte (CB débitée
        # sans commande à honorer), on ne notifie pas, on renvoie 200.
        event = self._event(metadata={"commande_id": "999999"})
        with self.assertLogs("apps.boutique.views", level="ERROR") as logs:
            response = self._post_webhook(event)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(any("introuvable" in m for m in logs.output))
        self.assertEqual(len(mail.outbox), 0)

    def test_webhook_non_paye_ignore(self):
        response = self._post_webhook(self._event(payment_status="unpaid"))
        self.assertEqual(response.status_code, 200)
        self.commande.refresh_from_db()
        self.assertEqual(self.commande.statut, Commande.STATUT_EN_ATTENTE_PAIEMENT)
        self.assertEqual(len(mail.outbox), 0)

    def test_webhook_signature_invalide_400(self):
        with patch(
            "apps.boutique.views.stripe.Webhook.construct_event",
            side_effect=stripe.error.SignatureVerificationError("bad", "sig"),
        ):
            response = self.client.post(
                reverse("boutique:webhook_stripe"),
                data=b"{}",
                content_type="application/json",
                HTTP_STRIPE_SIGNATURE="bad",
            )
        self.assertEqual(response.status_code, 400)
        self.commande.refresh_from_db()
        self.assertEqual(self.commande.statut, Commande.STATUT_EN_ATTENTE_PAIEMENT)
