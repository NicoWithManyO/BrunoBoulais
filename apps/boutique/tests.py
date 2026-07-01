from django.contrib.sessions.backends.cache import SessionStore
from django.core import mail
from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse

from .cart import Chapeau
from .models import BoutiquePage, Commande, LigneCommande, Produit


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
    def test_frais_port_forfait_par_mode(self):
        from .models import Commande
        from .pricing import frais_port_cents
        self.assertEqual(frais_port_cents(Commande.LIVRAISON_POINT_RELAIS), 415)
        self.assertEqual(frais_port_cents(Commande.LIVRAISON_DOMICILE), 749)
        self.assertIsNone(frais_port_cents(""))

    def test_total_articles_plus_port(self):
        from .models import Commande
        from .pricing import total_cents
        self.assertEqual(total_cents(2000, Commande.LIVRAISON_POINT_RELAIS), 2415)
        self.assertEqual(total_cents(2000, Commande.LIVRAISON_DOMICILE), 2749)
        self.assertIsNone(total_cents(2000, "inconnu"))


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
        self.livre = Produit.objects.create(nom="Livre", slug="livre", prix_cents=2000)
        self.cd = Produit.objects.create(nom="CD", slug="cd", prix_cents=1500)

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

    def test_commande_valide_cree_commande_lignes_et_notifie(self):
        self._remplir_chapeau()
        response = self.client.post(reverse("boutique:commande"), data=self._data())
        self.assertRedirects(response, reverse("boutique:merci"))

        self.assertEqual(Commande.objects.count(), 1)
        commande = Commande.objects.get()
        self.assertEqual(commande.statut, Commande.STATUT_EN_ATTENTE_REGLEMENT)
        # Montants : 2×2000 + 1×1500 = 5500 articles ; port domicile = 749.
        self.assertEqual(commande.montant_articles_cents, 5500)
        self.assertEqual(commande.frais_port_cents, 749)
        self.assertEqual(commande.montant_total_cents, 6249)

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

    def test_cb_non_propose_dans_le_formulaire(self):
        self._remplir_chapeau()
        response = self.client.post(
            reverse("boutique:commande"),
            data=self._data(mode_paiement=Commande.PAIEMENT_CB),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Commande.objects.count(), 0)
