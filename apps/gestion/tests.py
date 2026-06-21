import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.carnet.models import Billet, BilletImageContenu
from apps.contact.models import Message

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
            nb_exemplaires=2, mode_livraison=Message.LIVRAISON_DOMICILE,
            adresse_postale="1 rue X\n40000 Ville", mode_paiement=Message.PAIEMENT_CB,
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
        self.assertIn("Carte bancaire", body)

    def test_commande_relais_payee(self):
        order = Message.objects.create(
            nom="Bob", email="b@b.fr", sujet=Message.SUJET_COMMANDE,
            nb_exemplaires=1, mode_livraison=Message.LIVRAISON_POINT_RELAIS,
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
