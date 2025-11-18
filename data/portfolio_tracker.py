#!/usr/bin/env python3
"""
Portfolio Tracker - Phase 4
포트폴리오 추적 및 리밸런싱 제안
사용자 요구: 47% (14명)
"""

import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from pathlib import Path
import FinanceDataReader as fdr

logger = logging.getLogger(__name__)


class PortfolioTracker:
    """포트폴리오 추적 및 분석"""

    def __init__(self, portfolio_file: str = "portfolio.json"):
        """
        Args:
            portfolio_file: 포트폴리오 저장 파일 경로
        """
        self.portfolio_file = Path(portfolio_file)
        self.portfolio = self._load_portfolio()

    def _load_portfolio(self) -> Dict[str, Any]:
        """포트폴리오 로드"""
        if self.portfolio_file.exists():
            try:
                with open(self.portfolio_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"포트폴리오 로드 실패: {str(e)}")
                return {"holdings": [], "transactions": [], "created_at": datetime.now().isoformat()}
        else:
            return {"holdings": [], "transactions": [], "created_at": datetime.now().isoformat()}

    def _save_portfolio(self):
        """포트폴리오 저장"""
        try:
            with open(self.portfolio_file, 'w', encoding='utf-8') as f:
                json.dump(self.portfolio, f, ensure_ascii=False, indent=2)
            logger.info(f"포트폴리오 저장 완료: {self.portfolio_file}")
        except Exception as e:
            logger.error(f"포트폴리오 저장 실패: {str(e)}")

    def add_holding(
        self,
        stock_code: str,
        company_name: str,
        shares: int,
        avg_price: float,
        purchase_date: str = None
    ) -> Dict[str, Any]:
        """
        보유 종목 추가

        Args:
            stock_code: 종목코드
            company_name: 회사명
            shares: 보유 주식수
            avg_price: 평균 매수가
            purchase_date: 매수 날짜 (YYYY-MM-DD)

        Returns:
            추가된 보유 종목 정보
        """
        try:
            if purchase_date is None:
                purchase_date = datetime.now().strftime("%Y-%m-%d")

            # 기존 종목 확인
            existing = next((h for h in self.portfolio["holdings"] if h["stock_code"] == stock_code), None)

            if existing:
                # 평균 매수가 재계산
                total_shares = existing["shares"] + shares
                total_cost = (existing["shares"] * existing["avg_price"]) + (shares * avg_price)
                new_avg_price = total_cost / total_shares

                existing["shares"] = total_shares
                existing["avg_price"] = new_avg_price
                existing["last_updated"] = datetime.now().isoformat()

                holding = existing
            else:
                # 신규 종목 추가
                holding = {
                    "stock_code": stock_code,
                    "company_name": company_name,
                    "shares": shares,
                    "avg_price": avg_price,
                    "purchase_date": purchase_date,
                    "added_at": datetime.now().isoformat(),
                    "last_updated": datetime.now().isoformat()
                }
                self.portfolio["holdings"].append(holding)

            # 거래 기록 추가
            transaction = {
                "type": "BUY",
                "stock_code": stock_code,
                "company_name": company_name,
                "shares": shares,
                "price": avg_price,
                "date": purchase_date,
                "timestamp": datetime.now().isoformat()
            }
            self.portfolio["transactions"].append(transaction)

            self._save_portfolio()

            logger.info(f"보유 종목 추가: {company_name} ({stock_code}) - {shares}주 @ {avg_price:,}원")
            return holding

        except Exception as e:
            logger.error(f"보유 종목 추가 실패: {str(e)}")
            return {"error": str(e)}

    def remove_holding(self, stock_code: str, shares: int = None) -> Dict[str, Any]:
        """
        보유 종목 제거/감소

        Args:
            stock_code: 종목코드
            shares: 판매 주식수 (None이면 전량 매도)

        Returns:
            제거된 종목 정보
        """
        try:
            holding = next((h for h in self.portfolio["holdings"] if h["stock_code"] == stock_code), None)

            if not holding:
                return {"error": f"보유하지 않은 종목: {stock_code}"}

            if shares is None or shares >= holding["shares"]:
                # 전량 매도
                sold_shares = holding["shares"]
                self.portfolio["holdings"].remove(holding)
            else:
                # 일부 매도
                sold_shares = shares
                holding["shares"] -= shares
                holding["last_updated"] = datetime.now().isoformat()

            # 거래 기록
            transaction = {
                "type": "SELL",
                "stock_code": stock_code,
                "company_name": holding["company_name"],
                "shares": sold_shares,
                "price": self._get_current_price(stock_code),
                "date": datetime.now().strftime("%Y-%m-%d"),
                "timestamp": datetime.now().isoformat()
            }
            self.portfolio["transactions"].append(transaction)

            self._save_portfolio()

            logger.info(f"보유 종목 제거: {holding['company_name']} ({stock_code}) - {sold_shares}주 매도")
            return {"stock_code": stock_code, "sold_shares": sold_shares}

        except Exception as e:
            logger.error(f"보유 종목 제거 실패: {str(e)}")
            return {"error": str(e)}

    def get_portfolio_summary(self) -> Dict[str, Any]:
        """
        포트폴리오 요약 정보

        Returns:
            총 평가액, 총 손익, 수익률 등
        """
        try:
            if not self.portfolio["holdings"]:
                return {
                    "total_holdings": 0,
                    "total_value": 0,
                    "total_cost": 0,
                    "total_profit": 0,
                    "total_return_pct": 0,
                    "holdings_detail": []
                }

            total_value = 0
            total_cost = 0
            holdings_detail = []

            for holding in self.portfolio["holdings"]:
                stock_code = holding["stock_code"]
                shares = holding["shares"]
                avg_price = holding["avg_price"]

                # 현재가 조회
                current_price = self._get_current_price(stock_code)
                if not current_price:
                    current_price = avg_price  # Fallback

                # 평가액 및 손익 계산
                market_value = current_price * shares
                cost = avg_price * shares
                profit = market_value - cost
                return_pct = (profit / cost * 100) if cost > 0 else 0

                total_value += market_value
                total_cost += cost

                holdings_detail.append({
                    "stock_code": stock_code,
                    "company_name": holding["company_name"],
                    "shares": shares,
                    "avg_price": int(avg_price),
                    "current_price": int(current_price),
                    "market_value": int(market_value),
                    "cost": int(cost),
                    "profit": int(profit),
                    "return_pct": round(return_pct, 2),
                    "weight_pct": 0  # 나중에 계산
                })

            # 종목별 비중 계산
            for detail in holdings_detail:
                detail["weight_pct"] = round(detail["market_value"] / total_value * 100, 2) if total_value > 0 else 0

            total_profit = total_value - total_cost
            total_return_pct = (total_profit / total_cost * 100) if total_cost > 0 else 0

            return {
                "total_holdings": len(self.portfolio["holdings"]),
                "total_value": int(total_value),
                "total_cost": int(total_cost),
                "total_profit": int(total_profit),
                "total_return_pct": round(total_return_pct, 2),
                "holdings_detail": holdings_detail,
                "last_updated": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"포트폴리오 요약 생성 실패: {str(e)}")
            return {"error": str(e)}

    def suggest_rebalancing(self, target_weights: Dict[str, float] = None) -> Dict[str, Any]:
        """
        리밸런싱 제안

        Args:
            target_weights: 목표 비중 (종목코드: 비중%)
                            None이면 균등 분산

        Returns:
            리밸런싱 제안 내역
        """
        try:
            summary = self.get_portfolio_summary()

            if summary.get("total_holdings", 0) == 0:
                return {"message": "보유 종목이 없습니다"}

            holdings = summary["holdings_detail"]
            total_value = summary["total_value"]

            # 목표 비중 설정
            if target_weights is None:
                # 균등 분산
                equal_weight = 100 / len(holdings)
                target_weights = {h["stock_code"]: equal_weight for h in holdings}

            # 리밸런싱 계산
            rebalancing_actions = []

            for holding in holdings:
                stock_code = holding["stock_code"]
                current_weight = holding["weight_pct"]
                target_weight = target_weights.get(stock_code, 0)
                weight_diff = target_weight - current_weight

                if abs(weight_diff) > 1.0:  # 1% 이상 차이날 때만
                    target_value = total_value * target_weight / 100
                    current_value = holding["market_value"]
                    value_diff = target_value - current_value
                    shares_diff = int(value_diff / holding["current_price"])

                    action = "BUY" if shares_diff > 0 else "SELL"

                    rebalancing_actions.append({
                        "stock_code": stock_code,
                        "company_name": holding["company_name"],
                        "action": action,
                        "shares": abs(shares_diff),
                        "current_weight": current_weight,
                        "target_weight": target_weight,
                        "weight_diff": round(weight_diff, 2),
                        "estimated_cost": int(abs(value_diff))
                    })

            # 우선순위 정렬 (차이가 큰 순)
            rebalancing_actions.sort(key=lambda x: abs(x["weight_diff"]), reverse=True)

            return {
                "status": "success",
                "total_value": total_value,
                "rebalancing_needed": len(rebalancing_actions) > 0,
                "actions": rebalancing_actions,
                "generated_at": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"리밸런싱 제안 생성 실패: {str(e)}")
            return {"error": str(e)}

    def get_transactions_history(self, days: int = 30) -> List[Dict[str, Any]]:
        """
        거래 내역 조회

        Args:
            days: 조회 기간 (일)

        Returns:
            거래 내역 리스트
        """
        try:
            cutoff_date = datetime.now() - timedelta(days=days)

            recent_transactions = []
            for txn in self.portfolio["transactions"]:
                txn_date = datetime.fromisoformat(txn["timestamp"])
                if txn_date >= cutoff_date:
                    recent_transactions.append(txn)

            # 최신순 정렬
            recent_transactions.sort(key=lambda x: x["timestamp"], reverse=True)

            return recent_transactions

        except Exception as e:
            logger.error(f"거래 내역 조회 실패: {str(e)}")
            return []

    def _get_current_price(self, stock_code: str) -> Optional[float]:
        """현재가 조회"""
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=7)

            df = fdr.DataReader(stock_code, start_date, end_date)
            if df is not None and not df.empty:
                return float(df['Close'].iloc[-1])
            return None
        except Exception as e:
            logger.error(f"현재가 조회 실패 ({stock_code}): {str(e)}")
            return None


# 편의 함수
def create_portfolio_tracker(portfolio_file: str = "portfolio.json") -> PortfolioTracker:
    """포트폴리오 트래커 생성"""
    return PortfolioTracker(portfolio_file)


if __name__ == "__main__":
    # 테스트
    tracker = create_portfolio_tracker("test_portfolio.json")

    # 종목 추가
    tracker.add_holding("005930", "삼성전자", 10, 60000)
    tracker.add_holding("000660", "SK하이닉스", 5, 120000)

    # 요약 조회
    summary = tracker.get_portfolio_summary()
    print(json.dumps(summary, indent=2, ensure_ascii=False))

    # 리밸런싱 제안
    rebalancing = tracker.suggest_rebalancing()
    print(json.dumps(rebalancing, indent=2, ensure_ascii=False))
