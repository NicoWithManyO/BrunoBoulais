from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import models

from apps.core.fields import RichTextField
from apps.core.models import TimestampedModel

CACHE_KEY_CONTACT_PAGE = "contact_page"

# Catalogue et tarifs. Montants en centimes = source de vérité unique (pills,
# récap navigateur, page /contact/merci/, email). Le livre et chaque volume CD
# sont vendus à l'unité (PRIX_UNITE_CENTS) ; l'intégrale et le pack ont un prix
# fixe (PRIX_OFFRE_CENTS, le pack incluant déjà la remise de 5 €). Les frais de
# port dépendent de l'offre/quantité ET du mode de livraison (cf.
# FRAIS_PORT_CENTS, défini après Message pour réutiliser ses constantes LIVRAISON_*).
PRIX_UNITE_CENTS = 2000  # livre OU volume à l'unité : 20 €

PRODUIT_LIVRE = "livre"
PRODUIT_VOLUMES = "volumes"
PRODUIT_INTEGRALE = "integrale"
PRODUIT_PACK = "pack"
PRODUIT_CHOICES = [
    (PRODUIT_LIVRE, "Le livre"),
    (PRODUIT_VOLUMES, "Volume(s) à l'unité"),
    (PRODUIT_INTEGRALE, "Intégrale (3 volumes — 15 CD)"),
    (PRODUIT_PACK, "Pack Intégrale + Livre"),
]
PRIX_OFFRE_CENTS = {PRODUIT_INTEGRALE: 6000, PRODUIT_PACK: 7500}

# Quantité d'exemplaires du livre (offre « Le livre »).
EXEMPLAIRES_CHOICES = [(1, "1 exemplaire"), (2, "2 exemplaires")]
# Volumes de l'intégrale achetables à l'unité (1 ou 2 ; 3 = intégrale).
VOLUMES_CHOICES = [(1, "Volume 1"), (2, "Volume 2"), (3, "Volume 3")]


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
    sujet = models.CharField("Sujet", max_length=20, choices=SUJET_CHOICES)
    mode_paiement = models.CharField(
        "Mode de paiement", max_length=20, choices=PAIEMENT_CHOICES, blank=True
    )
    # Offre commandée (livre, volumes à l'unité, intégrale, pack). Vide hors
    # commande.
    produit = models.CharField("Offre", max_length=20, choices=PRODUIT_CHOICES, blank=True)
    # null pour les sujets non-commande (question, presse, autre). Ne concerne
    # que l'offre « Le livre ».
    nb_exemplaires = models.PositiveSmallIntegerField(
        "Nombre d'exemplaires",
        choices=EXEMPLAIRES_CHOICES,
        null=True,
        blank=True,
    )
    # Volumes choisis pour l'offre « Volume(s) à l'unité » : CSV des numéros,
    # ex. "1,3". Vide pour les autres offres.
    volumes = models.CharField("Volumes choisis", max_length=20, blank=True)
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

    def get_volumes_display(self):
        """Libellés des volumes choisis : "1,3" → "Volume 1, Volume 3"."""
        noms = dict(VOLUMES_CHOICES)
        # `isdigit` plutôt que `if v` : un token non numérique en base (donnée
        # corrompue / éditée à la main) ferait planter `int(v)` sinon.
        return ", ".join(noms.get(int(v), v) for v in self.volumes.split(",") if v.isdigit())


# Frais de port en centimes selon (variante, mode de livraison). La variante est
# l'offre quantifiée pour le livre/les volumes (ex. "livre_2", "volumes_1"),
# sinon l'offre seule. Défini après Message pour réutiliser ses constantes
# LIVRAISON_*.
FRAIS_PORT_CENTS = {
    (f"{PRODUIT_LIVRE}_1", Message.LIVRAISON_POINT_RELAIS): 415,
    (f"{PRODUIT_LIVRE}_1", Message.LIVRAISON_DOMICILE): 749,
    (f"{PRODUIT_LIVRE}_2", Message.LIVRAISON_POINT_RELAIS): 599,
    (f"{PRODUIT_LIVRE}_2", Message.LIVRAISON_DOMICILE): 949,
    (f"{PRODUIT_VOLUMES}_1", Message.LIVRAISON_POINT_RELAIS): 415,
    (f"{PRODUIT_VOLUMES}_1", Message.LIVRAISON_DOMICILE): 749,
    (f"{PRODUIT_VOLUMES}_2", Message.LIVRAISON_POINT_RELAIS): 415,
    (f"{PRODUIT_VOLUMES}_2", Message.LIVRAISON_DOMICILE): 749,
    (PRODUIT_INTEGRALE, Message.LIVRAISON_POINT_RELAIS): 415,
    (PRODUIT_INTEGRALE, Message.LIVRAISON_DOMICILE): 749,
    (PRODUIT_PACK, Message.LIVRAISON_POINT_RELAIS): 599,
    (PRODUIT_PACK, Message.LIVRAISON_DOMICILE): 949,
}


def _variante_port(produit, quantite):
    """Clé de frais de port : offre quantifiée (livre/volumes) ou offre seule."""
    if produit in (PRODUIT_LIVRE, PRODUIT_VOLUMES):
        return f"{produit}_{quantite}"
    return produit


def quantite_articles(produit, nb_exemplaires, volumes):
    """Quantité facturée : exemplaires (livre), nombre de volumes, sinon None.

    ``volumes`` est le CSV stocké sur Message (ex. "1,3"). L'intégrale et le pack
    sont des offres uniques : pas de quantité (None).
    """
    if produit == PRODUIT_LIVRE:
        return nb_exemplaires
    if produit == PRODUIT_VOLUMES:
        return len([v for v in (volumes or "").split(",") if v])
    return None


def montant_articles_cents(produit, quantite):
    """Prix des articles (hors port) en centimes, ou ``None`` si indéterminable.

    Livre et volumes : prix unitaire × quantité. Intégrale et pack : prix fixe.
    """
    if produit in (PRODUIT_LIVRE, PRODUIT_VOLUMES):
        return quantite * PRIX_UNITE_CENTS if quantite else None
    return PRIX_OFFRE_CENTS.get(produit)


def montant_total_cents(produit, quantite, mode_livraison):
    """Total commande en centimes : articles + frais de port.

    Retourne ``None`` si le prix des articles OU le port est inconnu (offre
    incomplète, ou tarif domicile CD pas encore renseigné) : le caller décide.
    """
    articles = montant_articles_cents(produit, quantite)
    port = FRAIS_PORT_CENTS.get((_variante_port(produit, quantite), mode_livraison))
    if articles is None or port is None:
        return None
    return articles + port


def montant_detail(produit, quantite, mode_livraison):
    """Décomposition chiffrée d'une commande, déjà formatée FR pour l'affichage.

    Retourne ``None`` si le prix des articles est inconnu (offre/quantité
    absente) : rien à afficher. Si les articles sont connus mais le port absent
    de la grille (combinaison non tarifée), renvoie ``port="à confirmer"`` et
    ``total=""`` plutôt que d'inventer un montant.
    Sinon un dict ``{articles, port, total}`` de montants type « 24,15 € ».
    """
    articles = montant_articles_cents(produit, quantite)
    if articles is None:
        return None
    port = FRAIS_PORT_CENTS.get((_variante_port(produit, quantite), mode_livraison))
    if port is None:
        return {"articles": montant_euros(articles), "port": "à confirmer", "total": ""}
    return {
        "articles": montant_euros(articles),
        "port": montant_euros(port),
        "total": montant_euros(articles + port),
    }
