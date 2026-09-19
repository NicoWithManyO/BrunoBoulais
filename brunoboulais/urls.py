from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import include, path

from apps.core.sitemaps import sitemaps
from apps.core.views import robots_txt

urlpatterns = [
    path("admin/", admin.site.urls),
    path("gestion/", include("apps.gestion.urls")),
    path("contact/", include("apps.contact.urls")),
    path("actualites/", include("apps.actualites.urls")),
    path("temoignages/", include("apps.temoignages.urls")),
    path("galerie/", include("apps.galerie.urls")),
    path("discotheque/", include("apps.discotheque.urls")),
    path("boutique/", include("apps.boutique.urls")),
    path("sitemap.xml", sitemap, {"sitemaps": sitemaps}, name="sitemap"),
    path("robots.txt", robots_txt, name="robots"),
    path("", include("apps.pages.urls")),
]

# Console shell (HTTPS) — branchée seulement si explicitement activée ET
# configurée : sur une install qui ne pose pas CONSOLE_ENABLED/CONSOLE_TOKEN,
# l'URL n'existe pas du tout, même en 404 « authentifiée ».
if settings.CONSOLE_ENABLED and settings.CONSOLE_TOKEN:
    urlpatterns.insert(0, path(settings.CONSOLE_URL_PATH, include("apps.console.urls")))

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += [path("__reload__/", include("django_browser_reload.urls"))]
