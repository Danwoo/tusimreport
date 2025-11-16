#!/usr/bin/env python3
"""
TuSimReport 환경 검증 스크립트
설치 후 환경이 올바르게 설정되었는지 확인합니다.
"""

import sys
import os
from pathlib import Path


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
        ("pandas", "Pandas"),
        ("pydantic_settings", "Pydantic Settings"),
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

    if not env_path.exists():
        print("⚠️  .env 파일이 없습니다")
        print("    다음 명령으로 생성하세요: cp .env.example .env")
        print("    그 후 .env 파일을 열어 API 키를 입력하세요")
        return False
    else:
        print("✅ .env 파일 존재")
        return True


def check_api_keys():
    """API 키 설정 확인"""
    print_section("4. API 키 설정 확인")

    from dotenv import load_dotenv
    load_dotenv()

    required_keys = {
        "LLM (필수)": [
            ("GOOGLE_API_KEY", "Google Gemini"),
            ("OPENAI_API_KEY", "OpenAI"),
        ],
        "금융 데이터 (필수)": [
            ("DART_API_KEY", "DART (금융감독원)"),
            ("ECOS_API_KEY", "ECOS (한국은행)"),
        ],
        "뉴스 (권장)": [
            ("NAVER_CLIENT_ID", "Naver News (한국)"),
            ("NAVER_CLIENT_SECRET", "Naver News Secret"),
            ("TAVILY_API_KEY", "Tavily (글로벌)"),
        ],
    }

    status = {}

    for category, keys in required_keys.items():
        print(f"\n{category}:")
        for key, name in keys:
            value = os.getenv(key)
            is_set = value is not None and value != f"your_{key.lower()}_here" and value != ""
            status[key] = is_set

            if is_set:
                masked = value[:8] + "..." if len(value) > 8 else "***"
                print(f"  ✅ {name}: {masked}")
            else:
                print(f"  ❌ {name}: 미설정")

    # 최소 요구사항 확인
    has_llm = status.get("GOOGLE_API_KEY") or status.get("OPENAI_API_KEY")
    has_dart = status.get("DART_API_KEY")
    has_ecos = status.get("ECOS_API_KEY")

    print("\n최소 요구사항 확인:")
    if has_llm and has_dart and has_ecos:
        print("✅ 최소 API 키 설정 완료 (LLM + DART + ECOS)")
        print("⚠️  뉴스 API 키를 추가하면 더 나은 분석이 가능합니다")
        return True
    else:
        print("❌ 최소 API 키가 설정되지 않았습니다")
        if not has_llm:
            print("    - GOOGLE_API_KEY 또는 OPENAI_API_KEY 필요")
        if not has_dart:
            print("    - DART_API_KEY 필요")
        if not has_ecos:
            print("    - ECOS_API_KEY 필요")
        return False


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
        print(f"✅ main.py")
    else:
        print(f"❌ main.py (없음)")
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

    all_ok = True
    for module_name in modules_to_test:
        try:
            __import__(module_name)
            print(f"✅ {module_name}")
        except Exception as e:
            print(f"❌ {module_name}: {str(e)[:60]}")
            all_ok = False

    return all_ok


def main():
    """메인 함수"""
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

    # 최종 결과
    print_header("최종 검증 결과")

    critical_checks = ["python", "dependencies", "env_file", "api_keys"]
    critical_ok = all(results.get(k, False) for k in critical_checks)

    optional_checks = ["chrome", "structure", "imports"]
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
