#!/usr/bin/env python3
"""
데모 데이터 로더
API 키 없이 시스템을 체험할 수 있도록 샘플 데이터 제공
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class DemoDataLoader:
    """데모 데이터 로더 클래스"""

    def __init__(self):
        """초기화"""
        self.demo_data_path = Path(__file__).parent / "demo_data.json"
        self._data = None

    def load_demo_data(self) -> Dict[str, Any]:
        """
        데모 데이터 로드

        Returns:
            전체 데모 데이터
        """
        if self._data is None:
            try:
                with open(self.demo_data_path, 'r', encoding='utf-8') as f:
                    self._data = json.load(f)
                logger.info("데모 데이터 로드 완료")
            except Exception as e:
                logger.error(f"데모 데이터 로드 실패: {e}")
                self._data = {}

        return self._data

    def get_company_demo(self, stock_code: str) -> Optional[Dict[str, Any]]:
        """
        특정 종목의 데모 데이터 가져오기

        Args:
            stock_code: 종목 코드

        Returns:
            해당 종목의 데모 데이터 또는 None
        """
        data = self.load_demo_data()
        companies = data.get("companies", {})
        return companies.get(stock_code)

    def get_agent_demo(self, stock_code: str, agent_name: str) -> Optional[Dict[str, Any]]:
        """
        특정 종목의 특정 에이전트 데모 데이터 가져오기

        Args:
            stock_code: 종목 코드
            agent_name: 에이전트 이름 (예: "context", "sentiment")

        Returns:
            해당 에이전트의 데모 데이터 또는 None
        """
        company_data = self.get_company_demo(stock_code)
        if not company_data:
            return None

        demo_analysis = company_data.get("demo_analysis", {})
        return demo_analysis.get(agent_name)

    def is_demo_available(self, stock_code: str) -> bool:
        """
        해당 종목의 데모 데이터 존재 여부

        Args:
            stock_code: 종목 코드

        Returns:
            데모 데이터 존재 여부
        """
        return self.get_company_demo(stock_code) is not None

    def get_demo_stock_list(self) -> list[str]:
        """
        데모 데이터가 있는 종목 코드 목록

        Returns:
            종목 코드 리스트
        """
        data = self.load_demo_data()
        companies = data.get("companies", {})
        return list(companies.keys())

    def get_demo_message(self) -> str:
        """
        데모 모드 안내 메시지

        Returns:
            안내 메시지
        """
        return (
            "🎭 데모 모드\n\n"
            "API 키 없이 샘플 데이터로 시스템을 체험하고 있습니다.\n"
            "실제 분석을 위해서는 .env 파일에 API 키를 설정해주세요.\n\n"
            "데모 가능 종목:\n"
            "- 005930 (삼성전자)\n"
            "- 035420 (네이버)"
        )


# 싱글톤 인스턴스
_demo_loader = DemoDataLoader()


def load_demo_data() -> Dict[str, Any]:
    """전체 데모 데이터 로드"""
    return _demo_loader.load_demo_data()


def get_company_demo(stock_code: str) -> Optional[Dict[str, Any]]:
    """종목 데모 데이터 가져오기"""
    return _demo_loader.get_company_demo(stock_code)


def get_agent_demo(stock_code: str, agent_name: str) -> Optional[Dict[str, Any]]:
    """에이전트 데모 데이터 가져오기"""
    return _demo_loader.get_agent_demo(stock_code, agent_name)


def is_demo_available(stock_code: str) -> bool:
    """데모 데이터 존재 여부"""
    return _demo_loader.is_demo_available(stock_code)


def get_demo_stock_list() -> list[str]:
    """데모 종목 목록"""
    return _demo_loader.get_demo_stock_list()


def get_demo_message() -> str:
    """데모 안내 메시지"""
    return _demo_loader.get_demo_message()
