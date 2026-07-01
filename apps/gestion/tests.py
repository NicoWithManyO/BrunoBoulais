import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.boutique.models import Commande, LigneCommande, Produit
from apps.carnet.models import Billet, BilletImageContenu
from apps.contact.models import PRODUIT_LIVRE, Message

# Uploads de test isolés dans un répertoire jetable (nettoyé en fin de classe).
_MEDIA_ROOT = tempfile.mkdtemp()

# PNG 1×1 valide, suffisant pour un ImageField.
_PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c63f80f00010101000a2db40000000049454e44ae426082"
)


# Le context processor `site_context` résout static("img/og-default.jpg") : sans
# collectstatic, le ManifestStaticFilesStorage des settings échoue en test. On
# repasse au stockage statique simple, non concerné par cette feature.
@override_settings(MEDIA_ROOT=_MEDIA_ROOT, STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class BilletPreviewTests(TestCase):
    """L'aperçu live rend le feuillet du Carnet à partir des valeurs POSTées,
    sans rien enregistrer."""

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(_MEDIA_ROOT, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        user = get_user_model().objects.create_user("staff", is_staff=True)
        self.client.force_login(user)

    def test_preview_billet_existant_reflete_les_valeurs_postees(self):
        billet = Billet.objects.create(
            titre="Ancien", contenu="<p>Ancien texte</p>",
            statut=Billet.STATUT_BROUILLON,
        )
        resp = self.client.post(
            reverse("gestion:billet_preview", args=[billet.pk]),
            {"titre": "Nouveau titre", "statut": "brouillon",
             "contenu": "<p>Texte en cours</p>"},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn("carnet-paper", body)
        self.assertIn("Nouveau titre", body)
        self.assertIn("Texte en cours", body)
        # Rien n'est enregistré : le billet en base reste inchangé.
        billet.refresh_from_db()
        self.assertEqual(billet.titre, "Ancien")

    def test_preview_nouveau_billet_sans_pk(self):
        resp = self.client.post(
            reverse("gestion:billet_preview_new"),
            {"titre": "Brouillon", "statut": "brouillon", "contenu": ""},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("carnet-paper", resp.content.decode())
        self.assertIn("Brouillon", resp.content.decode())

    def test_preview_applique_largeur_alignement_non_enregistres(self):
        # Une image de contenu en pleine largeur centrée, référencée dans le corps.
        billet = Billet.objects.create(
            titre="T", contenu="<p>[image:1]</p>", statut=Billet.STATUT_BROUILLON,
        )
        image = BilletImageContenu.objects.create(
            billet=billet, position=1, largeur="100", alignement="center",
            image=SimpleUploadedFile("a.png", _PNG_1PX, content_type="image/png"),
        )
        p = "images_contenu"  # préfixe par défaut du formset inline
        resp = self.client.post(
            reverse("gestion:billet_preview", args=[billet.pk]),
            {
                "titre": "T", "statut": "brouillon", "contenu": "<p>[image:1]</p>",
                f"{p}-TOTAL_FORMS": "1", f"{p}-INITIAL_FORMS": "1",
                f"{p}-MIN_NUM_FORMS": "0", f"{p}-MAX_NUM_FORMS": "1000",
                f"{p}-0-id": str(image.pk), f"{p}-0-billet": str(billet.pk),
                f"{p}-0-position": "1", f"{p}-0-largeur": "50",
                f"{p}-0-alignement": "left", f"{p}-0-alt": "", f"{p}-0-legende": "",
            },
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        # L'aperçu reflète les nouvelles largeur/alignement…
        self.assertIn("news-img--w50", body)
        self.assertIn("news-img--left", body)
        # …sans rien enregistrer.
        image.refresh_from_db()
        self.assertEqual(image.largeur, "100")
        self.assertEqual(image.alignement, "center")


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class MessageDetailCommandeTests(TestCase):
    """Le détail d'un message de commande montre montant, livraison et état du paiement."""

    def setUp(self):
        user = get_user_model().objects.create_user("staff", is_staff=True)
        self.client.force_login(user)

    def test_commande_domicile_non_payee(self):
        order = Message.objects.create(
            nom="Alice", email="a@b.fr", sujet=Message.SUJET_COMMANDE,
            produit=PRODUIT_LIVRE, nb_exemplaires=2, mode_livraison=Message.LIVRAISON_DOMICILE,
            adresse_postale="1 rue X\n40000 Ville", mode_paiement=Message.PAIEMENT_CHEQUE,
            paye=False, contenu="Bonjour",
        )
        body = self.client.get(
            reverse("gestion:message_detail", args=[order.pk])
        ).content.decode()
        self.assertIn("En attente de règlement", body)
        self.assertIn("49,49", body)  # total 2 ex domicile
        self.assertIn("9,49", body)   # frais de port domicile
        self.assertIn("Domicile", body)
        self.assertIn("1 rue X", body)
        self.assertIn("Chèque", body)

    def test_commande_relais_payee(self):
        order = Message.objects.create(
            nom="Bob", email="b@b.fr", sujet=Message.SUJET_COMMANDE,
            produit=PRODUIT_LIVRE, nb_exemplaires=1, mode_livraison=Message.LIVRAISON_POINT_RELAIS,
            point_relais_id="FR-123", point_relais_libelle="Tabac, 40000 MDM",
            dedicace=False, mode_paiement=Message.PAIEMENT_CHEQUE, paye=True, contenu="x",
        )
        body = self.client.get(
            reverse("gestion:message_detail", args=[order.pk])
        ).content.decode()
        self.assertIn("Payé", body)
        self.assertIn("24,15", body)  # total 1 ex relais
        self.assertIn("Tabac, 40000 MDM", body)
        self.assertIn("FR-123", body)

    def test_message_simple_sans_bloc_commande(self):
        msg = Message.objects.create(
            nom="Carl", email="c@b.fr", sujet=Message.SUJET_QUESTION, contenu="Question ?",
        )
        body = self.client.get(
            reverse("gestion:message_detail", args=[msg.pk])
        ).content.decode()
        self.assertNotIn("En attente de règlement", body)


@override_settings(MEDIA_ROOT=_MEDIA_ROOT, STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class ProduitCrudTests(TestCase):
    """CRUD produit boutique : création avec illustration + suppression nettoyant le fichier."""

    # PNG 2×2 réellement valide (le _PNG_1PX du module a un checksum IDAT
    # cassé → rejeté par la validation ImageField/Pillow ; ici on en a besoin).
    _PNG_OK = bytes.fromhex(
        "89504e470d0a1a0a0000000d4948445200000002000000020802000000fdd49a73"
        "0000001649444154789c633c91a2c1c0c0c0c4c0c0c0c0c0000010ba0158bb948b"
        "e30000000049454e44ae426082"
    )

    def setUp(self):
        user = get_user_model().objects.create_user("staff", is_staff=True)
        self.client.force_login(user)

    def test_creation_avec_illustration_et_slug_auto(self):
        img = SimpleUploadedFile("Cover.png", self._PNG_OK, content_type="image/png")
        resp = self.client.post(reverse("gestion:produit_ajouter"), {
            "nom": "Le livre",
            "slug": "",  # laissé vide → généré depuis le nom
            "reference": "LIV",
            "prix_cents": "2000",
            "description": "",
            "illustration": img,
            "dedicacable": "on",
            "position": "1",
            "publie": "on",
        })
        self.assertEqual(resp.status_code, 302)
        produit = Produit.objects.get()
        self.assertEqual(produit.slug, "le-livre")
        self.assertTrue(produit.illustration)
        self.assertTrue(produit.illustration.storage.exists(produit.illustration.name))

    def test_suppression_nettoie_le_fichier(self):
        img = SimpleUploadedFile("c.png", self._PNG_OK, content_type="image/png")
        produit = Produit.objects.create(nom="CD", slug="cd", prix_cents=1500, illustration=img)
        name = produit.illustration.name
        storage = produit.illustration.storage
        self.assertTrue(storage.exists(name))
        resp = self.client.post(reverse("gestion:produit_supprimer", args=[produit.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Produit.objects.filter(pk=produit.pk).exists())
        self.assertFalse(storage.exists(name))


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class CommandeGestionTests(TestCase):
    """Gestion des commandes : filtres de liste, marquage payé/archive, badge non-lues."""

    def setUp(self):
        user = get_user_model().objects.create_user("staff", is_staff=True)
        self.client.force_login(user)

    def _commande(self, **overrides):
        defaults = {
            "nom": "Alice", "email": "a@b.fr",
            "mode_livraison": Commande.LIVRAISON_DOMICILE,
            "adresse_postale": "1 rue X, 40000 Ville",
            "mode_paiement": Commande.PAIEMENT_CHEQUE,
            "montant_articles_cents": 4000, "frais_port_cents": 749,
            "montant_total_cents": 4749,
            "statut": Commande.STATUT_EN_ATTENTE_REGLEMENT,
        }
        defaults.update(overrides)
        commande = Commande.objects.create(**defaults)
        LigneCommande.objects.create(
            commande=commande, libelle="Livre", prix_unitaire_cents=2000, quantite=2,
        )
        return commande

    def test_liste_a_traiter_exclut_payees_et_archives(self):
        a_traiter = self._commande()
        payee = self._commande(statut=Commande.STATUT_PAYE)
        archivee = self._commande(archive=True)
        body = self.client.get(reverse("gestion:commandes_liste")).content.decode()
        self.assertIn(a_traiter.reference_commande, body)
        self.assertNotIn(payee.reference_commande, body)
        self.assertNotIn(archivee.reference_commande, body)

    def test_liste_payees(self):
        a_traiter = self._commande()
        payee = self._commande(statut=Commande.STATUT_PAYE)
        body = self.client.get(
            reverse("gestion:commandes_liste"), {"filtre": "payees"}
        ).content.decode()
        self.assertIn(payee.reference_commande, body)
        self.assertNotIn(a_traiter.reference_commande, body)

    def test_liste_archives(self):
        vivante = self._commande()
        archivee = self._commande(archive=True)
        body = self.client.get(
            reverse("gestion:commandes_liste"), {"filtre": "archives"}
        ).content.decode()
        self.assertIn(archivee.reference_commande, body)
        self.assertNotIn(vivante.reference_commande, body)

    def test_detail_marque_lu_au_get(self):
        commande = self._commande()
        self.assertFalse(commande.lu)
        self.client.get(reverse("gestion:commande_detail", args=[commande.pk]))
        commande.refresh_from_db()
        self.assertTrue(commande.lu)

    def test_marquer_paye(self):
        commande = self._commande()
        resp = self.client.post(
            reverse("gestion:commande_detail", args=[commande.pk]),
            {"action": "marquer_paye"},
        )
        self.assertEqual(resp.status_code, 302)
        commande.refresh_from_db()
        self.assertEqual(commande.statut, Commande.STATUT_PAYE)
        self.assertTrue(commande.paye)

    def test_archiver(self):
        commande = self._commande()
        resp = self.client.post(
            reverse("gestion:commande_detail", args=[commande.pk]),
            {"action": "archiver"},
        )
        self.assertEqual(resp.status_code, 302)
        commande.refresh_from_db()
        self.assertTrue(commande.archive)

    def test_unread_commandes_count_dans_le_contexte(self):
        self._commande()  # non lue, non archivée
        self._commande(lu=True)
        self._commande(archive=True)
        resp = self.client.get(reverse("gestion:commandes_liste"))
        self.assertEqual(resp.context["unread_commandes_count"], 1)
