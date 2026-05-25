import pytest

from apps.discotheque.models import Chanson, extract_youtube_id


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
