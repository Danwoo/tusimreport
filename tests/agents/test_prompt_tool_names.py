"""프롬프트가 부르라고 지시하는 도구 이름이 실제로 등록된 도구인지 검증.

OpenAI/Gemini는 없는 도구 호출을 에러 메시지로 돌려주고 넘어가지만, Groq 등은
서버에서 도구 이름을 검사해 400(tool_use_failed)으로 에이전트를 실패시킨다.
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path

import pytest
from langchain_core.tools import BaseTool

AGENT_FILES = sorted((Path(__file__).resolve().parents[2] / "agents").glob("korean_*.py"))
TOOL_PREFIXES = ("get_", "search_", "fetch_", "analyze_", "save_", "calculate_", "generate_")


@pytest.mark.parametrize("path", AGENT_FILES, ids=lambda p: p.stem)
def test_prompt_mentions_only_registered_tools(path: Path) -> None:
    module = importlib.import_module(f"agents.{path.stem}")
    registered = {obj.name for obj in vars(module).values() if isinstance(obj, BaseTool)}
    mentioned = set(re.findall(r"`([a-z][a-z0-9_]+)`", path.read_text(encoding="utf-8")))
    tool_like = {name for name in mentioned if name.startswith(TOOL_PREFIXES)}

    assert tool_like <= registered, f"등록되지 않은 도구를 프롬프트가 언급: {sorted(tool_like - registered)}"
