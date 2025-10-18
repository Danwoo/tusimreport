#!/usr/bin/env python3
"""
SQLite 데이터베이스 클라이언트
분석 보고서, 에이전트 분석, 뉴스 소스, 대화 히스토리 영구 저장
"""

import sqlite3
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
import json

logger = logging.getLogger(__name__)

class TuSimReportDB:
    """TuSimReport SQLite 데이터베이스 클라이언트"""

    def __init__(self, db_path: str = "tusimreport.db"):
        """
        DB 클라이언트 초기화

        Args:
            db_path: 데이터베이스 파일 경로
        """
        self.db_path = Path(db_path)
        self._initialize_database()
        logger.info(f"SQLite DB 초기화 완료: {self.db_path}")

    def _get_connection(self) -> sqlite3.Connection:
        """DB 연결 생성"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Dict-like 결과 반환
        return conn

    def _initialize_database(self):
        """데이터베이스 테이블 초기화"""
        conn = self._get_connection()
        cursor = conn.cursor()

        # 1. 분석 보고서 메타데이터 테이블
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS analysis_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                stock_code TEXT NOT NULL,
                company_name TEXT NOT NULL,
                analysis_date DATETIME NOT NULL,
                analysis_method TEXT,
                chart_image BLOB,
                final_report TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 2. 에이전트 분석 테이블 (8개 에이전트 개별 보고서)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS agent_analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id INTEGER NOT NULL,
                agent_name TEXT NOT NULL,
                agent_content TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (report_id) REFERENCES analysis_reports(id) ON DELETE CASCADE
            )
        """)

        # 3. 뉴스/커뮤니티 소스 테이블
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS news_sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id INTEGER NOT NULL,
                source_type TEXT NOT NULL,
                title TEXT,
                url TEXT,
                pub_date TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (report_id) REFERENCES analysis_reports(id) ON DELETE CASCADE
            )
        """)

        # 4. 대화 히스토리 테이블
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversation_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp DATETIME NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (report_id) REFERENCES analysis_reports(id) ON DELETE CASCADE
            )
        """)

        # 인덱스 생성 (검색 성능 향상)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_stock_code
            ON analysis_reports(stock_code, analysis_date DESC)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_report_id
            ON conversation_history(report_id)
        """)

        conn.commit()
        conn.close()
        logger.info("데이터베이스 테이블 초기화 완료")

    def save_analysis_report(
        self,
        stock_code: str,
        company_name: str,
        analysis_date: str,
        analysis_method: str,
        final_report: str,
        agent_summaries: Dict[str, str],
        news_sources: List[Dict[str, str]] = None,
        community_sources: List[Dict[str, str]] = None,
        chart_image: bytes = None
    ) -> int:
        """
        분석 보고서 저장 (메타데이터 + 에이전트 분석 + 뉴스 소스)

        Args:
            stock_code: 종목 코드
            company_name: 회사명
            analysis_date: 분석 일시
            analysis_method: 분석 방법 (순차/병렬)
            final_report: 종합 보고서 텍스트
            agent_summaries: 8개 에이전트 분석 딕셔너리
            news_sources: 뉴스 소스 리스트
            community_sources: 커뮤니티 소스 리스트
            chart_image: 차트 이미지 바이너리

        Returns:
            int: 저장된 보고서 ID
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # 1. 보고서 메타데이터 저장
            cursor.execute("""
                INSERT INTO analysis_reports
                (stock_code, company_name, analysis_date, analysis_method, final_report, chart_image)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (stock_code, company_name, analysis_date, analysis_method, final_report, chart_image))

            report_id = cursor.lastrowid
            logger.info(f"보고서 메타데이터 저장 완료: report_id={report_id}")

            # 2. 에이전트 분석 저장
            for agent_name, agent_content in agent_summaries.items():
                cursor.execute("""
                    INSERT INTO agent_analyses (report_id, agent_name, agent_content)
                    VALUES (?, ?, ?)
                """, (report_id, agent_name, agent_content))

            logger.info(f"에이전트 분석 {len(agent_summaries)}개 저장 완료")

            # 3. 뉴스 소스 저장
            if news_sources:
                for news in news_sources:
                    cursor.execute("""
                        INSERT INTO news_sources (report_id, source_type, title, url, pub_date)
                        VALUES (?, ?, ?, ?, ?)
                    """, (report_id, "news", news.get("title"), news.get("url"), news.get("pub_date")))

                logger.info(f"뉴스 소스 {len(news_sources)}개 저장 완료")

            # 4. 커뮤니티 소스 저장
            if community_sources:
                for community in community_sources:
                    cursor.execute("""
                        INSERT INTO news_sources (report_id, source_type, title, url, pub_date)
                        VALUES (?, ?, ?, ?, ?)
                    """, (report_id, "community", community.get("title"), community.get("url"), community.get("pub_date")))

                logger.info(f"커뮤니티 소스 {len(community_sources)}개 저장 완료")

            conn.commit()
            logger.info(f"✅ 보고서 저장 완료: {stock_code} ({company_name}) - ID: {report_id}")
            return report_id

        except Exception as e:
            conn.rollback()
            logger.error(f"보고서 저장 실패: {str(e)}")
            raise

        finally:
            conn.close()

    def save_conversation_message(
        self,
        report_id: int,
        role: str,
        content: str,
        timestamp: str
    ):
        """
        대화 메시지 저장

        Args:
            report_id: 보고서 ID
            role: 역할 (user/assistant)
            content: 메시지 내용
            timestamp: 타임스탬프
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO conversation_history (report_id, role, content, timestamp)
                VALUES (?, ?, ?, ?)
            """, (report_id, role, content, timestamp))

            conn.commit()
            logger.debug(f"대화 메시지 저장: report_id={report_id}, role={role}")

        except Exception as e:
            conn.rollback()
            logger.error(f"대화 메시지 저장 실패: {str(e)}")

        finally:
            conn.close()

    def get_recent_reports(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        최근 보고서 목록 조회

        Args:
            limit: 최대 조회 개수

        Returns:
            List[Dict]: 보고서 목록
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT
                    id, stock_code, company_name, analysis_date,
                    analysis_method, created_at
                FROM analysis_reports
                ORDER BY analysis_date DESC
                LIMIT ?
            """, (limit,))

            rows = cursor.fetchall()
            reports = [dict(row) for row in rows]

            logger.info(f"최근 보고서 {len(reports)}개 조회 완료")
            return reports

        except Exception as e:
            logger.error(f"보고서 조회 실패: {str(e)}")
            return []

        finally:
            conn.close()

    def get_reports_by_stock(self, stock_code: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        특정 종목의 보고서 목록 조회

        Args:
            stock_code: 종목 코드
            limit: 최대 조회 개수

        Returns:
            List[Dict]: 보고서 목록
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT
                    id, stock_code, company_name, analysis_date,
                    analysis_method, created_at
                FROM analysis_reports
                WHERE stock_code = ?
                ORDER BY analysis_date DESC
                LIMIT ?
            """, (stock_code, limit))

            rows = cursor.fetchall()
            reports = [dict(row) for row in rows]

            logger.info(f"{stock_code} 보고서 {len(reports)}개 조회 완료")
            return reports

        except Exception as e:
            logger.error(f"종목별 보고서 조회 실패: {str(e)}")
            return []

        finally:
            conn.close()

    def load_full_report(self, report_id: int) -> Optional[Dict[str, Any]]:
        """
        보고서 전체 데이터 로드 (에이전트 분석 + 뉴스 + 대화 포함)

        Args:
            report_id: 보고서 ID

        Returns:
            Dict: 전체 보고서 데이터
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # 1. 메타데이터 조회
            cursor.execute("""
                SELECT * FROM analysis_reports WHERE id = ?
            """, (report_id,))

            row = cursor.fetchone()
            if not row:
                logger.warning(f"보고서를 찾을 수 없음: report_id={report_id}")
                return None

            report = dict(row)

            # 2. 에이전트 분석 조회
            cursor.execute("""
                SELECT agent_name, agent_content
                FROM agent_analyses
                WHERE report_id = ?
            """, (report_id,))

            agent_rows = cursor.fetchall()
            report["agent_summaries"] = {row["agent_name"]: row["agent_content"] for row in agent_rows}

            # 3. 뉴스 소스 조회
            cursor.execute("""
                SELECT source_type, title, url, pub_date
                FROM news_sources
                WHERE report_id = ? AND source_type = 'news'
            """, (report_id,))

            news_rows = cursor.fetchall()
            report["news_sources"] = [dict(row) for row in news_rows]

            # 4. 커뮤니티 소스 조회
            cursor.execute("""
                SELECT source_type, title, url, pub_date
                FROM news_sources
                WHERE report_id = ? AND source_type = 'community'
            """, (report_id,))

            community_rows = cursor.fetchall()
            report["community_sources"] = [dict(row) for row in community_rows]

            # 5. 대화 히스토리 조회
            cursor.execute("""
                SELECT role, content, timestamp
                FROM conversation_history
                WHERE report_id = ?
                ORDER BY timestamp ASC
            """, (report_id,))

            conversation_rows = cursor.fetchall()
            report["conversation_history"] = [dict(row) for row in conversation_rows]

            logger.info(f"✅ 보고서 전체 로드 완료: report_id={report_id}")
            return report

        except Exception as e:
            logger.error(f"보고서 로드 실패: {str(e)}")
            return None

        finally:
            conn.close()

    def delete_report(self, report_id: int) -> bool:
        """
        보고서 삭제 (연관 데이터 자동 삭제)

        Args:
            report_id: 보고서 ID

        Returns:
            bool: 삭제 성공 여부
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("DELETE FROM analysis_reports WHERE id = ?", (report_id,))
            conn.commit()

            logger.info(f"보고서 삭제 완료: report_id={report_id}")
            return True

        except Exception as e:
            conn.rollback()
            logger.error(f"보고서 삭제 실패: {str(e)}")
            return False

        finally:
            conn.close()

    def get_db_stats(self) -> Dict[str, int]:
        """
        데이터베이스 통계 조회

        Returns:
            Dict: 테이블별 레코드 수
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            stats = {}

            cursor.execute("SELECT COUNT(*) as count FROM analysis_reports")
            stats["total_reports"] = cursor.fetchone()["count"]

            cursor.execute("SELECT COUNT(*) as count FROM agent_analyses")
            stats["total_agent_analyses"] = cursor.fetchone()["count"]

            cursor.execute("SELECT COUNT(*) as count FROM news_sources")
            stats["total_news_sources"] = cursor.fetchone()["count"]

            cursor.execute("SELECT COUNT(*) as count FROM conversation_history")
            stats["total_conversations"] = cursor.fetchone()["count"]

            return stats

        except Exception as e:
            logger.error(f"DB 통계 조회 실패: {str(e)}")
            return {}

        finally:
            conn.close()


# 전역 DB 클라이언트 인스턴스 (싱글톤)
_db_client = None

def get_db_client() -> TuSimReportDB:
    """전역 DB 클라이언트 인스턴스 반환 (싱글톤)"""
    global _db_client
    if _db_client is None:
        _db_client = TuSimReportDB()
    return _db_client
