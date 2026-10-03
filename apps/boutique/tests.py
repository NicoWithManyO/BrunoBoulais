from unittest.mock import patch

from django.contrib.messages import get_messages
from django.contrib.sessions.backends.cache import SessionStore
from django.core import mail
from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse

from apps.parametres.models import Parametres

from .cart import Chapeau
from .models import BoutiquePage, Commande, Produit, TranchePort

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


class ChapeauAjouterViewTests(TestCase):
    """La vue d'ajout au chapeau file un message de confirmation (rendu en toast)."""

    def setUp(self):
        self.produit = Produit.objects.create(
            nom="Livre", slug="livre", prix_cents=2000, publie=True
        )

    def test_ajout_file_un_message_succes(self):
        resp = self.client.post(
            reverse("boutique:chapeau_ajouter", args=[self.produit.pk]),
            HTTP_REFERER=reverse("boutique:liste"),
        )
        msgs = list(get_messages(resp.wsgi_request))
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0].level_tag, "success")
        self.assertIn(self.produit.nom, str(msgs[0]))


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
        # créer une commande à port nul.
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

    def test_notify_defaillant_enregistre_la_commande_sans_500(self):
        # Un plantage dans notify() (ici construction du récap) ne doit pas
        # remonter en 500 : la commande est déjà enregistrée, on la marque
        # notified=False pour qu'elle remonte « à traiter » en gestion.
        self._remplir_chapeau()
        with patch("apps.boutique.pricing.montant_euros", side_effect=Exception("boom")):
            response = self.client.post(reverse("boutique:commande"), data=self._data())
        self.assertRedirects(response, reverse("boutique:merci"))
        commande = Commande.objects.get()
        self.assertFalse(commande.notified)
        self.assertEqual(len(mail.outbox), 0)
