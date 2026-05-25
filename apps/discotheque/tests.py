from unittest.mock import patch
from urllib.error import URLError

import pytest

from apps.discotheque.models import Chanson, extract_youtube_id
from apps.discotheque.youtube import download_thumbnail, fetch_oembed


class TestExtractYoutubeId:
    """Vérifie l'extraction de l'ID vidéo depuis les formats d'URL YT courants."""

    def test_watch_url(self):
        assert extract_youtube_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_watch_url_no_www(self):
        assert extract_youtube_id("https://youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_short_url(self):
        assert extract_youtube_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_embed_url(self):
        assert extract_youtube_id("https://www.youtube.com/embed/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_shorts_url(self):
        assert extract_youtube_id("https://www.youtube.com/shorts/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_watch_url_with_timestamp(self):
        assert (
            extract_youtube_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=42s")
            == "dQw4w9WgXcQ"
        )

    def test_short_url_with_timestamp(self):
        assert extract_youtube_id("https://youtu.be/dQw4w9WgXcQ?t=42") == "dQw4w9WgXcQ"

    def test_id_with_underscore_and_dash(self):
        assert extract_youtube_id("https://youtu.be/abc_DEF-123") == "abc_DEF-123"

    def test_invalid_url_returns_none(self):
        assert extract_youtube_id("https://example.com/foo") is None

    def test_empty_string_returns_none(self):
        assert extract_youtube_id("") is None

    def test_none_returns_none(self):
        assert extract_youtube_id(None) is None


@pytest.mark.django_db
class TestChansonModel:
    def test_str_uses_titre_when_present(self):
        chanson = Chanson.objects.create(
            titre="La balade du désir",
            url_youtube="https://youtu.be/dQw4w9WgXcQ",
        )
        assert str(chanson) == "La balade du désir"

    def test_str_falls_back_to_url_when_no_titre(self):
        chanson = Chanson.objects.create(url_youtube="https://youtu.be/dQw4w9WgXcQ")
        assert str(chanson) == "https://youtu.be/dQw4w9WgXcQ"

    def test_youtube_id_property(self):
        chanson = Chanson.objects.create(
            url_youtube="https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        )
        assert chanson.youtube_id == "dQw4w9WgXcQ"


def _fake_response(payload):
    """Petit contexte mock pour `urlopen`."""

    class _Resp:
        def __init__(self, body):
            self._body = body

        def read(self, *args):
            return self._body

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    return _Resp(payload)


class TestFetchOembed:
    def test_returns_title_and_thumbnail_on_success(self):
        body = (
            b'{"title": "Ma chanson", '
            b'"thumbnail_url": "https://i.ytimg.com/vi/abc/hqdefault.jpg"}'
        )
        with patch("apps.discotheque.youtube.urlopen", return_value=_fake_response(body)):
            data = fetch_oembed("https://youtu.be/dQw4w9WgXcQ")
        assert data == {
            "title": "Ma chanson",
            "thumbnail_url": "https://i.ytimg.com/vi/abc/hqdefault.jpg",
        }

    def test_returns_none_on_network_error(self):
        with patch(
            "apps.discotheque.youtube.urlopen", side_effect=URLError("nope")
        ):
            assert fetch_oembed("https://youtu.be/dQw4w9WgXcQ") is None

    def test_returns_none_on_invalid_json(self):
        with patch(
            "apps.discotheque.youtube.urlopen",
            return_value=_fake_response(b"not json"),
        ):
            assert fetch_oembed("https://youtu.be/dQw4w9WgXcQ") is None

    def test_returns_none_for_empty_url(self):
        assert fetch_oembed("") is None
        assert fetch_oembed(None) is None


class TestDownloadThumbnail:
    def test_returns_name_and_bytes_on_success(self):
        with patch(
            "apps.discotheque.youtube.urlopen",
            return_value=_fake_response(b"\xff\xd8\xff\xe0fakejpeg"),
        ):
            name, content = download_thumbnail("https://i.ytimg.com/vi/abc/hqdefault.jpg")
        assert name == "yt-thumbnail.jpg"
        assert content == b"\xff\xd8\xff\xe0fakejpeg"

    def test_returns_none_on_network_error(self):
        with patch(
            "apps.discotheque.youtube.urlopen", side_effect=URLError("nope")
        ):
            name, content = download_thumbnail("https://example.com/img.jpg")
        assert name is None and content is None

    def test_returns_none_when_oversized(self):
        # 5 Mo + 1 octet → trop gros, on rejette.
        oversized = b"x" * (5 * 1024 * 1024 + 1)
        with patch(
            "apps.discotheque.youtube.urlopen",
            return_value=_fake_response(oversized),
        ):
            name, content = download_thumbnail("https://example.com/big.jpg")
        assert name is None and content is None

    def test_returns_none_for_empty_url(self):
        name, content = download_thumbnail("")
        assert name is None and content is None
