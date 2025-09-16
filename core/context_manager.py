#!/usr/bin/env python3
"""
Enterprise Context Manager - 토큰 최적화 및 컨텍스트 압축
대규모 멀티 에이전트 시스템을 위한 intelligent context management
"""

import logging
import json
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
import tiktoken
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class ContextWindow:
    """컨텍스트 윈도우 관리 클래스"""
    max_tokens: int = 300000  # 30만 토큰으로 안전하게 설정
    reserved_tokens: int = 100000  # 응답용 여유 토큰 대폭 증가
    agent_summary_tokens: int = 10000  # 에이전트별 여유 토큰

    @property
    def available_tokens(self) -> int:
        return self.max_tokens - self.reserved_tokens

class EnterpriseContextManager:
    """엔터프라이즈급 컨텍스트 관리자"""

    def __init__(self, model_name: str = "gpt-4"):
        self.model_name = model_name
        self.encoding = tiktoken.encoding_for_model("gpt-4")
        self.window = ContextWindow()
        self.agent_summaries = {}
        self.data_cache = {}

        logger.info(f"Context Manager 초기화: 최대 {self.window.max_tokens:,} 토큰")

    def count_tokens(self, text: str) -> int:
        """정확한 토큰 수 계산"""
        return len(self.encoding.encode(text))

    def preserve_agent_output(self, agent_name: str, full_output: str) -> str:
        """에이전트 출력 완전 보존 - 압축/요약 없음"""
        original_tokens = self.count_tokens(full_output)
        logger.info(f"[{agent_name}] 컨텍스트 완전 보존: {original_tokens:,} 토큰")
        return full_output

    def create_progressive_summary(self, agent_outputs: Dict[str, str]) -> str:
        """점진적 요약 생성 - 정보 손실 최소화"""
        try:
            # 에이전트별 핵심 지표 추출
            summary_sections = []

            for agent_name, output in agent_outputs.items():
                compressed = self.compress_agent_output(agent_name, output)

                # 에이전트별 구조화된 요약
                agent_display_name = {
                    'context_expert': '시장환경',
                    'sentiment_expert': '시장심리',
                    'financial_expert': '재무분석',
                    'advanced_technical_expert': '기술분석',
                    'institutional_trading_expert': '수급분석',
                    'comparative_expert': '상대평가',
                    'esg_expert': 'ESG평가'
                }.get(agent_name, agent_name)

                summary_sections.append(f"## {agent_display_name}\n{compressed}")

            progressive_summary = '\n\n'.join(summary_sections)

            # 최종 토큰 검증
            final_tokens = self.count_tokens(progressive_summary)

            if final_tokens > self.window.available_tokens:
                # 추가 압축 필요
                additional_compression = self.window.available_tokens / final_tokens
                logger.warning(f"추가 압축 필요: {additional_compression:.2%}")

                # 에이전트별 동등 압축
                target_length = int(len(progressive_summary) * additional_compression)
                progressive_summary = progressive_summary[:target_length]

            logger.info(f"최종 요약 생성: {self.count_tokens(progressive_summary):,} 토큰")
            return progressive_summary

        except Exception as e:
            logger.error(f"점진적 요약 생성 오류: {str(e)}")
            return "## 요약 생성 오류\n기술적 문제로 요약을 생성할 수 없습니다."

    def optimize_data_requests(self, agent_name: str, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """데이터 요청 최적화 - 중복 제거 및 캐싱"""
        try:
            cache_key = f"{agent_name}_{hash(str(request_data))}"

            # 캐시 확인
            if cache_key in self.data_cache:
                logger.info(f"캐시 사용: {agent_name}")
                return self.data_cache[cache_key]

            # 새로운 데이터인 경우 캐시에 저장
            self.data_cache[cache_key] = request_data

            # 캐시 크기 관리 (메모리 절약)
            if len(self.data_cache) > 50:
                # LRU 방식으로 오래된 캐시 제거
                oldest_key = next(iter(self.data_cache))
                del self.data_cache[oldest_key]
                logger.info("캐시 정리 완료")

            return request_data

        except Exception as e:
            logger.error(f"데이터 요청 최적화 오류: {str(e)}")
            return request_data

    def create_context_aware_prompt(self, base_prompt: str, available_tokens: int) -> str:
        """토큰 제한에 맞는 adaptive prompt 생성"""
        try:
            prompt_tokens = self.count_tokens(base_prompt)

            if prompt_tokens <= available_tokens:
                return base_prompt

            # 토큰 초과시 adaptive compression
            compression_ratio = available_tokens / prompt_tokens

            # 프롬프트의 핵심 부분 보존
            lines = base_prompt.split('\n')

            # 중요도별 라인 분류
            critical_lines = []  # CRITICAL REQUIREMENTS, MISSION
            structure_lines = []  # 분석 구조
            detail_lines = []   # 상세 설명

            for line in lines:
                if any(keyword in line.upper() for keyword in ['CRITICAL', 'MISSION', 'IMPORTANT']):
                    critical_lines.append(line)
                elif any(keyword in line for keyword in ['###', '##', '-']):
                    structure_lines.append(line)
                else:
                    detail_lines.append(line)

            # 중요도 순으로 재구성
            compressed_lines = (
                critical_lines +
                structure_lines[:int(len(structure_lines) * compression_ratio)] +
                detail_lines[:int(len(detail_lines) * compression_ratio * 0.5)]
            )

            compressed_prompt = '\n'.join(compressed_lines)

            logger.info(f"프롬프트 압축: {prompt_tokens:,} → {self.count_tokens(compressed_prompt):,} 토큰")
            return compressed_prompt

        except Exception as e:
            logger.error(f"프롬프트 최적화 오류: {str(e)}")
            # 실패시 단순 truncation
            return base_prompt[:int(len(base_prompt) * 0.7)]

    def get_context_stats(self) -> Dict[str, Any]:
        """컨텍스트 사용량 통계"""
        return {
            "max_tokens": self.window.max_tokens,
            "available_tokens": self.window.available_tokens,
            "cached_data_items": len(self.data_cache),
            "agent_summaries": len(self.agent_summaries),
            "timestamp": datetime.now().isoformat()
        }

# 전역 컨텍스트 매니저 인스턴스
enterprise_context_manager = EnterpriseContextManager()

def get_context_manager() -> EnterpriseContextManager:
    """전역 컨텍스트 매니저 접근"""
    return enterprise_context_manager