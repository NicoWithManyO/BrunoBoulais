"""Test settings — dev, sans les artefacts de build dont la suite ne doit pas dépendre."""
from .dev import *  # noqa: F401,F403

# Django force DEBUG=False pendant les tests, ce qui réactive le lookup du
# manifest whitenoise hérité de base.py. Celui-ci exige un `collectstatic`
# préalable — artefact gitignoré, donc absent d'un clone frais ou d'une CI :
# tout `{% static %}` d'un asset non encore collecté ferait planter le rendu.
# Le storage simple rend la suite indépendante du build.
STORAGES = {
    **STORAGES,  # noqa: F405
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}
