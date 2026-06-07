"""Sitemap definitions for /sitemap.xml.

The home page gets a higher priority; the livre / personnes / dédicaces
pages come next; the auxiliary pages (témoignages, contact,
mentions) trail behind.
"""
from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from apps.actualites.models import Actualite


class StaticPagesSitemap(Sitemap):
    protocol = "https"
    changefreq = "monthly"

    def items(self):
        return [
            ("pages:home", 1.0),
            ("pages:livre", 0.9),
            ("pages:bertin", 0.8),
            ("pages:auteur", 0.7),
            ("actualites:liste", 0.7),
            ("temoignages:liste", 0.5),
            ("contact:form", 0.5),
            ("pages:mentions", 0.1),
        ]

    def location(self, item):
        return reverse(item[0])

    def priority(self, item):
        return item[1]


class ActualiteSitemap(Sitemap):
    protocol = "https"
    changefreq = "monthly"
    priority = 0.6

    def items(self):
        return Actualite.objects.filter(statut=Actualite.STATUT_PUBLIE).order_by("-date_publication")

    def lastmod(self, obj):
        return obj.updated_at


sitemaps = {
    "pages": StaticPagesSitemap,
    "actualites": ActualiteSitemap,
}
