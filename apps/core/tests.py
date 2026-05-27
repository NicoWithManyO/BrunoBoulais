from django.test import RequestFactory

from apps.core.middleware import _client_ip


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
