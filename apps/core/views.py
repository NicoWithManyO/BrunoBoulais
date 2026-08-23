from django.http import HttpResponse
from django.urls import reverse


def robots_txt(request):
    """Allow search engines on public routes, forbid the backoffice & uploads."""
    sitemap_url = request.build_absolute_uri(reverse("sitemap"))
    lines = [
        "User-agent: *",
        "Disallow: /admin/",
        "Disallow: /gestion/",
        "Disallow: /media/",
        "",
        f"Sitemap: {sitemap_url}",
        "",
    ]
    return HttpResponse("\n".join(lines), content_type="text/plain; charset=utf-8")
