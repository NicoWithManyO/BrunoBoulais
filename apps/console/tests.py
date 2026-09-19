"""Tests de la console web.

Le urlconf du projet ne branche la console que si elle est activée : les tests
passent donc par un urlconf dédié (``pytest.mark.urls``) pour pouvoir tester
les vues elles-mêmes, plus un test qui vérifie qu'avec les réglages par défaut
l'URL n'existe pas du tout.
"""

import base64
import json
import time

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client
from django.urls import include, path

from apps.console import client as console_client

# urlconf utilisé via @pytest.mark.urls("apps.console.tests")
urlpatterns = [path("console/", include("apps.console.urls"))]

PASSWORD = "mot-de-passe-de-test-123"
TOKEN = "jeton-de-test"

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def clear_cache():
    # Le rate-limit s'appuie sur LocMemCache global : isoler chaque test.
    cache.clear()
    yield
    cache.clear()


@pytest.fixture(autouse=True)
def disable_manifest_storage(settings):
    # Les context processors du projet appellent `static(...)` au rendu, ce qui
    # exige un manifest produit par `collectstatic` — pas voulu ici.
    settings.STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }


@pytest.fixture
def console_settings(settings, tmp_path):
    settings.CONSOLE_ENABLED = True
    settings.CONSOLE_TOKEN = TOKEN
    settings.CONSOLE_USERS = []
    settings.CONSOLE_RUNTIME_DIR = str(tmp_path / "console")
    settings.CONSOLE_CWD = str(tmp_path)
    settings.CONSOLE_IDLE_TIMEOUT = 60
    settings.CONSOLE_MAX_LIFETIME = 120
    return settings


@pytest.fixture
def superuser():
    return get_user_model().objects.create_superuser(
        username="nico", email="nico@example.test", password=PASSWORD
    )


@pytest.fixture
def staff():
    return get_user_model().objects.create_user(
        username="bruno", email="bruno@example.test", password=PASSWORD, is_staff=True
    )


def _login(user):
    http = Client()
    http.force_login(user)
    return http


def _unlock(http):
    return http.post("/console/", {"password": PASSWORD, "token": TOKEN})


# --- exposition -------------------------------------------------------------


def test_url_absente_par_defaut(client):
    """Réglages par défaut (console désactivée) : l'URL n'est même pas routée."""
    assert client.get("/console/").status_code == 404


@pytest.mark.urls("apps.console.tests")
def test_desactivee_404(settings, superuser):
    settings.CONSOLE_ENABLED = False
    settings.CONSOLE_TOKEN = TOKEN
    assert _login(superuser).get("/console/").status_code == 404


@pytest.mark.urls("apps.console.tests")
def test_sans_token_404(settings, superuser):
    """Activée mais sans secret posé : on refuse quand même de servir."""
    settings.CONSOLE_ENABLED = True
    settings.CONSOLE_TOKEN = ""
    assert _login(superuser).get("/console/").status_code == 404


@pytest.mark.urls("apps.console.tests")
def test_anonyme_redirige_vers_connexion(console_settings, client):
    response = client.get("/console/")
    assert response.status_code == 302
    assert "/gestion/connexion/" in response["Location"]


@pytest.mark.urls("apps.console.tests")
def test_staff_non_superuser_404(console_settings, staff):
    assert _login(staff).get("/console/").status_code == 404


@pytest.mark.urls("apps.console.tests")
def test_superuser_hors_allowlist_404(console_settings, superuser):
    console_settings.CONSOLE_USERS = ["quelquun-dautre"]
    assert _login(superuser).get("/console/").status_code == 404


# --- déverrouillage ---------------------------------------------------------


@pytest.mark.urls("apps.console.tests")
def test_superuser_voit_le_verrou(console_settings, superuser):
    response = _login(superuser).get("/console/")
    assert response.status_code == 200
    assert b"D\xc3\xa9verrouiller" in response.content
    assert response["Cache-Control"] == "no-store"


@pytest.mark.urls("apps.console.tests")
@pytest.mark.parametrize(
    "password,token",
    [(PASSWORD, "mauvais-jeton"), ("mauvais-mot-de-passe", TOKEN)],
)
def test_deverrouillage_refuse(console_settings, superuser, password, token):
    """Mot de passe ET jeton : l'un sans l'autre ne suffit pas."""
    http = _login(superuser)
    response = http.post("/console/", {"password": password, "token": token})
    assert response.status_code == 200
    assert b"invalide" in response.content
    # Toujours verrouillé : l'API refuse.
    assert http.post("/console/io/", "{}", content_type="application/json").status_code == 403


@pytest.mark.urls("apps.console.tests")
def test_deverrouillage_ok_affiche_le_terminal(console_settings, superuser):
    http = _login(superuser)
    assert _unlock(http).status_code == 302
    response = http.get("/console/")
    assert response.status_code == 200
    assert b"console-term" in response.content


@pytest.mark.urls("apps.console.tests")
def test_deverrouillage_expire(console_settings, superuser):
    http = _login(superuser)
    _unlock(http)
    console_settings.CONSOLE_UNLOCK_TTL = 0  # tout déverrouillage est périmé
    assert http.post("/console/io/", "{}", content_type="application/json").status_code == 403


@pytest.mark.urls("apps.console.tests")
def test_rate_limit_des_tentatives(console_settings, superuser):
    http = _login(superuser)
    for _ in range(12):
        response = http.post("/console/", {"password": "non", "token": "non"})
    assert response.status_code == 429
    assert response["Retry-After"]
    # Et le bon mot de passe ne passe plus non plus tant que ça dure.
    assert _unlock(http).status_code == 429


@pytest.mark.urls("apps.console.tests")
def test_api_verrouiller(console_settings, superuser):
    http = _login(superuser)
    _unlock(http)
    assert http.post("/console/lock/").status_code == 200
    assert http.post("/console/io/", "{}", content_type="application/json").status_code == 403


# --- shell réel -------------------------------------------------------------


def _io(http, **payload):
    response = http.post("/console/io/", json.dumps(payload), content_type="application/json")
    assert response.status_code == 200, response.content
    return response.json()


@pytest.mark.urls("apps.console.tests")
def test_shell_execute_une_commande(console_settings, superuser):
    """Bout en bout : ouverture du démon, frappe envoyée, sortie relue."""
    console_settings.CONSOLE_SHELL = "/bin/sh"
    http = _login(superuser)
    _unlock(http)

    first = _io(http, since=None, cols=80, rows=24)
    assert first["alive"] is True
    sid = first["sid"]

    _io(http, **{"in": base64.b64encode(b"echo bonjour-console\n").decode(), "since": False})

    seen = base64.b64decode(first["out"])
    since = first["seq"]
    deadline = time.time() + 15
    while seen.count(b"bonjour-console") < 2 and time.time() < deadline:
        payload = _io(http, since=since)
        seen += base64.b64decode(payload["out"])
        since = payload["seq"]
        time.sleep(0.1)

    # L'écho de la frappe ET le résultat de la commande sont présents : la
    # deuxième occurrence n'existe que si le shell a réellement tourné.
    assert seen.count(b"bonjour-console") >= 2, seen

    assert http.post("/console/close/").status_code == 200
    assert not console_client.alive(sid)


@pytest.mark.urls("apps.console.tests")
def test_session_perdue_renvoie_409(console_settings, superuser):
    """Démon disparu (serveur redémarré, session expirée) : 409, pas une 500."""
    http = _login(superuser)
    _unlock(http)
    session = http.session
    session["console_sid"] = console_client.new_sid()  # aucun démon derrière
    session.save()

    response = http.post(
        "/console/io/", json.dumps({"since": None}), content_type="application/json"
    )
    assert response.status_code == 409
    assert response.json()["error"] == "gone"


@pytest.mark.urls("apps.console.tests")
def test_entree_non_base64_rejetee(console_settings, superuser):
    console_settings.CONSOLE_SHELL = "/bin/sh"
    http = _login(superuser)
    _unlock(http)
    _io(http, since=None)
    response = http.post(
        "/console/io/",
        json.dumps({"in": "pas du base64 !!", "since": False}),
        content_type="application/json",
    )
    assert response.status_code == 400
    http.post("/console/close/")
