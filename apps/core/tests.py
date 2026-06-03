from types import SimpleNamespace

from django.test import RequestFactory

from apps.core.middleware import _client_ip
from apps.core.templatetags.richtext import richtext, richtext_images


def _img(position, url, alt="", legende=""):
    # Stub minimal : le filtre ne lit que position, image.url, alt, legende.
    return SimpleNamespace(position=position, image=SimpleNamespace(url=url), alt=alt, legende=legende)


class TestRichtextImages:
    """Filtre `richtext_images` : remplacement des repères `[image:N]` par une
    figure cliquable, en réutilisant l'« Ordre »/`position` des images contenu."""

    def test_standalone_marker_absorbs_wrapping_p(self):
        # Un repère seul dans son <p> : le <p> est absorbé (la <figure>, élément
        # bloc, ne doit pas finir imbriquée dans un <p>).
        out = richtext_images("<p>[image:1]</p>", [_img(1, "/media/a.jpg", alt="Photo")])
        assert "<figure class=\"news-img\">" in out
        assert "<p>" not in out
        assert out.startswith("<figure")

    def test_inline_marker_kept_in_place(self):
        # Repère au milieu d'un paragraphe : remplacé sur place, <p> conservé.
        out = richtext_images("<p>Avant [image:1] apres</p>", [_img(1, "/media/a.jpg")])
        assert out.startswith("<p>Avant <figure")
        assert "apres</p>" in out

    def test_unknown_marker_left_as_is(self):
        # Pas d'image à cette position : repère laissé tel quel.
        out = richtext_images("<p>[image:9]</p>", [_img(1, "/media/a.jpg")])
        assert "[image:9]" in out
        assert "<figure" not in out

    def test_empty_value_returns_empty_string(self):
        assert richtext_images("", [_img(1, "/media/a.jpg")]) == ""
        assert richtext_images(None, []) == ""

    def test_alt_and_url_are_html_escaped(self):
        # alt et url passent par escape : pas d'injection via guillemet/chevron.
        img = _img(1, '/media/a&b".jpg', alt='Méchant"<script>')
        out = richtext_images("<p>[image:1]</p>", [img])
        assert "/media/a&amp;b&quot;.jpg" in out
        assert "&quot;&lt;script&gt;" in out
        assert "<script>" not in out

    def test_alt_falls_back_to_legend_plain_text(self):
        # alt vide → on retombe sur la légende en texte brut (balises retirées).
        img = _img(1, "/media/a.jpg", alt="", legende="<strong>Une</strong> légende")
        out = richtext_images("<p>[image:1]</p>", [img])
        assert 'alt="Une légende"' in out

    def test_legend_rendered_as_inline_richtext_in_figcaption(self):
        # La légende garde son balisage inline (<strong>) dans le <figcaption>.
        img = _img(1, "/media/a.jpg", legende="<strong>Gras</strong>")
        out = richtext_images("<p>[image:1]</p>", [img])
        assert "<figcaption><strong>Gras</strong></figcaption>" in out

    def test_no_legend_omits_figcaption(self):
        out = richtext_images("<p>[image:1]</p>", [_img(1, "/media/a.jpg")])
        assert "<figcaption>" not in out

    def test_consecutive_markers_form_a_row(self):
        # Deux repères collés dans le même <p> : rangée côte à côte, <p> absorbé.
        out = richtext_images(
            "<p>[image:1][image:2]</p>",
            [_img(1, "/media/a.jpg"), _img(2, "/media/b.jpg")],
        )
        assert '<div class="news-img-row">' in out
        assert out.count("<figure") == 2
        assert "<p>" not in out
        assert "/media/a.jpg" in out and "/media/b.jpg" in out

    def test_consecutive_markers_tolerate_whitespace(self):
        # Espaces entre les repères : toujours une rangée.
        out = richtext_images(
            "<p>[image:1]  [image:2]</p>",
            [_img(1, "/media/a.jpg"), _img(2, "/media/b.jpg")],
        )
        assert '<div class="news-img-row">' in out
        assert out.count("<figure") == 2

    def test_single_marker_paragraph_not_wrapped_in_row(self):
        # Un seul repère : pas de rangée, juste la figure (comportement inchangé).
        out = richtext_images("<p>[image:1]</p>", [_img(1, "/media/a.jpg")])
        assert "news-img-row" not in out
        assert out.startswith("<figure")

    def test_marker_literal_in_legend_is_not_re_substituted(self):
        # Un [image:N] écrit dans une légende ne doit pas être ré-interprété en
        # figure (sinon HTML corrompu) : une seule passe, pas de re-balayage.
        out = richtext_images(
            "<p>[image:1][image:2]</p>",
            [_img(1, "/media/a.jpg", legende="comparer avec [image:1]"),
             _img(2, "/media/b.jpg")],
        )
        assert out.count("<figure") == 2
        assert "<figcaption>comparer avec [image:1]</figcaption>" in out

    def test_sans_habillage_adds_noflow_class_on_side_aligned_image(self):
        # Case « pas de texte à côté » cochée + alignement latéral : on coupe le
        # float via la classe news-img--noflow, la largeur (w50) est conservée.
        img = SimpleNamespace(
            position=1, image=SimpleNamespace(url="/media/a.jpg"), alt="", legende="",
            largeur="50", alignement="left", sans_habillage=True,
        )
        out = richtext_images("<p>[image:1]</p>", [img])
        assert "news-img--noflow" in out
        assert "news-img--left" in out
        assert "news-img--w50" in out

    def test_sans_habillage_ignored_when_centered(self):
        # Centré : pas de float à couper, la classe noflow n'a pas lieu d'être.
        img = SimpleNamespace(
            position=1, image=SimpleNamespace(url="/media/a.jpg"), alt="", legende="",
            largeur="100", alignement="center", sans_habillage=True,
        )
        out = richtext_images("<p>[image:1]</p>", [img])
        assert "news-img--noflow" not in out


class TestRichtextBoldItalic:
    """L'éditeur émet <b>/<i> (sortie native de execCommand bold/italic) ;
    le rendu doit les conserver, pas seulement <strong>/<em>."""

    def test_block_keeps_b_and_i(self):
        out = richtext("<p><b>gras</b> et <i>italique</i></p>")
        assert "<b>gras</b>" in out
        assert "<i>italique</i>" in out

    def test_inline_keeps_b_and_i(self):
        out = richtext("<b>gras</b> <i>it</i>", mode="inline")
        assert "<b>gras</b>" in out
        assert "<i>it</i>" in out


class TestClientIp:
    """Vérifie la résolution d'IP client sous les différentes archis de bind.

    Régression de référence : commit f2ccab8 + déploiement socket unix → tous
    les visiteurs collapsent sur ip="" donc /contact/ fail-closed 503 et le
    compteur ne s'incrémente plus. Le fix (option α de to-dev.md) considère
    REMOTE_ADDR vide comme implicitement trusté (le socket unix n'est joignable
    que depuis nginx local, sur le même host).
    """

    def setup_method(self):
        self.rf = RequestFactory()

    def test_socket_unix_reads_cf_connecting_ip(self):
        # gunicorn bindé sur socket unix : REMOTE_ADDR vide. nginx local
        # pose CF-Connecting-IP (et strip celui qui rentre côté public).
        request = self.rf.get("/", REMOTE_ADDR="", HTTP_CF_CONNECTING_IP="1.2.3.4")
        assert _client_ip(request) == "1.2.3.4"

    def test_tcp_loopback_reads_cf_connecting_ip(self):
        # gunicorn bindé sur TCP loopback : REMOTE_ADDR == 127.0.0.1, trusté
        # par _TRUSTED_PROXY_NETWORKS, on lit CF-Connecting-IP.
        request = self.rf.get("/", REMOTE_ADDR="127.0.0.1", HTTP_CF_CONNECTING_IP="1.2.3.4")
        assert _client_ip(request) == "1.2.3.4"

    def test_untrusted_remote_addr_ignores_cf_header(self):
        # REMOTE_ADDR == IP publique (cas anormal, gunicorn bindé public sans
        # proxy) : on n'a pas le droit de trust CF-Connecting-IP, sinon
        # spoof trivial. On retourne REMOTE_ADDR tel quel.
        request = self.rf.get("/", REMOTE_ADDR="8.8.8.8", HTTP_CF_CONNECTING_IP="1.2.3.4")
        assert _client_ip(request) == "8.8.8.8"

    def test_socket_unix_without_cf_header_returns_empty(self):
        # Socket unix mais CF-Connecting-IP absent (header strippé en amont
        # ou requête non-CF) : on retourne "" pour que les callers fail-closed
        # plutôt que de bucket tout le monde ensemble.
        request = self.rf.get("/", REMOTE_ADDR="")
        assert _client_ip(request) == ""

    def test_garbage_remote_addr_does_not_trust_cf_header(self):
        # REMOTE_ADDR non-vide mais non parseable par `ipaddress.ip_address` :
        # _normalize_ip retourne "" via swallow ValueError. Le trust DOIT être
        # gaté sur la valeur RAW, pas la normalisée — sinon n'importe quel
        # garbage hérite du trust socket unix et permet de spoof CF-Connecting-IP.
        request = self.rf.get("/", REMOTE_ADDR="not-an-ip", HTTP_CF_CONNECTING_IP="1.2.3.4")
        assert _client_ip(request) == ""

    def test_whitespace_remote_addr_does_not_trust_cf_header(self):
        # REMOTE_ADDR avec whitespace parasite : `ipaddress.ip_address` ne strip
        # pas et lève ValueError. Même contrat que garbage — pas de trust.
        request = self.rf.get("/", REMOTE_ADDR=" 127.0.0.1", HTTP_CF_CONNECTING_IP="1.2.3.4")
        assert _client_ip(request) == ""
