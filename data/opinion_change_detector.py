#!/usr/bin/env python3
"""
Opinion Change Detector - Phase 4
투자 의견 변경 감지 및 알림
사용자 요구: 50% (15명)
"""

import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)


class OpinionChangeDetector:
    """투자 의견 변경 감지 시스템"""

    def __init__(self, history_file: str = "opinion_history.json"):
        """
        Args:
            history_file: 투자 의견 히스토리 저장 파일
        """
        self.history_file = Path(history_file)
        self.history = self._load_history()

    def _load_history(self) -> Dict[str, List[Dict[str, Any]]]:
        """투자 의견 히스토리 로드"""
        if self.history_file.exists():
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"히스토리 로드 실패: {str(e)}")
                return {}
        else:
            return {}

    def _save_history(self):
        """투자 의견 히스토리 저장"""
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(self.history, f, ensure_ascii=False, indent=2)
            logger.info(f"히스토리 저장 완료: {self.history_file}")
        except Exception as e:
            logger.error(f"히스토리 저장 실패: {str(e)}")

    def record_opinion(
        self,
        stock_code: str,
        company_name: str,
        opinion_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        투자 의견 기록

        Args:
            stock_code: 종목코드
            company_name: 회사명
            opinion_data: 투자 의견 데이터 (investment_opinion_agent 결과)

        Returns:
            변경 감지 결과
        """
        try:
            if stock_code not in self.history:
                self.history[stock_code] = []

            # 현재 의견 추출
            current_opinion = opinion_data.get('investment_opinion', {})
            decision = current_opinion.get('decision', 'N/A')
            confidence = current_opinion.get('confidence', 0)
            current_price = opinion_data.get('current_price', 0)
            target_price_3m = opinion_data.get('target_prices', {}).get('3_months', {}).get('price', 0)

            # 기록 생성
            record = {
                "timestamp": datetime.now().isoformat(),
                "company_name": company_name,
                "decision": decision,
                "confidence": confidence,
                "current_price": current_price,
                "target_price_3m": target_price_3m,
                "key_reasons": current_opinion.get('key_reasons', [])
            }

            # 이전 의견과 비교
            change_detected = self._detect_change(stock_code, record)

            # 히스토리에 추가
            self.history[stock_code].append(record)

            # 최근 30개만 유지
            if len(self.history[stock_code]) > 30:
                self.history[stock_code] = self.history[stock_code][-30:]

            self._save_history()

            return change_detected

        except Exception as e:
            logger.error(f"투자 의견 기록 실패: {str(e)}")
            return {"error": str(e)}

    def _detect_change(self, stock_code: str, new_record: Dict[str, Any]) -> Dict[str, Any]:
        """
        투자 의견 변경 감지

        Args:
            stock_code: 종목코드
            new_record: 새로운 기록

        Returns:
            변경 감지 결과
        """
        try:
            if stock_code not in self.history or len(self.history[stock_code]) == 0:
                return {
                    "change_detected": False,
                    "message": "첫 번째 분석입니다",
                    "new_decision": new_record["decision"]
                }

            # 가장 최근 기록
            previous = self.history[stock_code][-1]

            # 변경 사항 확인
            changes = []

            # 1. 투자 의견 변경
            if previous["decision"] != new_record["decision"]:
                changes.append({
                    "type": "DECISION_CHANGE",
                    "severity": "HIGH",
                    "from": previous["decision"],
                    "to": new_record["decision"],
                    "message": f"투자 의견 변경: {previous['decision']} → {new_record['decision']}"
                })

            # 2. 신뢰도 대폭 변화 (±20% 이상)
            confidence_diff = new_record["confidence"] - previous["confidence"]
            if abs(confidence_diff) >= 20:
                severity = "HIGH" if abs(confidence_diff) >= 30 else "MEDIUM"
                changes.append({
                    "type": "CONFIDENCE_CHANGE",
                    "severity": severity,
                    "from": previous["confidence"],
                    "to": new_record["confidence"],
                    "diff": confidence_diff,
                    "message": f"신뢰도 {'증가' if confidence_diff > 0 else '감소'}: {previous['confidence']}% → {new_record['confidence']}% ({confidence_diff:+}%)"
                })

            # 3. 목표가 대폭 변화 (±10% 이상)
            if previous["target_price_3m"] > 0:
                target_diff_pct = (new_record["target_price_3m"] / previous["target_price_3m"] - 1) * 100
                if abs(target_diff_pct) >= 10:
                    severity = "HIGH" if abs(target_diff_pct) >= 20 else "MEDIUM"
                    changes.append({
                        "type": "TARGET_PRICE_CHANGE",
                        "severity": severity,
                        "from": previous["target_price_3m"],
                        "to": new_record["target_price_3m"],
                        "diff_pct": round(target_diff_pct, 1),
                        "message": f"목표가 {'상향' if target_diff_pct > 0 else '하향'}: {previous['target_price_3m']:,}원 → {new_record['target_price_3m']:,}원 ({target_diff_pct:+.1f}%)"
                    })

            # 4. 주가 급등/급락 (±5% 이상)
            if previous["current_price"] > 0:
                price_diff_pct = (new_record["current_price"] / previous["current_price"] - 1) * 100
                if abs(price_diff_pct) >= 5:
                    severity = "HIGH" if abs(price_diff_pct) >= 10 else "MEDIUM"
                    changes.append({
                        "type": "PRICE_MOVEMENT",
                        "severity": severity,
                        "from": previous["current_price"],
                        "to": new_record["current_price"],
                        "diff_pct": round(price_diff_pct, 1),
                        "message": f"주가 {'급등' if price_diff_pct > 0 else '급락'}: {previous['current_price']:,}원 → {new_record['current_price']:,}원 ({price_diff_pct:+.1f}%)"
                    })

            # 변경 사항이 있으면 알림 생성
            if changes:
                # 심각도 순으로 정렬
                severity_order = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
                changes.sort(key=lambda x: severity_order.get(x["severity"], 0), reverse=True)

                # 알림 메시지 생성
                alert_message = self._generate_alert_message(
                    new_record["company_name"],
                    stock_code,
                    changes,
                    previous,
                    new_record
                )

                return {
                    "change_detected": True,
                    "changes": changes,
                    "alert_message": alert_message,
                    "severity": changes[0]["severity"],  # 가장 심각한 변경사항
                    "timestamp": datetime.now().isoformat()
                }
            else:
                return {
                    "change_detected": False,
                    "message": "유의미한 변경사항 없음"
                }

        except Exception as e:
            logger.error(f"변경 감지 실패: {str(e)}")
            return {"error": str(e)}

    def _generate_alert_message(
        self,
        company_name: str,
        stock_code: str,
        changes: List[Dict[str, Any]],
        previous: Dict[str, Any],
        new_record: Dict[str, Any]
    ) -> str:
        """알림 메시지 생성"""
        lines = []
        lines.append(f"🔔 {company_name} ({stock_code}) 투자 의견 업데이트")
        lines.append("")

        # 주요 변경사항
        lines.append("📊 주요 변경사항:")
        for i, change in enumerate(changes[:3], 1):  # 상위 3개만
            lines.append(f"  {i}. {change['message']}")

        lines.append("")

        # 현재 투자 의견
        lines.append("💡 현재 투자 의견:")
        lines.append(f"  - 결론: {new_record['decision']} (신뢰도 {new_record['confidence']}%)")
        lines.append(f"  - 현재가: {new_record['current_price']:,}원")
        lines.append(f"  - 3개월 목표가: {new_record['target_price_3m']:,}원")

        lines.append("")

        # 권장 조치
        lines.append("⚡ 권장 조치:")
        recommended_action = self._get_recommended_action(changes, previous, new_record)
        lines.append(f"  {recommended_action}")

        return "\n".join(lines)

    def _get_recommended_action(
        self,
        changes: List[Dict[str, Any]],
        previous: Dict[str, Any],
        new_record: Dict[str, Any]
    ) -> str:
        """권장 조치 생성"""
        # 투자 의견 변경 우선
        decision_change = next((c for c in changes if c["type"] == "DECISION_CHANGE"), None)

        if decision_change:
            if decision_change["to"] == "BUY" and decision_change["from"] != "BUY":
                return "✅ 신규 진입 또는 비중 확대 고려"
            elif decision_change["to"] == "SELL" and decision_change["from"] != "SELL":
                return "⚠️ 포지션 축소 또는 손절 고려"
            elif decision_change["to"] == "HOLD":
                if decision_change["from"] == "BUY":
                    return "⏸️ 신규 진입 보류, 기존 포지션 유지"
                else:
                    return "⏸️ 관망 권장"

        # 신뢰도 변화
        confidence_change = next((c for c in changes if c["type"] == "CONFIDENCE_CHANGE"), None)
        if confidence_change:
            if confidence_change["diff"] > 0:
                return f"📈 투자 확신 증가 - {new_record['decision']} 전략 강화 고려"
            else:
                return "📉 투자 확신 감소 - 신중한 접근 필요"

        return "ℹ️ 현재 포지션 유지 및 모니터링"

    def get_recent_changes(self, stock_code: str, days: int = 7) -> List[Dict[str, Any]]:
        """
        최근 변경 내역 조회

        Args:
            stock_code: 종목코드
            days: 조회 기간 (일)

        Returns:
            변경 내역 리스트
        """
        try:
            if stock_code not in self.history:
                return []

            cutoff_date = datetime.now() - timedelta(days=days)

            recent_records = []
            for record in self.history[stock_code]:
                record_date = datetime.fromisoformat(record["timestamp"])
                if record_date >= cutoff_date:
                    recent_records.append(record)

            return recent_records

        except Exception as e:
            logger.error(f"최근 변경 내역 조회 실패: {str(e)}")
            return []

    def get_alert_triggers(self, stock_code: str) -> Dict[str, Any]:
        """
        알림 트리거 설정 조회

        Args:
            stock_code: 종목코드

        Returns:
            알림 트리거 설정
        """
        # 기본 알림 트리거
        return {
            "decision_change": True,  # 투자 의견 변경
            "confidence_threshold": 20,  # 신뢰도 변화 임계값 (%)
            "target_price_threshold": 10,  # 목표가 변화 임계값 (%)
            "price_movement_threshold": 5,  # 주가 변동 임계값 (%)
        }


# 편의 함수
def create_opinion_detector(history_file: str = "opinion_history.json") -> OpinionChangeDetector:
    """투자 의견 변경 감지기 생성"""
    return OpinionChangeDetector(history_file)


if __name__ == "__main__":
    # 테스트
    detector = create_opinion_detector("test_opinion_history.json")

    # 첫 번째 분석 기록
    opinion_1 = {
        "investment_opinion": {
            "decision": "BUY",
            "confidence": 75,
            "key_reasons": ["긍정 뉴스", "기관 매수", "저평가"]
        },
        "current_price": 60000,
        "target_prices": {
            "3_months": {"price": 70000}
        }
    }

    result_1 = detector.record_opinion("005930", "삼성전자", opinion_1)
    print("=== 첫 번째 분석 ===")
    print(json.dumps(result_1, indent=2, ensure_ascii=False))

    # 두 번째 분석 (변경 있음)
    opinion_2 = {
        "investment_opinion": {
            "decision": "HOLD",
            "confidence": 55,
            "key_reasons": ["메모리 가격 하락", "기관 매도", "밸류에이션 부담"]
        },
        "current_price": 57000,
        "target_prices": {
            "3_months": {"price": 62000}
        }
    }

    result_2 = detector.record_opinion("005930", "삼성전자", opinion_2)
    print("\n=== 두 번째 분석 (변경 감지) ===")
    print(json.dumps(result_2, indent=2, ensure_ascii=False))

    if result_2.get("change_detected"):
        print("\n=== 알림 메시지 ===")
        print(result_2.get("alert_message", ""))
