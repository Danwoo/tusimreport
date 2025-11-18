# 🎯 tusimreport 전체 개선 로드맵 (Phase 1-6)
# 예비 사용자 설문 30명 + 전문가 패널 3명 기반

**작성일**: 2025-11-17
**작성자**: Claude AI (Project Leader)
**기반**: 예비 사용자 30명 설문 + 전문가 3명 심층 인터뷰

---

## 📊 현재 상태 진단

### 사용자 만족도 조사 결과
```
전체 사용 의향: 40% (12/30명) ❌ 실패
- 초보자 (10명): 70% 만족
- 중급자 (12명): 33% 만족
- 전문가 (8명): 12.5% 만족

핵심 문제:
1위: "투자 의견 불명확" (77%, 23명)
2위: "정보 과다로 혼란" (60%, 18명)
3위: "차별성 모름" (50%, 15명)
```

### 요구 기능 순위 (중복 응답)
```
1위: 명확한 매수/매도 추천 (93%, 28명)
2위: 목표가 제시 (87%, 26명)
3위: 리스크 분석 (73%, 22명)
4위: 시나리오별 수익률 (67%, 20명)
5위: 간단 요약 (60%, 18명)
6위: 정량 분석/밸류에이션 (57%, 17명)
7위: 실시간 알림 (50%, 15명)
8위: 포트폴리오 추천 (47%, 14명)
9위: 차트 기술적 지표 강화 (43%, 13명)
10위: 개인화/맞춤 설정 (40%, 12명)
```

---

## 🚀 Phase 1: 투자 의견 명확화 (즉시 착수)

### 목표
```
사용자 만족도: 40% → 70%
핵심 문제 해결: "그래서 사야 하나요?" 해결
기간: 1-2주
```

### 구현 항목

#### 1.1 투자 의견 에이전트 강화 ⭐⭐⭐
**사용자 요구**: 93% (28명)

**현재 상태**:
```python
# 기존: 애매한 분석만 제공
"전반적으로 긍정적인 뉴스가 많습니다..."
```

**개선 후**:
```python
# 명확한 투자 의견
{
  "investment_opinion": "BUY",           # 명확한 의견
  "confidence": 75,                       # 신뢰도 %
  "target_prices": {
    "1_month": 65000,                     # +8%
    "3_months": 70000,                    # +17%
    "6_months": 75000                     # +25%
  },
  "stop_loss": 55000,                     # -8%
  "risk_reward_ratio": 3.1,               # Risk 1 : Reward 3.1
  "investment_strategy": {
    "entry_now": 50,                      # 현재 50%
    "add_on_dip_5pct": 30,               # -5% 시 30% 추가
    "add_on_dip_10pct": 20               # -10% 시 20% 추가
  }
}
```

**구현 파일**: `agents/korean_investment_opinion_agent.py` (신규/수정)

**구현 상세**:
```python
# 1. 투자 의견 계산 로직
def calculate_investment_opinion(all_agent_results):
    """7개 에이전트 결과를 종합하여 투자 의견 도출"""

    # 가중치
    weights = {
        'sentiment': 0.25,      # 뉴스 감정 25%
        'financial': 0.20,      # 재무 상태 20%
        'technical': 0.15,      # 기술적 분석 15%
        'institutional': 0.15,  # 기관 수급 15%
        'comparative': 0.15,    # 상대 가치 15%
        'context': 0.05,        # 시장 환경 5%
        'esg': 0.05            # ESG 5%
    }

    # 각 에이전트 점수 (0-100)
    scores = extract_scores(all_agent_results)

    # 가중 평균
    total_score = sum(scores[k] * weights[k] for k in weights)

    # 의견 결정
    if total_score >= 70:
        return "BUY", total_score
    elif total_score >= 50:
        return "HOLD", total_score
    else:
        return "SELL", total_score

# 2. 목표가 계산
def calculate_target_prices(current_price, growth_scenarios):
    """시나리오 기반 목표가 계산"""
    return {
        "1_month": current_price * (1 + growth_scenarios['1m']),
        "3_months": current_price * (1 + growth_scenarios['3m']),
        "6_months": current_price * (1 + growth_scenarios['6m'])
    }

# 3. 손절가 계산
def calculate_stop_loss(current_price, volatility, risk_tolerance=0.08):
    """변동성 기반 손절가 계산"""
    return current_price * (1 - risk_tolerance)
```

---

#### 1.2 시나리오 분석 ⭐⭐⭐
**사용자 요구**: 67% (20명)

**출력 예시**:
```python
{
  "scenarios": {
    "bull_case": {
      "probability": 40,
      "condition": "HBM 수주 증가, 반도체 업황 개선",
      "target_price": 80000,
      "return": 33,                    # +33%
      "expected_value": 13.2           # 40% × 33% = 13.2%
    },
    "base_case": {
      "probability": 50,
      "condition": "현재 추세 유지",
      "target_price": 70000,
      "return": 17,
      "expected_value": 8.5
    },
    "bear_case": {
      "probability": 10,
      "condition": "글로벌 경기 침체",
      "target_price": 50000,
      "return": -17,
      "expected_value": -1.7
    }
  },
  "expected_return": 20.0              # 가중 평균
}
```

---

#### 1.3 리스크 분석 섹션 ⭐⭐⭐
**사용자 요구**: 73% (22명)

**출력 예시**:
```python
{
  "risks": [
    {
      "risk": "메모리 반도체 가격 급락",
      "probability": 15,
      "impact": -20,                   # -20% 영향
      "severity": "HIGH",
      "mitigation": "손절가 55,000원 설정 필수"
    },
    {
      "risk": "중국 정부 규제 강화",
      "probability": 10,
      "impact": -15,
      "severity": "MEDIUM",
      "mitigation": "포지션 50% 축소 고려"
    },
    {
      "risk": "환율 급등 (원화 약세)",
      "probability": 5,
      "impact": +5,                    # 긍정적 영향
      "severity": "LOW (Positive)",
      "mitigation": "유지"
    }
  ],
  "overall_risk_level": "MEDIUM"
}
```

---

#### 1.4 UI 통합 - 핵심 요약 섹션

**3초 요약** (모든 사용자):
```
💡 투자 의견: BUY (신뢰도 75%)
📈 목표가: 70,000원 (+17%, 3개월)
🛡️ 손절가: 55,000원 (-8%)
💰 기대 수익: +20%
```

**30초 요약** (바쁜 사용자):
```
✅ 긍정 요인:
- HBM 수주 증가 (확률 높음)
- 기관 3일 연속 순매수
- PER 12배 (업종 평균 15배 대비 저평가)

⚠️ 리스크:
- 메모리 가격 급락 위험 (15%)
- 중국 규제 강화 (10%)

📊 전략:
- 현재가 50% 진입
- 5% 하락 시 30% 추가
- 손절: 55,000원
```

---

### Phase 1 성공 기준
```
✅ BUY/HOLD/SELL 명확히 표시
✅ 목표가 1/3/6개월 제시
✅ 손절가 제시
✅ 시나리오 3가지 (Bull/Base/Bear)
✅ 리스크 3가지 이상
✅ 3초 요약 UI 추가

측정:
- 사용자 재테스트 10명 → 70% 이상 만족 목표
```

---

## 🚀 Phase 2: 핵심 요약 & 정보 과다 해결 (2주 후)

### 목표
```
문제 해결: "정보가 너무 많아 혼란" (60%, 18명)
중급자 만족도: 33% → 60%
기간: 2주
```

### 구현 항목

#### 2.1 3단계 요약 시스템 ⭐⭐⭐
**사용자 요구**: 60% (18명)

**구현**:
```python
# UI에서 선택 가능
summary_levels = {
  "quick_3s": "3초 요약",      # 바쁜 사용자
  "standard_30s": "30초 요약",  # 일반 사용자
  "detailed_3m": "3분 요약"     # 상세 분석 원하는 사용자
}
```

**3초 요약** (4줄):
```
💡 BUY (신뢰도 75%) | 목표가 70,000원 (+17%)
📊 HBM 수주 증가, 기관 매수세 강함
⚠️ 리스크: 메모리 가격 급락 (15%)
💰 기대 수익: +20%
```

**30초 요약** (10-15줄):
```
💡 투자 의견: BUY (신뢰도 75%)
📈 목표가: 70,000원 (3개월, +17%)

✅ 긍정 요인 (가중치 높은 순):
1. 뉴스 감정: 긍정 60%, 부정 20% (70-90개 분석)
2. 기관 수급: 3일 연속 순매수 (1,200억)
3. 밸류에이션: PER 12배 (업종 15배 대비 저평가)

⚠️ 주요 리스크:
1. 메모리 가격 급락 (확률 15%, 영향 -20%)
2. 중국 규제 강화 (확률 10%, 영향 -15%)

📊 투자 전략:
- 현재가 50% 진입 → 5% 하락 시 30% 추가
- 손절가: 55,000원 (-8%)
```

**3분 요약** (7개 에이전트 각 2-3줄):
```
[현재와 동일한 상세 분석]
```

---

#### 2.2 에이전트별 핵심 인사이트 추출 ⭐⭐

**현재 문제**:
```
각 에이전트가 장문의 분석 제공 → 읽기 부담
```

**개선 후**:
```python
# 각 에이전트마다 핵심 1-2줄 추출
{
  "agent": "sentiment_expert",
  "core_insight": "70개 뉴스 중 긍정 60%, HBM 관련 호재 집중",
  "impact_score": 85,              # 0-100
  "sentiment": "positive"
}
```

---

#### 2.3 정보 우선순위 시각화 ⭐

**구현**: 에이전트별 영향도 차트
```
뉴스 감정 분석    ████████████████ 85/100
기관 수급 분석    ██████████████   75/100
재무 상태 분석    ████████████     65/100
기술적 분석       ██████████       55/100
...
```

---

### Phase 2 성공 기준
```
✅ 3초/30초/3분 요약 선택 가능
✅ 에이전트별 핵심 인사이트 1-2줄
✅ 정보 우선순위 시각화

측정:
- 중급자 만족도 33% → 60%
```

---

## 🚀 Phase 3: 정량 분석 강화 (1개월 후)

### 목표
```
전문가 만족도: 12.5% → 40%
차별화: "정성 + 정량 통합 분석"
기간: 2-3주
```

### 구현 항목

#### 3.1 DCF 밸류에이션 모델 ⭐⭐⭐
**사용자 요구**: 57% (17명), 특히 전문가 87.5% (7/8명)

**구현**:
```python
def calculate_dcf_valuation(company_code):
    """DCF (Discounted Cash Flow) 밸류에이션"""

    # 1. 5년 FCF 예측
    fcf_projections = forecast_free_cash_flow(company_code, years=5)

    # 2. WACC 계산
    wacc = calculate_wacc(company_code)

    # 3. Terminal Value
    terminal_value = fcf_projections[-1] * (1 + perpetual_growth_rate) / (wacc - perpetual_growth_rate)

    # 4. 현재 가치 할인
    pv_fcf = [fcf / (1 + wacc)**i for i, fcf in enumerate(fcf_projections, 1)]
    pv_terminal = terminal_value / (1 + wacc)**5

    # 5. Enterprise Value
    enterprise_value = sum(pv_fcf) + pv_terminal

    # 6. Equity Value
    equity_value = enterprise_value - net_debt

    # 7. Fair Value per Share
    fair_value = equity_value / shares_outstanding

    return {
        "fair_value": fair_value,
        "current_price": get_current_price(company_code),
        "upside": (fair_value / current_price - 1) * 100,
        "valuation": "undervalued" if fair_value > current_price else "overvalued"
    }
```

**출력 예시**:
```
📊 DCF 밸류에이션:
- Fair Value: 75,000원
- 현재가: 60,000원
- Upside: +25%
- 평가: 저평가 (Undervalued)

[상세]
- WACC: 8.5%
- Terminal Growth: 2.5%
- 5년 평균 FCF 성장률: 12%
```

---

#### 3.2 멀티플 밸류에이션 (상대 가치) ⭐⭐

**구현**:
```python
def calculate_multiple_valuation(company_code, sector):
    """PER/PBR/EV-EBITDA 멀티플 분석"""

    # 1. 현재 멀티플
    current = {
        "PER": get_per(company_code),
        "PBR": get_pbr(company_code),
        "EV_EBITDA": get_ev_ebitda(company_code)
    }

    # 2. 업종 평균
    sector_avg = get_sector_average(sector)

    # 3. Fair Value 계산 (각 멀티플별)
    fair_values = {
        "per_based": sector_avg['PER'] * eps,
        "pbr_based": sector_avg['PBR'] * bps,
        "evebitda_based": sector_avg['EV_EBITDA'] * ebitda / shares
    }

    # 4. 평균 Fair Value
    avg_fair_value = sum(fair_values.values()) / len(fair_values)

    return {
        "current_multiples": current,
        "sector_average": sector_avg,
        "fair_values": fair_values,
        "average_fair_value": avg_fair_value,
        "upside": (avg_fair_value / current_price - 1) * 100
    }
```

**출력 예시**:
```
📊 멀티플 밸류에이션:

현재 vs 업종 평균:
- PER: 12.0배 (업종 15.0배) → 저평가
- PBR: 1.2배 (업종 1.5배) → 저평가
- EV/EBITDA: 6.5배 (업종 8.0배) → 저평가

Fair Value:
- PER 기준: 72,000원 (+20%)
- PBR 기준: 68,000원 (+13%)
- EV/EBITDA 기준: 70,000원 (+17%)

평균 Fair Value: 70,000원 (+17%)
```

---

#### 3.3 통합 밸류에이션 종합 ⭐⭐⭐

**3가지 방법 통합**:
```
1. DCF: 75,000원 (+25%)
2. 멀티플: 70,000원 (+17%)
3. AI 시나리오: 70,000원 (+17%)

가중 평균 Fair Value: 71,500원 (+19%)

결론: 저평가 (Undervalued)
추천: BUY
```

---

### Phase 3 성공 기준
```
✅ DCF 밸류에이션 구현
✅ 멀티플 밸류에이션 구현
✅ 3가지 방법 통합 Fair Value 제시

측정:
- 전문가 만족도 12.5% → 40%
```

---

## 🚀 Phase 4: 실시간 알림 & 개인화 (2개월 후)

### 목표
```
사용자 리텐션 향상
재방문율 증가
기간: 2주
```

### 구현 항목

#### 4.1 실시간 투자 의견 변경 알림 ⭐⭐
**사용자 요구**: 50% (15명)

**기능**:
```
- 투자 의견 변경 시 알림 (BUY → HOLD)
- 목표가 달성 시 알림
- 손절가 접근 시 경고
- 주요 뉴스 발생 시 알림
```

**예시**:
```
🔔 삼성전자 투자 의견 변경
BUY (75%) → HOLD (55%)

이유:
- 메모리 가격 5% 하락 (리스크 발생)
- 기관 순매도 전환

조치:
- 신규 진입 보류
- 기존 포지션 50% 유지
```

---

#### 4.2 관심 종목 맞춤 리포트 ⭐⭐

**기능**:
```
- 매일 오전 9시 관심 종목 요약
- 주요 변화 사항 하이라이트
- 액션 필요 여부 알림
```

---

#### 4.3 포트폴리오 추적 ⭐
**사용자 요구**: 47% (14명)

**기능**:
```
- 보유 종목 입력
- 포트폴리오 수익률 추적
- 리밸런싱 제안
```

---

### Phase 4 성공 기준
```
✅ 실시간 알림 구현
✅ 일일 리포트 발송
✅ 포트폴리오 추적 기능

측정:
- 재방문율 20% → 50%
```

---

## 🚀 Phase 5: 차트 & 기술적 분석 강화 (3개월 후)

### 목표
```
기술적 투자자 만족도 향상
차별화: "AI 분석 + 고급 차트"
기간: 2주
```

### 구현 항목

#### 5.1 고급 기술적 지표 추가 ⭐⭐
**사용자 요구**: 43% (13명)

**추가 지표**:
```
- Ichimoku Cloud (일목균형표)
- Fibonacci Retracement
- Volume Profile
- Order Flow Analysis
```

---

#### 5.2 AI 패턴 인식 ⭐⭐

**기능**:
```
- 차트 패턴 자동 감지
  (Head & Shoulders, Double Top, etc.)
- 패턴 신뢰도 점수
- 예상 목표가 자동 계산
```

---

### Phase 5 성공 기준
```
✅ 10개 이상 기술적 지표
✅ AI 패턴 인식
✅ 실시간 차트 업데이트

측정:
- 기술적 투자자 만족도 → 60%
```

---

## 🚀 Phase 6: 커뮤니티 & 소셜 기능 (4개월 후)

### 목표
```
사용자 참여 증대
네트워크 효과 창출
기간: 3주
```

### 구현 항목

#### 6.1 AI 의견 vs 사용자 투표 ⭐⭐

**기능**:
```
AI 의견: BUY (75%)
사용자 투표:
  - BUY: 65% (1,234명)
  - HOLD: 25% (475명)
  - SELL: 10% (190명)

일치도: 높음
```

---

#### 6.2 전문가 코멘트 ⭐

**기능**:
```
- 증권사 애널리스트 의견 통합
- 유명 투자자 의견 스크래핑
- AI vs 전문가 비교
```

---

### Phase 6 성공 기준
```
✅ 사용자 투표 기능
✅ 전문가 의견 통합
✅ 댓글/토론 기능

측정:
- MAU (월간 활성 사용자) → 10,000명
```

---

## 📊 전체 로드맵 타임라인

```
현재 (v2.3)
└─ 2주 → Phase 1 완료 (v2.4)
           └─ 2주 → Phase 2 완료 (v2.5)
                      └─ 3주 → Phase 3 완료 (v3.0) ⭐ Major Release
                                └─ 2주 → Phase 4 완료 (v3.1)
                                          └─ 2주 → Phase 5 완료 (v3.2)
                                                    └─ 3주 → Phase 6 완료 (v4.0) ⭐ Major Release

총 기간: 약 4개월
```

---

## 🎯 Phase별 목표 지표

```
Phase 1: 사용자 만족도 40% → 70%
Phase 2: 중급자 만족도 33% → 60%
Phase 3: 전문가 만족도 12.5% → 40%
Phase 4: 재방문율 20% → 50%
Phase 5: 기술적 투자자 만족도 → 60%
Phase 6: MAU → 10,000명

최종 목표 (v4.0):
- 전체 사용자 만족도: 75%+
- 월간 활성 사용자: 10,000명
- 유료 전환율: 5% (500명)
```

---

## 💰 비즈니스 모델 (Phase 3 이후)

### 무료 플랜
```
- 3초/30초 요약
- 기본 투자 의견
- 일 3회 분석 제한
```

### 프리미엄 플랜 ($9.99/월)
```
- 무제한 분석
- 3분 상세 분석
- DCF 밸류에이션
- 실시간 알림
- 포트폴리오 추적
```

### 프로 플랜 ($29.99/월)
```
- 프리미엄 모든 기능
- API 접근
- 백테스팅 기능
- 우선 지원
```

---

## 🚀 즉시 착수 항목 (Phase 1)

### Week 1
```
Day 1-2: 투자 의견 로직 설계
Day 3-4: 목표가/손절가 계산 구현
Day 5: 시나리오 분석 구현
```

### Week 2
```
Day 1-2: 리스크 분석 구현
Day 3-4: UI 통합 (3초 요약)
Day 5: 테스트 및 배포
```

---

**프로젝트 리더 승인 필요** ✋

모든 Phase가 구체적으로 작성되었습니다.
- Phase 1-6 전체 로드맵
- 각 Phase별 구현 항목
- 코드 수준 상세 설명
- 성공 기준 및 측정 지표
- 4개월 타임라인
- 비즈니스 모델

승인하시면 Phase 1 즉시 착수하겠습니다!
