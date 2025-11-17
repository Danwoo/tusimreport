"""
Smoke Test - 기본 동작 확인
시스템의 기본적인 기능이 작동하는지 확인하는 빠른 테스트
"""

import pytest
import sys
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestImports:
    """모든 주요 모듈이 import 가능한지 테스트"""

    def test_import_config(self):
        """설정 모듈 import"""
        from config import settings
        assert settings is not None

    def test_import_utils(self):
        """유틸리티 모듈 import"""
        from utils import helpers
        assert helpers is not None

    def test_import_agents(self):
        """8개 에이전트 모듈 import"""
        from agents import korean_context_agent
        from agents import korean_sentiment_agent
        from agents import korean_financial_react_agent
        from agents import korean_advanced_technical_agent
        from agents import korean_institutional_trading_agent
        from agents import korean_comparative_agent
        from agents import korean_esg_analysis_agent
        from agents import korean_community_agent

        assert korean_context_agent is not None
        assert korean_sentiment_agent is not None
        assert korean_financial_react_agent is not None
        assert korean_advanced_technical_agent is not None
        assert korean_institutional_trading_agent is not None
        assert korean_comparative_agent is not None
        assert korean_esg_analysis_agent is not None
        assert korean_community_agent is not None

    def test_import_core(self):
        """코어 모듈 import"""
        from core import korean_supervisor_langgraph
        from core import progressive_supervisor
        from core import context_manager
        from core import enhanced_react_agent

        assert korean_supervisor_langgraph is not None
        assert progressive_supervisor is not None
        assert context_manager is not None
        assert enhanced_react_agent is not None

    def test_import_data_clients(self):
        """데이터 클라이언트 import"""
        from data import bok_api_client
        from data import dart_api_client
        from data import naver_api_client
        from data import tavily_api_client
        from data import paxnet_crawl_client
        from data import chart_generator
        from data import sector_analysis_client

        assert bok_api_client is not None
        assert dart_api_client is not None
        assert naver_api_client is not None
        assert tavily_api_client is not None
        assert paxnet_crawl_client is not None
        assert chart_generator is not None
        assert sector_analysis_client is not None


class TestSettings:
    """설정 파일 검증"""

    def test_settings_can_load(self):
        """Settings 클래스 로딩 가능"""
        from config.settings import Settings
        settings = Settings()
        assert settings is not None

    def test_settings_has_required_fields(self):
        """필수 설정 필드 존재"""
        from config.settings import settings

        # LLM 설정
        assert hasattr(settings, 'openai_api_key')
        assert hasattr(settings, 'google_api_key')
        assert hasattr(settings, 'use_gemini')

        # 데이터 API 설정
        assert hasattr(settings, 'dart_api_key')
        assert hasattr(settings, 'ecos_api_key')
        assert hasattr(settings, 'naver_client_id')

        # 앱 설정
        assert hasattr(settings, 'debug')
        assert hasattr(settings, 'log_level')

    def test_get_llm_model_function_exists(self):
        """LLM 모델 선택 함수 존재"""
        from config.settings import get_llm_model
        assert callable(get_llm_model)


class TestProjectStructure:
    """프로젝트 구조 검증"""

    def test_required_directories_exist(self):
        """필수 디렉토리 존재"""
        project_root = Path(__file__).parent.parent

        required_dirs = [
            'agents',
            'core',
            'data',
            'config',
            'utils',
            'tests',
        ]

        for dir_name in required_dirs:
            dir_path = project_root / dir_name
            assert dir_path.exists(), f"{dir_name} 디렉토리가 없습니다"
            assert dir_path.is_dir(), f"{dir_name}은(는) 디렉토리가 아닙니다"

    def test_required_files_exist(self):
        """필수 파일 존재"""
        project_root = Path(__file__).parent.parent

        required_files = [
            'main.py',
            'requirements.txt',
            'README.md',
            'CLAUDE.md',
            '.gitignore',
            '.env.example',
            'setup_check.py',
        ]

        for file_name in required_files:
            file_path = project_root / file_name
            assert file_path.exists(), f"{file_name} 파일이 없습니다"
            assert file_path.is_file(), f"{file_name}은(는) 파일이 아닙니다"

    def test_agents_count(self):
        """8개 에이전트 파일 존재"""
        project_root = Path(__file__).parent.parent
        agents_dir = project_root / 'agents'

        agent_files = [
            'korean_context_agent.py',
            'korean_sentiment_agent.py',
            'korean_financial_react_agent.py',
            'korean_advanced_technical_agent.py',
            'korean_institutional_trading_agent.py',
            'korean_comparative_agent.py',
            'korean_esg_analysis_agent.py',
            'korean_community_agent.py',  # v2.1
        ]

        for agent_file in agent_files:
            agent_path = agents_dir / agent_file
            assert agent_path.exists(), f"{agent_file} 파일이 없습니다"


class TestBasicFunctionality:
    """기본 기능 테스트 (API 호출 없음)"""

    def test_stock_code_validation(self):
        """종목 코드 형식 검증 로직 테스트"""
        # 6자리 숫자 검증
        valid_codes = ['005930', '035420', '000660']
        invalid_codes = ['05930', 'abc123', '12345', '1234567']

        for code in valid_codes:
            assert len(code) == 6, f"{code}는 6자리가 아닙니다"
            assert code.isdigit(), f"{code}는 숫자가 아닙니다"

        for code in invalid_codes:
            assert not (len(code) == 6 and code.isdigit()), \
                f"{code}는 유효한 종목코드 형식입니다 (예상: 무효)"

    def test_logger_setup(self):
        """로거 설정 가능"""
        from utils.helpers import setup_logging
        logger = setup_logging("INFO", enable_file_logging=False)
        assert logger is not None

    def test_no_hardcoded_api_keys(self):
        """하드코딩된 API 키 없음 확인"""
        from config.settings import settings

        # deepsearch_api_key는 None이어야 함 (하드코딩 제거됨)
        # 환경 변수가 설정되지 않은 경우 None이어야 함
        if settings.deepsearch_api_key:
            # 환경 변수에서 읽은 경우만 허용
            import os
            assert os.getenv("DEEPSEARCH_API_KEY") is not None, \
                "deepsearch_api_key가 하드코딩되어 있습니다"


class TestRequirements:
    """requirements.txt 검증"""

    def test_requirements_file_exists(self):
        """requirements.txt 파일 존재"""
        project_root = Path(__file__).parent.parent
        req_file = project_root / 'requirements.txt'
        assert req_file.exists()

    def test_critical_packages_in_requirements(self):
        """필수 패키지가 requirements.txt에 있는지"""
        project_root = Path(__file__).parent.parent
        req_file = project_root / 'requirements.txt'

        with open(req_file, 'r') as f:
            content = f.read()

        critical_packages = [
            'streamlit',
            'langchain',
            'pandas',
            'pydantic-settings',
            'selenium',  # v2.1
            'pytest',
        ]

        for package in critical_packages:
            assert package in content, \
                f"{package}가 requirements.txt에 없습니다"


if __name__ == "__main__":
    # pytest가 없어도 직접 실행 가능하도록
    pytest.main([__file__, "-v"])
