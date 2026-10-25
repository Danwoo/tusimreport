#!/usr/bin/env python3
"""
TuSimReport 환경 검증 스크립트
설치 후 환경이 올바르게 설정되었는지 확인합니다.
"""

import argparse
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlparse


def print_header(text):
    """헤더 출력"""
    print(f"\n{'=' * 60}")
    print(f"  {text}")
    print(f"{'=' * 60}\n")


def print_section(text):
    """섹션 헤더"""
    print(f"\n{'─' * 60}")
    print(f"  {text}")
    print(f"{'─' * 60}")


def check_python_version():
    """Python 버전 확인"""
    print_section("1. Python 버전 확인")
    version = sys.version_info
    print(f"현재 Python 버전: {version.major}.{version.minor}.{version.micro}")

    if version.major == 3 and version.minor >= 11:
        print("✅ Python 버전 요구사항 충족 (3.11+)")
        return True
    else:
        print(f"❌ Python 3.11 이상이 필요합니다 (현재: {version.major}.{version.minor})")
        return False


def check_dependencies():
    """필수 패키지 설치 확인"""
    print_section("2. 필수 패키지 설치 확인")

    required_packages = [
        ("streamlit", "Streamlit"),
        ("langchain", "LangChain"),
        ("langchain_openai", "LangChain OpenAI"),
        ("langgraph", "LangGraph"),
        ("pandas", "Pandas"),
        ("pydantic_settings", "Pydantic Settings"),
        ("FinanceDataReader", "FinanceDataReader"),
        ("selenium", "Selenium (v2.1)"),
        ("pytest", "Pytest"),
    ]

    all_installed = True
    for package, name in required_packages:
        try:
            __import__(package)
            print(f"✅ {name}: 설치됨")
        except ImportError:
            print(f"❌ {name}: 미설치")
            all_installed = False

    if not all_installed:
        print("\n⚠️  일부 패키지가 설치되지 않았습니다.")
        print("    다음 명령으로 설치하세요: pip install -r requirements.txt")

    return all_installed


def check_env_file():
    """환경 설정 파일 확인"""
    print_section("3. 환경 설정 파일 확인")

    env_path = Path(".env")
    env_example_path = Path(".env.example")

    if not env_example_path.exists():
        print("❌ .env.example 파일이 없습니다")
        return False
    else:
        print("✅ .env.example 파일 존재")

    if env_path.exists():
        print("✅ .env 파일 존재")
    else:
        print("ℹ️  .env 파일이 없습니다 — 환경변수(클라우드 세션 secret 등)에서만 키를 읽습니다")
        print("    로컬에서는: cp .env.example .env 후 키 입력 (안내: docs/API_KEYS.md)")
    return True


def _endpoint_host(base_url):
    """URL에 섞인 user:password를 빼고 host[:port]만 돌려준다."""
    if not base_url:
        return "provider 기본값"
    parsed = urlparse(base_url)
    return f"{parsed.hostname}:{parsed.port}" if parsed.port else str(parsed.hostname)


def check_api_keys():
    """API 키 설정 확인. 키 값은 일부라도 출력하지 않는다."""
    print_section("4. API 키 설정 확인")

    try:
        from config.settings import get_api_key_status, resolve_llm_config

        status = get_api_key_status()
        llm_config, llm_problem = resolve_llm_config()
    except Exception as e:  # 잘못된 .env 값이면 Settings() 생성에서 ValidationError가 난다
        print(f"❌ 설정을 읽지 못했습니다: {type(e).__name__}: {str(e)[:300]}")
        return False
    labels = {
        "llm": "LLM (필수)",
        "dart": "DART (금융감독원, 필수)",
        "ecos": "ECOS (한국은행, 필수)",
        "naver": "Naver 뉴스 검색 (발급 보류 — docs/API_KEYS.md 4.4)",
        "tavily": "Tavily (선택)",
        "alpha_vantage": "Alpha Vantage (선택)",
    }
    for key, label in labels.items():
        print(f"  {label}: {status[key]}")

    # pykrx는 settings가 아니라 os.environ에서 직접 읽는다.
    has_krx = bool(os.getenv("KRX_ID")) and bool(os.getenv("KRX_PW"))
    print(f"  KRX 데이터 포털 로그인 (pykrx): {'✅ 설정됨' if has_krx else '⚠️ 미설정 (KRX_ID·KRX_PW)'}")

    if llm_config is not None:
        print(
            f"\n  사용할 LLM: provider={llm_config.provider} model={llm_config.model_name} "
            f"endpoint={_endpoint_host(llm_config.base_url)}"
        )
    elif llm_problem:
        print(f"\n  에이전트가 LLM을 만들 수 없습니다:\n{llm_problem}")

    has_dart = status["dart"].startswith("✅")
    has_ecos = status["ecos"].startswith("✅")
    print("\n최소 요구사항 확인:")
    if llm_config is not None and has_dart and has_ecos:
        print("✅ 최소 설정 완료 (LLM + DART + ECOS)")
        return True
    print("❌ 최소 설정이 완료되지 않았습니다 (안내: docs/API_KEYS.md)")
    return False


def probe_llm_tool_calling():
    """설정된 LLM에 tool calling 요청을 한 번 보내 ReAct 에이전트가 쓸 수 있는지 확인한다."""
    print_section("8. LLM tool calling 확인 (--llm-probe, 실제 호출 1회)")

    from langchain_core.tools import tool

    from config.llm_factory import build_llm

    @tool
    def get_stock_price(stock_code: str) -> str:
        """종목코드의 현재가를 조회한다."""
        return "0"

    try:
        llm = build_llm(temperature=0)  # 에이전트와 같은 raise_on_missing=True 경로
    except Exception as e:
        print(f"❌ 에이전트가 쓰는 LLM을 만들지 못했습니다: {str(e).splitlines()[0]}")
        return False

    started = time.monotonic()
    try:
        response = llm.bind_tools([get_stock_price]).invoke(
            "삼성전자(005930)의 현재가를 get_stock_price 도구로 조회해줘."
        )
    except Exception as e:
        print(f"❌ 호출 실패: {type(e).__name__}: {str(e)[:300]}")
        return False
    elapsed = time.monotonic() - started

    if not response.tool_calls:
        print(
            f"❌ 응답은 왔지만 tool call이 없습니다 ({elapsed:.1f}s) — ReAct 에이전트에 쓸 수 없는 모델입니다"
        )
        print(f"    응답 앞부분: {str(response.content)[:200]}")
        return False
    call = response.tool_calls[0]
    print(f"✅ tool call 수신 ({elapsed:.1f}s): {call['name']}({call['args']})")
    usage = getattr(response, "usage_metadata", None)
    if usage:
        print(f"    토큰: 입력 {usage.get('input_tokens')} / 출력 {usage.get('output_tokens')}")
    return True


def check_chrome():
    """Chrome/Chromium 설치 확인 (Selenium용)"""
    print_section("5. Chrome/Chromium 확인 (Selenium 크롤링용)")

    import shutil

    chrome_paths = ["google-chrome", "chromium", "chromium-browser", "chrome"]
    chrome_found = False

    for cmd in chrome_paths:
        if shutil.which(cmd):
            print(f"✅ Chrome/Chromium 발견: {cmd}")
            chrome_found = True
            break

    if not chrome_found:
        print("⚠️  Chrome/Chromium이 설치되지 않았습니다")
        print("    커뮤니티 분석 기능(Paxnet 크롤링)이 작동하지 않을 수 있습니다")
        print("    Linux: sudo apt-get install chromium-browser")
        print("    Mac: brew install chromium")
        return False

    return True


def check_directory_structure():
    """디렉토리 구조 확인"""
    print_section("6. 디렉토리 구조 확인")

    required_dirs = [
        "agents",
        "core",
        "data",
        "config",
        "utils",
    ]

    all_exist = True
    for dir_name in required_dirs:
        dir_path = Path(dir_name)
        if dir_path.exists() and dir_path.is_dir():
            print(f"✅ {dir_name}/")
        else:
            print(f"❌ {dir_name}/ (없음)")
            all_exist = False

    # main.py 확인
    if Path("main.py").exists():
        print("✅ main.py")
    else:
        print("❌ main.py (없음)")
        all_exist = False

    return all_exist


def run_import_test():
    """기본 import 테스트"""
    print_section("7. 기본 모듈 Import 테스트")

    modules_to_test = [
        "config.settings",
        "utils.helpers",
        "agents.korean_context_agent",
        "core.korean_supervisor_langgraph",
    ]

    # pykrx는 import 시점에 KRX_ID·KRX_PW로 data.krx.co.kr에 로그인하고(같은 계정의 다른
    # 세션을 끊는다) 로그인 ID를 출력한다. import 확인에는 로그인이 필요 없으므로 잠시 뺀다.
    krx_credentials = {k: os.environ.pop(k) for k in ("KRX_ID", "KRX_PW") if k in os.environ}
    all_ok = True
    try:
        for module_name in modules_to_test:
            try:
                __import__(module_name)
                print(f"✅ {module_name}")
            except Exception as e:
                print(f"❌ {module_name}: {str(e)[:60]}")
                all_ok = False
    finally:
        os.environ.update(krx_credentials)

    return all_ok


def main():
    """메인 함수"""
    parser = argparse.ArgumentParser(description="TuSimReport 환경 검증")
    parser.add_argument(
        "--llm-probe",
        action="store_true",
        help="설정된 LLM에 tool calling 요청을 실제로 1회 보낸다 (무료 한도 소모)",
    )
    args = parser.parse_args()

    print_header("TuSimReport 환경 검증")
    print("설치 후 환경이 올바르게 설정되었는지 확인합니다.\n")

    results = {}

    results["python"] = check_python_version()
    results["dependencies"] = check_dependencies()
    results["env_file"] = check_env_file()
    results["api_keys"] = check_api_keys()
    results["chrome"] = check_chrome()
    results["structure"] = check_directory_structure()
    results["imports"] = run_import_test()
    if args.llm_probe:
        results["llm_probe"] = probe_llm_tool_calling()

    # 최종 결과
    print_header("최종 검증 결과")

    critical_checks = ["python", "dependencies", "api_keys"] + (["llm_probe"] if args.llm_probe else [])
    critical_ok = all(results.get(k, False) for k in critical_checks)

    optional_checks = ["env_file", "chrome", "structure", "imports"]
    optional_ok = all(results.get(k, False) for k in optional_checks)

    if critical_ok and optional_ok:
        print("✅ 모든 검증 통과!")
        print("   다음 명령으로 시스템을 시작할 수 있습니다:")
        print("   streamlit run main.py")
        return 0
    elif critical_ok:
        print("⚠️  기본 요구사항은 충족되었으나 일부 기능이 제한될 수 있습니다")
        print("   시스템 시작은 가능하지만 모든 기능이 작동하지 않을 수 있습니다:")
        print("   streamlit run main.py")
        return 1
    else:
        print("❌ 환경 설정이 완료되지 않았습니다")
        print("   위의 오류를 해결한 후 다시 시도하세요")
        return 2


if __name__ == "__main__":
    sys.exit(main())
