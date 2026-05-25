"""Common Django settings (shared by dev & prod)."""
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, []),
)
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY", default="dev-insecure-change-me")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")

SITE_ID = 1
# Domaine canonique utilisé par le framework `django.contrib.sites`
# (sitemap, allauth…). En prod : bruno.manyo.dev ; en dev : localhost:8000.
SITE_DOMAIN = env("SITE_DOMAIN", default="localhost:8000")
SITE_NAME = env("SITE_NAME", default="Bruno Boulais")

# --- Applications ---------------------------------------------------------

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    "django.contrib.sitemaps",
    "django.contrib.humanize",
]

THIRD_PARTY_APPS = [
    "tailwind",
    "crispy_forms",
    "crispy_tailwind",
    "honeypot",
    "taggit",
    "imagekit",
    "anymail",
    "allauth",
    "allauth.account",
]

LOCAL_APPS = [
    "apps.core",
    "apps.pages",
    "apps.livre",
    "apps.personnes",
    "apps.actualites",
    "apps.carnet",
    "apps.temoignages",
    "apps.galerie",
    "apps.contact",
    "apps.parametres",
    "apps.gestion",
]

# theme app (tailwind) — ajoutée après `tailwind init`
try:
    import theme  # noqa: F401
    LOCAL_APPS.append("theme")
    INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS
except ImportError:
    pass

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

TAILWIND_APP_NAME = "theme"
INTERNAL_IPS = ["127.0.0.1"]

# --- Middleware ----------------------------------------------------------

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "csp.middleware.CSPMiddleware",
    "apps.core.middleware.VisiteurCompteurMiddleware",
]

ROOT_URLCONF = "brunoboulais.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.site_context",
                "apps.gestion.context_processors.gestion_context",
            ],
        },
    },
]

WSGI_APPLICATION = "brunoboulais.wsgi.application"

# --- Database (SQLite) ---------------------------------------------------

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": env("SQLITE_PATH", default=str(BASE_DIR / "db.sqlite3")),
        "OPTIONS": {
            "init_command": (
                "PRAGMA journal_mode=WAL;"
                "PRAGMA synchronous=NORMAL;"
                "PRAGMA foreign_keys=ON;"
            ),
            "transaction_mode": "IMMEDIATE",
        },
    }
}

# --- Auth ----------------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

LOGIN_URL = "/gestion/connexion/"
LOGIN_REDIRECT_URL = "/gestion/"
LOGOUT_REDIRECT_URL = "/"

ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
ACCOUNT_EMAIL_VERIFICATION = "optional"
ACCOUNT_ADAPTER = "apps.core.adapters.NoSignupAccountAdapter"

# --- I18N / TZ -----------------------------------------------------------

LANGUAGE_CODE = "fr-fr"
TIME_ZONE = "Europe/Paris"
USE_I18N = True
USE_TZ = True

# --- Static & media ------------------------------------------------------

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATICFILES_FINDERS = [
    "django.contrib.staticfiles.finders.FileSystemFinder",
    "django.contrib.staticfiles.finders.AppDirectoriesFinder",
]

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# Upload memory thresholds — seuils mémoire/disque Django, PAS un cap
# global d'upload. ``DATA_UPLOAD_MAX_MEMORY_SIZE`` ne s'applique qu'aux
# field parts d'une requête multipart (champs non-file) ; les file parts
# en sont exempts (cf django/http/multipartparser.py). Le cap dur côté
# wire doit venir du reverse proxy en prod (nginx ``client_max_body_size``
# / Caddy ``request_body { max_size }``) — voir « Ops à appliquer côté
# Bruno » dans le plan sécu.
#
# Caps par-fichier enforced côté champ via validators :
#   - ``validate_image_size`` (apps/core/validators.py) : champs image-only
#     (livre, actualités, pages, personnes).
#   - ``validate_media_size`` : ``Media.fichier`` de la galerie, 8 Mo image
#     / 50 Mo vidéo selon l'extension.
FILE_UPLOAD_MAX_MEMORY_SIZE = 8 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Forms ---------------------------------------------------------------

CRISPY_ALLOWED_TEMPLATE_PACKS = "tailwind"
CRISPY_TEMPLATE_PACK = "tailwind"

# --- Sécurité (durci en prod) -------------------------------------------

X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"

# CSP — relâché ici, prod resserre
CONTENT_SECURITY_POLICY = {
    "DIRECTIVES": {
        "default-src": ("'self'",),
        "script-src": ("'self'", "'unsafe-inline'"),
        "style-src": ("'self'", "'unsafe-inline'"),
        "font-src": ("'self'",),
        "img-src": ("'self'", "data:", "blob:"),
        "media-src": ("'self'",),
        "frame-ancestors": ("'none'",),
    }
}

# --- Mail ----------------------------------------------------------------

DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="boulaisbruno@free.fr")
CONTACT_EMAIL = env("CONTACT_EMAIL", default="boulaisbruno@free.fr")

# --- Logging -------------------------------------------------------------

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "concise": {"format": "{levelname} {name}: {message}", "style": "{"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "concise",
        },
    },
    "root": {"handlers": ["console"], "level": "WARNING"},
    "loggers": {
        "django": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "apps": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}
