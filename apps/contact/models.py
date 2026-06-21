from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import models

from apps.core.fields import RichTextField
from apps.core.models import TimestampedModel

CACHE_KEY_CONTACT_PAGE = "contact_page"

# Tarifs du livre. Prix unitaire fixe ; les frais de port dépendent du nombre
# d'exemplaires ET du mode de livraison (cf. FRAIS_PORT_CENTS, défini après
# Message pour réutiliser ses constantes LIVRAISON_*). Montants en centimes =
# source de vérité unique (pills, récap navigateur, page /merci/, email).
PRIX_LIVRE_CENTS = 2000

PRODUITS = {
    1: {"label": "1 exemplaire"},
    2: {"label": "2 exemplaires"},
}


def montant_euros(cents):
    """Formate un montant en centimes pour l'affichage FR : 2410 → "24,10 €"."""
    return f"{cents / 100:.2f}".replace(".", ",") + " €"


class ContactPage(TimestampedModel):
    """Singleton holding the editable header of /contact/ AND the post-submit /contact/merci/ page."""

    eyebrow = models.CharField("Surtitre", max_length=80, blank=True)
    titre = models.CharField("Titre", max_length=120, blank=True)
    intro = RichTextField("Texte d'introduction", blank=True)
    merci_eyebrow = models.CharField("Surtitre (page Merci)", max_length=80, blank=True)
    merci_titre = models.CharField("Titre (page Merci)", max_length=120, blank=True)
    merci_message = RichTextField("Message de remerciement", mode="inline", blank=True)

    class Meta:
        verbose_name = "Page /contact/"
        verbose_name_plural = "Page /contact/"

    def __str__(self):
        return "Page /contact/"

    def clean(self):
        if not self.pk and ContactPage.objects.exists():
            raise ValidationError("Un seul en-tête peut exister (singleton).")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
        cache.delete(CACHE_KEY_CONTACT_PAGE)

    @classmethod
    def get_solo(cls):
        obj = cache.get(CACHE_KEY_CONTACT_PAGE)
        if obj is None:
            obj, _ = cls.objects.get_or_create(pk=1)
            cache.set(CACHE_KEY_CONTACT_PAGE, obj, 300)
        return obj


class Message(TimestampedModel):
    """A message sent through the public contact form."""

    SUJET_COMMANDE = "commande"
    SUJET_QUESTION = "question"
    SUJET_PRESSE = "presse"
    SUJET_AUTRE = "autre"
    SUJET_CHOICES = [
        (SUJET_COMMANDE, "Commande"),
        (SUJET_QUESTION, "Question"),
        (SUJET_PRESSE, "Demande presse"),
        (SUJET_AUTRE, "Autre"),
    ]

    PAIEMENT_CHEQUE = "cheque"
    PAIEMENT_VIREMENT = "virement"
    PAIEMENT_CHOICES = [
        (PAIEMENT_CHEQUE, "Chèque"),
        (PAIEMENT_VIREMENT, "Virement"),
    ]

    LIVRAISON_POINT_RELAIS = "point_relais"
    LIVRAISON_DOMICILE = "domicile"
    LIVRAISON_CHOICES = [
        # Le widget Mondial Relay ne sait pas filtrer les lockers à part : relais
        # et casiers sortent ensemble sur la carte, d'où une seule option.
        (LIVRAISON_POINT_RELAIS, "Point Relais ou Locker"),
        (LIVRAISON_DOMICILE, "Domicile"),
    ]

    nom = models.CharField("Nom", max_length=120)
    email = models.EmailField("Email")
    telephone = models.CharField("Téléphone", max_length=30, blank=True)
    adresse_postale = models.TextField("Adresse postale", blank=True)
    sujet = models.CharField("Sujet", max_length=20, choices=SUJET_CHOICES, default=SUJET_COMMANDE)
    mode_paiement = models.CharField(
        "Mode de paiement", max_length=20, choices=PAIEMENT_CHOICES, blank=True
    )
    # null pour les sujets non-commande (question, presse, autre).
    nb_exemplaires = models.PositiveSmallIntegerField(
        "Nombre d'exemplaires",
        choices=[(n, p["label"]) for n, p in PRODUITS.items()],
        null=True,
        blank=True,
    )
    mode_livraison = models.CharField(
        "Mode de livraison", max_length=20, choices=LIVRAISON_CHOICES, blank=True
    )
    # Renseignés par le widget Mondial Relay (point relais ou locker) ;
    # le domicile utilise `adresse_postale` en texte libre.
    point_relais_id = models.CharField("ID point relais", max_length=20, blank=True)
    point_relais_libelle = models.CharField("Point relais choisi", max_length=255, blank=True)
    dedicace = models.BooleanField("Dédicace souhaitée", default=True)
    prenom_dedicace = models.CharField("Prénom pour la dédicace", max_length=100, blank=True)
    contenu = models.TextField("Message")
    lu = models.BooleanField("Lu", default=False)
    archive = models.BooleanField("Archivé", default=False)
    # False = la commande est enregistrée mais l'email de notification n'est pas
    # parti : à traiter manuellement (visible/filtrable dans l'admin).
    notified = models.BooleanField("Notifié", default=True)
    # Coché à la main par Bruno quand il reçoit le chèque ou le virement.
    paye = models.BooleanField("Payé", default=False)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Message"
        verbose_name_plural = "Messages"

    def __str__(self):
        return f"{self.nom} — {self.get_sujet_display()}"


# Frais de port en centimes selon (nb exemplaires, mode de livraison). Défini
# après Message pour réutiliser ses constantes LIVRAISON_*. Couvre exactement
# les combinaisons proposées (1 ou 2 ex, point relais ou domicile).
FRAIS_PORT_CENTS = {
    (1, Message.LIVRAISON_POINT_RELAIS): 415,
    (1, Message.LIVRAISON_DOMICILE): 749,
    (2, Message.LIVRAISON_POINT_RELAIS): 599,
    (2, Message.LIVRAISON_DOMICILE): 949,
}


def montant_total_cents(nb_exemplaires, mode_livraison):
    """Total commande en centimes : livres (20 € pièce) + frais de port.

    Retourne ``None`` si la combinaison (quantité, mode) n'a pas de tarif
    (donnée legacy/incohérente) : le caller décide quoi en faire.
    """
    port = FRAIS_PORT_CENTS.get((nb_exemplaires, mode_livraison))
    if port is None:
        return None
    return nb_exemplaires * PRIX_LIVRE_CENTS + port


def montant_detail(nb_exemplaires, mode_livraison):
    """Décomposition chiffrée d'une commande, déjà formatée FR pour l'affichage.

    Retourne ``None`` si la combinaison (quantité, mode) n'a pas de tarif (donnée
    legacy/incohérente) : on ne livre jamais une décomposition partielle. Sinon
    un dict ``{prix_livre, livres, port, total}`` de montants type « 24,15 € ».
    """
    total = montant_total_cents(nb_exemplaires, mode_livraison)
    if total is None:
        return None
    port = FRAIS_PORT_CENTS[(nb_exemplaires, mode_livraison)]
    return {
        "prix_livre": montant_euros(PRIX_LIVRE_CENTS),
        "livres": montant_euros(nb_exemplaires * PRIX_LIVRE_CENTS),
        "port": montant_euros(port),
        "total": montant_euros(total),
    }
