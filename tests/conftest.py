"""테스트 공통 fixture.

설계 메모:
- 외부 API 호출은 `responses` 라이브러리로 mock한다. 모든 테스트가 실제
  네트워크에 닿지 않아야 unit test로 분류할 수 있고 CI가 빠르고 결정적이다.
- 통합(외부 API 실제 호출) 테스트는 `pytest.mark.integration`으로 표시하고
  기본 실행에서 제외한다.
- 캐시는 tempdir에 격리. 테스트마다 새 폴더라 cross-test 오염 없음.
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
import responses


@pytest.fixture
def mocked_responses() -> Generator[responses.RequestsMock, None, None]:
    """responses.RequestsMock을 enable + 모든 등록된 URL이 호출됐는지 검증."""
    with responses.RequestsMock(assert_all_requests_are_fired=True) as rsps:
        yield rsps


@pytest.fixture
def mocked_responses_loose() -> Generator[responses.RequestsMock, None, None]:
    """fire-and-forget 케이스용. 등록된 URL 중 일부만 호출돼도 OK."""
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        yield rsps


@pytest.fixture
def isolated_cache_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """BaseAPIClient의 캐시 디렉토리를 테스트별 tempdir로 강제.

    tempfile.gettempdir()를 monkeypatch해서 /tmp가 아닌 pytest tmp_path를
    쓰게 한다. 테스트 간 캐시 오염을 막고, 종료 시 자동 정리된다.
    """
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    return tmp_path
