"""Filename-sanitizing upload_to callables.

Each callable slugifies the original stem and appends a short UUID to avoid
collisions and prevent leaking client-side filenames. Defined as module-level
functions so Django migrations can serialize them by import path.
"""
import uuid
from pathlib import Path

from django.utils.text import slugify


def _slugged(prefix, filename):
    stem = Path(filename).stem
    ext = Path(filename).suffix.lower().lstrip(".") or "bin"
    slug = slugify(stem)[:60] or "file"
    return f"{prefix}/{slug}-{uuid.uuid4().hex[:8]}.{ext}"


def accueil_upload_to(instance, filename):
    return _slugged("accueil", filename)


def accueil_image_upload_to(instance, filename):
    return _slugged("accueil/images", filename)


def og_upload_to(instance, filename):
    return _slugged("og", filename)


def livre_upload_to(instance, filename):
    return _slugged("livre", filename)


def livre_image_upload_to(instance, filename):
    return _slugged("livre/images", filename)


def actualites_upload_to(instance, filename):
    return _slugged("actualites", filename)


def actualites_image_upload_to(instance, filename):
    return _slugged("actualites/images", filename)


def actualites_contenu_upload_to(instance, filename):
    return _slugged("actualites/contenu", filename)


def portraits_upload_to(instance, filename):
    return _slugged("portraits", filename)


def portraits_image_upload_to(instance, filename):
    return _slugged("portraits/images", filename)


def galerie_upload_to(instance, filename):
    return _slugged("galerie", filename)


def discotheque_upload_to(instance, filename):
    return _slugged("discotheque", filename)
