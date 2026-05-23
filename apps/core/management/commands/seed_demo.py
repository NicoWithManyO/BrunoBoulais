"""Populate the database with placeholder content so all public pages display nicely.

Idempotent: safe to re-run, updates existing rows instead of duplicating them.
"""
from datetime import time, timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.actualites.models import Actualite
from apps.livre.models import LienAchat, Livre
from apps.parametres.models import Parametres
from apps.personnes.models import Personne
from apps.temoignages.models import Temoignage


class Command(BaseCommand):
    help = "Seed the database with placeholder content for the public site."

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Seeding demo content…"))

        livre = self._seed_livre()
        self._seed_liens_achat(livre)
        self._seed_personnes()
        self._seed_actualites()
        self._seed_temoignages()
        self._seed_parametres()

        self.stdout.write(self.style.SUCCESS("Done."))

    # --- Livre ---------------------------------------------------------

    def _seed_livre(self):
        livre, _ = Livre.objects.get_or_create(pk=1)
        livre.titre = "Jacques Bertin, le géant discret de la chanson"
        livre.sous_titre = "Un portrait, une œuvre, une fidélité"
        livre.pitch_court = (
            "Bruno Boulais consacre un livre à Jacques Bertin, poète et chanteur à l’œuvre "
            "monumentale, longtemps tenu à l’écart des projecteurs."
        )
        livre.pitch_long = (
            "<p>Il y a des œuvres qui se font sans bruit, et qui pourtant accompagnent "
            "des vies entières. Celle de <em>Jacques Bertin</em>, chanteur, poète, écrivain, "
            "est de celles-là&nbsp;: rétive aux modes, ancrée dans une langue précise, "
            "tournée vers l’essentiel.</p>"
            "<p>Bruno Boulais a entrepris d’en raconter le parcours, les choix, les silences. "
            "Ce livre n’est ni une hagiographie ni un essai universitaire&nbsp;: c’est le "
            "récit attentif d’une rencontre prolongée avec une œuvre rare, et une invitation "
            "à la découvrir à son tour.</p>"
            "<p>De Rennes aux scènes parisiennes, des disques discrets aux poèmes publiés, "
            "le livre suit le fil d’une fidélité — celle d’un homme à son art, et celle d’un "
            "auteur à son sujet.</p>"
        )
        livre.sommaire = (
            "<ul>"
            "<li>Préface — d’après Jean-Claude Guillebaud</li>"
            "<li>Première partie · Le jeune homme et les mots</li>"
            "<li>Deuxième partie · La scène, le disque, la fidélité</li>"
            "<li>Troisième partie · Écrire ailleurs, écrire encore</li>"
            "<li>Annexes · Discographie, bibliographie, repères chronologiques</li>"
            "</ul>"
        )
        livre.extrait = (
            "<p>« Ses chansons ne séduisent pas&nbsp;: elles touchent. Ses poèmes ne décorent "
            "pas&nbsp;: ils dévoilent. Et c’est peut-être pour cela qu’il a, depuis si "
            "longtemps, ce petit nombre de lecteurs et d’auditeurs qui ne le lâchent pas — "
            "comme on ne lâche pas un ami, comme on ne lâche pas une braise. »</p>"
        )
        livre.editeur = "Éditions du Petit Pavé"
        livre.pages = 232
        livre.prix_euros = 18
        livre.isbn = "978-2-84712-XXX-X"
        livre.save()
        return livre

    def _seed_liens_achat(self, livre):
        liens = [
            {
                "libelle": "Sur le site de l’éditeur",
                "url": "https://www.petitpave.fr",
                "description": "Commande directe aux Éditions du Petit Pavé.",
                "position": 10,
            },
            {
                "libelle": "Librairies indépendantes (placedeslibraires.fr)",
                "url": "https://www.placedeslibraires.fr",
                "description": "Soutenez votre librairie de quartier.",
                "position": 20,
            },
        ]
        for data in liens:
            LienAchat.objects.update_or_create(
                livre=livre,
                libelle=data["libelle"],
                defaults={
                    "url": data["url"],
                    "description": data["description"],
                    "position": data["position"],
                },
            )

    # --- Personnes -----------------------------------------------------

    def _seed_personnes(self):
        Personne.objects.update_or_create(
            role=Personne.ROLE_SUJET,
            defaults={
                "nom": "Jacques Bertin",
                "sous_titre": "Chanteur, poète, écrivain",
                "annee_naissance": 1946,
                "bio_courte": (
                    "Né à Rennes en 1946, Jacques Bertin a construit, en marge des modes, "
                    "une œuvre de chansons et de poèmes d’une exigence rare."
                ),
                "bio_longue": (
                    "<p>Né à Rennes en 1946, <em>Jacques Bertin</em> commence à écrire et à "
                    "chanter dans les années 1960. Son premier disque paraît en 1971&nbsp;; "
                    "suivront plus de vingt albums, des recueils de poèmes, des essais.</p>"
                    "<p>Reconnu par ses pairs (Léo Ferré, Jean Vasca, Allain Leprest), souvent "
                    "salué par la presse spécialisée, il a fait le choix d’une carrière sans "
                    "concession au système — ce qui en fait, paradoxalement, l’un des grands "
                    "discrets de la chanson française.</p>"
                    "<p>Aujourd’hui encore, il chante, écrit, et trace son chemin&nbsp;: "
                    "celui d’une fidélité à la langue, aux émotions vraies, à la dignité "
                    "des humbles.</p>"
                ),
            },
        )
        Personne.objects.update_or_create(
            role=Personne.ROLE_AUTEUR,
            defaults={
                "nom": "Bruno Boulais",
                "sous_titre": "Auteur · Misson (40)",
                "bio_courte": (
                    "Bruno Boulais vit dans les Landes. Lecteur passionné de la chanson de "
                    "texte, il a consacré plusieurs années à ce livre sur Jacques Bertin."
                ),
                "bio_longue": (
                    "<p><em>Bruno Boulais</em> est né et a grandi dans l’ouest de la France. "
                    "Installé près de Dax, il a longtemps exercé un métier sans rapport "
                    "avec l’écriture, tout en accumulant lectures, notes, écoutes attentives.</p>"
                    "<p>Le projet d’écrire sur Jacques Bertin est né d’une fidélité — celle "
                    "d’un auditeur de longue date qui voulait, à son tour, faire connaître "
                    "celui qu’il considère comme l’un des plus grands chanteurs-poètes de "
                    "notre époque.</p>"
                    "<p>« Jacques Bertin, le géant discret de la chanson » est son premier "
                    "livre publié aux Éditions du Petit Pavé.</p>"
                ),
            },
        )

    # --- Actualités ----------------------------------------------------

    def _seed_actualites(self):
        today = timezone.localdate()

        items = [
            {
                "titre": "Dédicace à l’Intermarché de Pouillon",
                "type": Actualite.TYPE_DEDICACE,
                "date_evenement": today + timedelta(days=14),
                "heure_debut": time(10, 0),
                "heure_fin": time(17, 0),
                "lieu": "Intermarché de Pouillon",
                "ville": "Pouillon (40)",
                "chapo": "Rencontre avec l’auteur, échanges autour du livre et signature des exemplaires.",
                "contenu": (
                    "<p>Bruno Boulais sera présent toute la journée à l’Intermarché de Pouillon "
                    "pour présenter son livre, échanger avec les lecteurs et dédicacer les "
                    "exemplaires achetés sur place.</p>"
                    "<p>Une belle occasion de prolonger la lecture par un dialogue, ou tout "
                    "simplement de découvrir l’univers de Jacques Bertin.</p>"
                ),
            },
            {
                "titre": "Soirée lecture à la créperie Ty Breizh",
                "type": Actualite.TYPE_DEDICACE,
                "date_evenement": today + timedelta(days=42),
                "heure_debut": time(19, 30),
                "lieu": "Créperie Ty Breizh",
                "ville": "Chalonnes-sur-Loire (49)",
                "chapo": "Lecture d’extraits suivie d’une discussion et d’un repas crêpes.",
                "contenu": (
                    "<p>Une soirée conviviale&nbsp;: Bruno lira quelques pages du livre, "
                    "présentera son travail et répondra aux questions du public, autour "
                    "d’un repas crêpes (sur réservation auprès de la créperie).</p>"
                ),
            },
            {
                "titre": "Dédicace à la créperie Ty Breizh — déjà passée",
                "type": Actualite.TYPE_DEDICACE,
                "date_evenement": today - timedelta(days=30),
                "lieu": "Créperie Ty Breizh",
                "ville": "Chalonnes-sur-Loire (49)",
                "chapo": "Une première rencontre chaleureuse autour du livre.",
                "contenu": (
                    "<p>Belle après-midi de dédicace, dans une ambiance amicale&nbsp;: "
                    "merci aux lecteurs venus échanger, et à la créperie pour son accueil.</p>"
                ),
            },
            {
                "titre": "Parution annoncée dans Le Petit Pavé",
                "type": Actualite.TYPE_PRESSE,
                "date_evenement": today - timedelta(days=90),
                "lieu": "",
                "ville": "",
                "chapo": "L’éditeur annonce la sortie du livre dans sa lettre d’information.",
                "contenu": (
                    "<p>Les Éditions du Petit Pavé ont consacré une page de leur lettre "
                    "à la parution du livre, mettant en avant la rigueur du travail "
                    "biographique et la qualité d’écriture.</p>"
                ),
            },
        ]
        for data in items:
            Actualite.objects.update_or_create(
                titre=data["titre"],
                defaults={
                    "statut": Actualite.STATUT_PUBLIE,
                    "type": data["type"],
                    "date_evenement": data["date_evenement"],
                    "heure_debut": data.get("heure_debut"),
                    "heure_fin": data.get("heure_fin"),
                    "lieu": data["lieu"],
                    "ville": data["ville"],
                    "chapo": data["chapo"],
                    "contenu": data["contenu"],
                },
            )

    # --- Témoignages ---------------------------------------------------

    def _seed_temoignages(self):
        items = [
            {
                "auteur": "Dominique Lefèvre",
                "source": "Lecteur, Angers",
                "texte": (
                    "J’ai dévoré ton bouquin&nbsp;! Un récit fluide, à la découverte de "
                    "Jacques Bertin dans son exigence de vérité et de sincérité."
                ),
                "mis_en_avant": True,
                "position": 10,
            },
            {
                "auteur": "Marie-Hélène C.",
                "source": "Lectrice, Rennes",
                "texte": (
                    "Un livre qui se lit comme une longue conversation. On y croise un "
                    "artiste rare, et on en ressort avec l’envie d’écouter ses disques "
                    "autrement."
                ),
                "mis_en_avant": True,
                "position": 20,
            },
            {
                "auteur": "Jean-Yves B.",
                "source": "Facebook",
                "texte": (
                    "Bravo Bruno. Tu rends justice à un grand monsieur de la chanson, "
                    "avec une plume juste et sans complaisance."
                ),
                "mis_en_avant": True,
                "position": 30,
            },
            {
                "auteur": "Anne et Jacques B.",
                "source": "Dédicace de Chalonnes",
                "texte": (
                    "Merci pour ce moment. On a aimé l’humilité de votre démarche et "
                    "la finesse de votre écriture."
                ),
                "mis_en_avant": False,
                "position": 40,
            },
        ]
        for data in items:
            Temoignage.objects.update_or_create(
                auteur=data["auteur"],
                texte=data["texte"],
                defaults={
                    "source": data["source"],
                    "statut": Temoignage.STATUT_PUBLIE,
                    "mis_en_avant": data["mis_en_avant"],
                    "position": data["position"],
                },
            )

    # --- Paramètres ----------------------------------------------------

    def _seed_parametres(self):
        Parametres.get_solo()
