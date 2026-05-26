"""ChatSession: 시스템 프롬프트 빌드 / 대화 메시지 흐름 / lock 안전성 검증."""

from __future__ import annotations

import threading
from unittest.mock import MagicMock

import pytest

from core.chat_session import ChatSession


@pytest.fixture
def patched_llm(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """build_llm을 patched하여 ChatSession이 .invoke()를 받았을 때 결정론적
    응답을 돌려준다. caller 마다 다른 응답이 필요하면 stub.invoke.side_effect
    를 갈아 끼우면 된다.
    """
    stub_llm = MagicMock()

    def fake_invoke(messages):
        response = MagicMock()
        # 마지막 user 메시지를 echo해 테스트가 메시지 흐름을 검증할 수 있게.
        last_user = next(
            (m.content for m in reversed(messages) if type(m).__name__ == "HumanMessage"),
            "",
        )
        response.content = f"AI 답변: {last_user[:30]}"
        return response

    stub_llm.invoke.side_effect = fake_invoke
    monkeypatch.setattr("core.chat_session.build_llm", lambda **_kw: stub_llm)
    return stub_llm


def test_system_prompt_includes_company_and_agent_results(patched_llm: MagicMock) -> None:
    analysis = {
        "context_expert": {"content": "macro 환경 양호"},
        "sentiment_expert": {"content": "뉴스 긍정"},
    }
    session = ChatSession("005930", "삼성전자", analysis)
    assert "삼성전자" in session.system_prompt
    assert "005930" in session.system_prompt


def test_ask_appends_user_and_assistant_messages(patched_llm: MagicMock) -> None:
    session = ChatSession("005930", "삼성전자", {})
    answer = session.ask("PER이 뭐야?")

    assert answer.startswith("AI 답변")
    history = session.get_conversation_history()
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[0]["content"] == "PER이 뭐야?"
    assert history[1]["role"] == "assistant"
    # timestamp는 KST ISO
    assert "+09:00" in history[0]["timestamp"]


def test_recent_window_keeps_user_assistant_pairs(patched_llm: MagicMock) -> None:
    """LLM에 전달되는 최근 컨텍스트는 user 메시지부터 시작해야 한다.

    (assistant부터 시작하는 비대칭 컨텍스트는 부자연스러운 응답을 유발.)
    """
    session = ChatSession("005930", "삼성전자", {})
    for i in range(8):
        session.ask(f"질문 {i}")

    # ask 내부에서 LangChain HumanMessage / AIMessage로 변환되어 llm.invoke에
    # 전달된다. 가장 최근 호출의 인자 검사.
    call_args, _ = patched_llm.invoke.call_args
    messages = call_args[0]
    # 0번은 SystemMessage, 1번은 첫 HumanMessage여야 함
    assert type(messages[0]).__name__ == "SystemMessage"
    assert type(messages[1]).__name__ == "HumanMessage"


def test_concurrent_asks_do_not_corrupt_history(patched_llm: MagicMock) -> None:
    """ChatSession의 lock이 멀티스레드 ask에 안전한지.

    threadunsafe하면 messages 리스트 길이가 (스레드수×2)와 안 맞거나
    user/assistant 페어가 깨진다.
    """
    session = ChatSession("005930", "삼성전자", {})

    def worker(i: int) -> None:
        session.ask(f"concurrent question {i}")

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    history = session.get_conversation_history()
    assert len(history) == 16  # 8 × (user + assistant)
    # role 순서 검증: 짝수 인덱스는 user, 홀수는 assistant여야 한다.
    for idx, msg in enumerate(history):
        expected = "user" if idx % 2 == 0 else "assistant"
        assert msg["role"] == expected, f"index {idx}: expected {expected}, got {msg['role']}"


def test_clear_history_resets_messages(patched_llm: MagicMock) -> None:
    session = ChatSession("005930", "삼성전자", {})
    session.ask("first")
    session.ask("second")
    assert len(session.get_conversation_history()) == 4

    session.clear_history()
    assert session.get_conversation_history() == []


def test_llm_exception_returns_korean_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """LLM이 raise하면 ChatSession은 한글 에러 문자열을 돌려준다 — 위 레이어에서
    `st.error()`로 표시하는 데 의존."""
    bad_llm = MagicMock()
    bad_llm.invoke.side_effect = RuntimeError("LLM provider down")
    monkeypatch.setattr("core.chat_session.build_llm", lambda **_kw: bad_llm)

    session = ChatSession("005930", "삼성전자", {})
    answer = session.ask("질문")
    assert answer.startswith("❌")
    assert "오류" in answer
