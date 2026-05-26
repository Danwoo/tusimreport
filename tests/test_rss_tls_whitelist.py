"""verify=False를 화이트리스트 호스트에만 적용하는지 검증.

회귀 시나리오: 누군가 다시 모든 RSS 요청에 `verify=False`를 박으면
이 테스트가 깨진다.
"""

from __future__ import annotations

from data.korean_news_rss_client import _ALLOWED_INSECURE_HOSTS, _should_verify_tls


class TestShouldVerifyTLS:
    def test_unknown_host_verifies(self):
        assert _should_verify_tls("https://example.com/rss") is True

    def test_google_news_verifies_by_default(self):
        # 활성 소스. 정상 인증서이므로 verify=True여야 한다.
        assert _should_verify_tls("https://news.google.com/rss/search?q=x") is True

    def test_whitelisted_host_skips_verification(self):
        """화이트리스트가 비어 있는 현재 상태에서는 모두 verify=True.
        목록에 호스트를 추가하면 False가 나와야 함을 보장."""
        for host in _ALLOWED_INSECURE_HOSTS:
            assert _should_verify_tls(f"https://{host}/feed") is False

    def test_malformed_url_falls_back_to_verify(self):
        # 파싱 실패해도 안전한 기본값(True)을 반환해야 한다.
        assert _should_verify_tls("not a url at all") is True

    def test_http_scheme_with_unknown_host_verifies(self):
        # http://에서도 호스트 화이트리스트 동일 적용.
        assert _should_verify_tls("http://random.example/feed") is True
