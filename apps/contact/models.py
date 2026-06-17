from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import models

from apps.core.fields import RichTextField
from apps.core.models import TimestampedModel

CACHE_KEY_CONTACT_PAGE = "contact_page"

# Tarifs dégressifs du livre. Montants en centimes = source de vérité unique
# (formulaire, page /merci/, line items Stripe, email de notification).
PRODUITS = {
    1: {"label": "1 exemplaire", "montant_cents": 2410},
    2: {"label": "2 exemplaires", "montant_cents": 4599},
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

    PAIEMENT_CB = "cb"
    PAIEMENT_CHEQUE = "cheque"
    PAIEMENT_VIREMENT = "virement"
    PAIEMENT_CHOICES = [
        (PAIEMENT_CB, "Carte bancaire"),
        (PAIEMENT_CHEQUE, "Chèque"),
        (PAIEMENT_VIREMENT, "Virement"),
    ]

    LIVRAISON_POINT_RELAIS = "point_relais"
    LIVRAISON_LOCKER = "locker"
    LIVRAISON_DOMICILE = "domicile"
    LIVRAISON_CHOICES = [
        (LIVRAISON_POINT_RELAIS, "Point Relais"),
        (LIVRAISON_LOCKER, "Locker (casier)"),
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
        choices=[
            (n, f"{n} exemplaire{'s' if n > 1 else ''} — {montant_euros(p['montant_cents'])}")
            for n, p in PRODUITS.items()
        ],
        null=True,
        blank=True,
    )
    mode_livraison = models.CharField(
        "Mode de livraison", max_length=20, choices=LIVRAISON_CHOICES, blank=True
    )
    # Renseignés par le widget Mondial Relay (point relais / locker uniquement) ;
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
    # Posé par le webhook Stripe (CB) ou coché à la main par Bruno (chèque/virement).
    paye = models.BooleanField("Payé", default=False)
    stripe_session_id = models.CharField("Session Stripe", max_length=255, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Message"
        verbose_name_plural = "Messages"

    def __str__(self):
        return f"{self.nom} — {self.get_sujet_display()}"
