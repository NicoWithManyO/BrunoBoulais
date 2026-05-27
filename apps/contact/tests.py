import pytest
from django.core.cache import cache
from django.test import Client


@pytest.fixture(autouse=True)
def clear_cache():
    # Le rate-limit et le dédup log s'appuient sur LocMemCache global :
    # nettoyer avant/après pour ne pas polluer un autre test.
    cache.clear()
    yield
    cache.clear()


@pytest.fixture(autouse=True)
def disable_manifest_storage(settings):
    # Le rendu du template de /contact/ appelle `static(...)` côté context
    # processor, ce qui exige un `manifest.json` produit par `collectstatic` —
    # pas voulu en suite de tests.
    settings.STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }


@pytest.mark.django_db
class TestContactIpUnresolved:
    """Régression check sur le fail-closed introduit par f2ccab8.

    Quand `_client_ip` retourne "" (IP indéterminée), la vue doit retourner
    503 + Cache-Control: no-store — pas 200, pas 302, pas un succès silencieux
    qui aurait permis à l'attaquant de bypasser le rate-limit par IP.
    """

    def test_post_with_unresolved_ip_returns_503(self):
        client = Client()
        response = client.post(
            "/contact/",
            data={
                "nom": "Alice",
                "sujet": "question",
                "email": "alice@example.com",
                "telephone": "",
                "adresse_postale": "",
                "contenu": "Bonjour Bruno, juste une question.",
                "website": "",
            },
            REMOTE_ADDR="",
        )
        assert response.status_code == 503
        assert response["Cache-Control"] == "no-store"
