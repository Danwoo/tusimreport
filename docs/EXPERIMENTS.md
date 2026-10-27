# 멀티에이전트 구조 비교 실험

이 문서는 `docs/PROJECT_PLAN.md` 4단계("리포트 품질과 구조의 효과 평가")의 방법을 정의한다.

## 1. 질문

같은 데이터·같은 도구·같은 보고서 형식 위에서 **오케스트레이션 구조만 바꾸면** 보고서 품질, 비용, 실패에 대한 견고성이 어떻게 달라지는가.

가장 먼저 답할 질문은 다음이다. 9개 전문 에이전트로 나눈 지금의 구조가 도구를 모두 가진 단일 에이전트보다 나은가. 낫다면 무엇이 낫고, 그 대가로 무엇을 더 쓰는가.

## 2. 비교 대상

세 구조의 차이는 **"다음에 무엇을 할지 누가 정하는가"**와 **"에이전트 사이에 무엇이 오가는가"**다.

| topology | 실행 순서를 정하는 주체 | 전문가 간 정보 전달 | 보고서 작성 |
|---|---|---|---|
| `single_agent` | LLM 하나 (ReAct 루프) | 없음 (한 컨텍스트에 모든 도구 결과가 쌓인다) | 같은 에이전트가 직접 |
| `progressive` | 코드 (병렬 7개 → 순차 2개) | 순차 2개가 병렬 7개의 요약을 참고 정보로 받는다 | 별도 보고서 작성기 |
| `supervisor` | supervisor LLM (handoff) | supervisor의 메시지 이력 | 별도 보고서 작성기 (progressive와 동일) |

```text
single_agent   사용자 요청 ─▶ [ReAct 에이전트 + 도구 14개] ─▶ 보고서

progressive    사용자 요청 ─▶ ┌ context ┐
                              │ sentiment │
                              │ technical │  (병렬)
                              │ ... 7개   │ ─▶ financial ─▶ comparative ─▶ 보고서 작성기
                              └──────────┘      (순차, 병렬 결과를 참고)

supervisor     사용자 요청 ─▶ supervisor LLM ⇄ 전문가 9개 (handoff, 순서는 LLM이 결정)
                              ─▶ 보고서 작성기
```

용어 정리:

- **workflow**: 실행 경로를 코드가 미리 정한 구조다. `progressive`의 조율부가 여기에 해당한다.
- **agent**: LLM이 다음 행동(어떤 도구를 부를지, 언제 멈출지)을 스스로 정하는 구조다.
- `progressive`는 orchestrator-workers 형태다. 조율은 workflow이고, 각 전문가는 ReAct agent다.
- `supervisor`는 조율까지 LLM에 맡긴다.
- `single_agent`는 분업 자체가 없는 기준선이다.

## 3. 고정하는 것 (통제 변수)

| 항목 | 고정 방법 |
|---|---|
| 도구 | 세 구조 모두 `lab/tool_registry.py`의 같은 14개 도구를 쓴다 |
| 데이터 | `--snapshot-mode record`로 한 번 받은 도구 결과를 `replay`로 돌려준다. 외부 API를 다시 호출하지 않는다 |
| LLM | 실행마다 provider, 모델, endpoint host, 분당 호출 제한, temperature를 레코드(`llm`)에 남긴다. 비교는 같은 값끼리만 한다 |
| temperature | 에이전트 코드는 0, 0.1, 0.3을 섞어 쓴다. 실험 중에는 `config/llm_factory.temperature_override`가 모든 LLM(전문가, supervisor, 보고서 작성기, 단일 에이전트)을 한 값으로 고정한다. 기본 0.0, `--temperature`로 바꾼다 |
| 단계 한도 | 전문가 하나에 25단계(`core.signals.AGENT_RECURSION_LIMIT`)를 기준으로 맞춘다. 아래 표. 레코드의 `notes.step_budget`에 남는다 |
| 보고서 형식 | 같은 템플릿(`REPORT_GUIDE`, `REPORT_TEMPLATE`)과 근거 규칙(`GROUNDING_RULE`)을 쓴다 |
| 보고서 생성 조건 | `progressive`·`supervisor`는 근거 데이터가 있는 전문가가 5개(과반) 이상일 때만 보고서를 만든다 |

`single_agent`에는 전문가 단위가 없어서 생성 조건을 적용하지 않는다. 이 비대칭은 7절에서 다룬다.

**단계 한도** (LangGraph `recursion_limit`. LLM 호출 한 번과 도구 노드 실행 한 번(한 턴에 요청한 도구 호출 묶음)이 각각 한 단계다)

| topology | 한도 |
|---|---|
| `single_agent` | 그래프 전체 225 (25 × 9). 9개 영역을 한 그래프에서 다루므로 전문가 9명 몫을 준다 |
| `progressive` | 전문가마다 25. 엔진이 전문가 그래프를 따로 실행한다 |
| `supervisor` | supervisor 그래프 225. LangGraph는 같은 config를 하위 그래프에 넘기고 단계를 따로 세므로, 전문가 하나도 최대 225단계를 쓸 수 있다 |

`single_agent`가 한도를 다 쓰면 LangGraph는 "Sorry, need more steps to process this request."를 마지막 메시지로 돌려준다. 이 문구나 `GraphRecursionError`로 끝난 실행은 보고서가 아니라 오류로 기록한다. supervisor 아래 전문가가 한도를 다 쓰면 그 전문가는 분석이 없는 것으로 보고(`excluded`에 "분석 없음") 보고서 입력에서 뺀다. supervisor 그래프 전체가 한도에 닿으면(`GraphRecursionError`) 보고서를 만들지 않고 오류로 기록한다. 그때까지 모인 전문가 호출·분석·제외 사유는 `notes`에 남기고 `notes.supervisor_hit_step_limit`을 참으로 둔다.

## 4. 지표

| 지표 | 정의 | 출처 |
|---|---|---|
| 성공 | 보고서가 있고 오류가 없다. 보고서 작성기가 실패하면(`ReportGenerationError`) 그 사유가 실행의 오류가 된다 | `RunRecord.succeeded` |
| 시간 | 실행 시작부터 끝까지의 경과 초 | `elapsed_s` |
| LLM 호출·토큰 | LLM 호출 수, 입력·출력 토큰. 도구 안에서 다시 부르는 LLM 호출도 포함한다. 제공자가 `usage`를 주지 않은 응답 수는 `llm_calls_without_usage`로 따로 센다 | `core/run_metrics.py` 콜백, 제공자가 돌려준 `usage` |
| 도구 호출 | 아래 두 계측 | `core/run_metrics.py`, `lab/snapshot.py` |
| 커버리지 | 보고서에 들어간 전문가 영역 수 / 9. 도구 단위 커버리지는 `tool_coverage`로 따로 남긴다 | `lab/runner.py` |
| 숫자 근거 일치율 | 보고서의 숫자 중 보고서에 들어간 전문가의 도구 결과에 있는 값의 비율 | `lab/grounding.py` |

**도구 호출의 두 계측**

두 숫자는 세는 시점이 달라 같지 않을 수 있다. 요약표에 나란히 둔다.

| 요약표 열 | 레코드 | 세는 것 |
|---|---|---|
| 도구 호출(콜백) | `stats.tool_calls` | LangChain이 시작한 데이터 도구 호출. 인자 검증에서 막혀 도구 함수가 실행되지 않은 호출도 들어간다 |
| 인자 오류 | `stats.tool_arg_errors` | 위 호출 중 인자 검증에서 막힌 수. `stats.tool_errors`(도구 오류 전체)에도 들어간다 |
| handoff | `stats.handoffs` | supervisor가 전문가에게 일을 넘긴 호출(`transfer_to_*`). 데이터 도구가 아니라 `tool_calls`에서 뺀다 |
| 기록된 도구 호출(데이터/전체) | `tool_calls.with_data`, `tool_calls.calls` | 도구 함수까지 도달한 호출(replay에서는 스냅샷을 찾은 호출과 못 찾은 호출 모두). 오류 수(예외·스냅샷 누락·손상)와 출처별 수(live / snapshot / snapshot_fuzzy / missing / corrupt)도 남긴다 |

모든 도구가 계측되어 있으면 `stats.tool_calls - stats.tool_arg_errors`가 `tool_calls.calls`와 같다. LLM이 없는 도구 이름을 부르면 도구가 시작되지 않으므로 어느 쪽에도 잡히지 않는다.

토큰 열은 `usage` 없는 응답이 있으면 합계 앞에 `≥`를 붙이고 그 횟수를 적는다. 모든 응답에 `usage`가 없으면 `n/a`다.

**커버리지**

- `progressive`·`supervisor`: 보고서 작성기에 분석이 들어간 전문가(`notes.grounded_agents`, `coverage.basis = "report_inputs"`)를 센다. 실행이 예외 없이 끝났고 도구 결과에 근거 데이터가 있는 전문가다. 도구는 데이터를 받았지만 마지막 LLM 호출이 실패한 전문가는 여기서 빠진다. 보고서 작성기가 실패한 실행도 들어갔을 전문가를 센다.
- `single_agent`: 전문가 단위가 없어서 근거 데이터를 하나라도 받은 도구의 담당 영역을 센다(`basis = "tool_calls"`).
- 세 구조 모두 `tool_coverage`에 도구 단위 값이 있다. 구조끼리 비교할 때는 `tool_coverage`가 같은 기준이고, `coverage`는 보고서가 실제로 다룬 범위다.

**숫자 근거 일치율의 계산**

- 보고서에서 숫자를 뽑는다. 날짜·시각, 연도, 기간(20일, 3분기, 52주 등), 개수·순번(10 이하 정수), 종목코드는 제외한다. 연도는 쉼표·단위·소수점·'원'이 없는 네 자리 수(1900~2100)만이다. '2,050원'은 값으로 검사한다.
- '6조 5,670억원'처럼 큰 단위부터 이어 쓴 값은 하나(6.567조)로 합친다.
- 단위(조·억·만, %)를 맞춰 도구 결과의 숫자와 비교한다. 비교 대상은 `progressive`·`supervisor`에서는 보고서에 들어간 전문가의 도구 결과, `single_agent`에서는 모든 도구 결과다.
- 도구 결과에서 날짜·시각 키(`last_updated`, `timestamp`, `*_date`, `pub_date`, `rcept_dt`, `recorded_at` 등)의 값, 문자열 전체가 날짜·시각인 값, 문장 속 날짜·기간 표현, 코드가 만든 요약·사유 문구는 숫자로 쓰지 않는다.
- 허용 오차는 보고서에 표시된 자릿수의 반올림 범위와 0.5% 중 큰 값이다.
- 퍼센트로 쓴 숫자만 비율과 같은 값으로 본다(0.025 ↔ 2.5%). 퍼센트가 아닌 숫자는 100배·100분의 1로 바꿔 맞추지 않는다.
- 숫자 앞뒤 15자 안에 방향어(하락, 상승, 순매도, 순매수, 감소, 증가 등)가 있으면 부호를 보지 않는다('3.52% 하락' ↔ -3.52). 방향어가 없으면 부호까지 맞아야 한다.

**이 지표가 뜻하는 것**

이 비율은 "검사 대상 숫자 중 비교 대상 도구 결과 어딘가에 같은 값이 있는 비율"이다. 값만 맞추고 의미는 보지 않으므로 사실 정확도의 하한도 상한도 아니다.

- 낮게 잡는 쪽: 보고서 안에서 계산한 값(예: 고점 대비 하락률)은 도구 결과에 그대로 없으므로 근거 없음이 된다.
- 높게 잡는 쪽: 다른 의미의 같은 값이 도구 결과에 있으면 근거 있음이 된다. 0.5% 상대 오차와 방향어 근처의 부호 무시도 같은 쪽으로 작용한다. 날짜·시각을 빼고 100배 환산을 퍼센트로 한정한 것은 이 쪽을 줄이기 위해서다.
- 검사하지 않는 것: 제외 규칙에 걸린 숫자와 숫자가 아닌 주장(예: "업황이 개선되고 있다").

**아직 없는 지표**

- 숫자가 아닌 주장의 근거 여부와 보고서의 유용성은 별도 평가가 필요하다. 후보는 사람이 확인하는 고정 질문 세트와, 판정 전용 모델(예: TypeSafe Jev의 Choice/Score 질문)이다.
- 판정 모델을 쓰면 자동 채점과 사람 확인을 구분해 기록한다.

## 5. 실행 방법

사전 준비는 `docs/API_KEYS.md`대로 키를 넣고, `python setup_check.py --llm-probe`로 tool calling을 확인하는 것이다.

```bash
# 1) 실데이터로 세 구조를 한 번씩 돌려 도구 결과를 새 디렉터리에 한 세션으로 남긴다
python scripts/run_experiment.py --stocks 005930:삼성전자 --snapshot-mode record --snapshot-dir snapshots/2026-10-27

# 2) 같은 스냅샷으로 세 구조를 비교한다 (데이터 API 호출 없음, LLM만 호출)
python scripts/run_experiment.py --stocks 005930:삼성전자 --snapshot-mode replay --snapshot-dir snapshots/2026-10-27 --repeats 3
```

- 결과는 `runs/experiments/<시각>/`에 실행별 JSON, `results.jsonl`, `summary.md`로 남는다.
- 1)은 세 구조를 모두 돌려야 구조마다 다르게 부르는 도구(예: 단일 에이전트가 고른 차트·업종 도구)가 스냅샷에 남는다. 장중에는 구조 사이에 시세가 바뀌므로 장 마감 뒤에 기록한다.
- 2)의 요약표에서 `스냅샷 근사/누락/손상` 중 하나라도 0이 아니면 새 디렉터리에 1)을 다시 돌린다. 기존 디렉터리에 덧붙여 기록하면 서로 다른 시점의 데이터가 섞인다(7절).
- `--temperature`(기본 0.0)는 실행 중 모든 LLM의 temperature를 고정한다. 레코드의 `llm.temperature`에 남는다.
- 무료 등급이면 `LLM_MAX_REQUESTS_PER_MINUTE`를 제공자 한도보다 낮게 둔다(KiraAI는 25).
- `snapshots/`와 `runs/`에는 외부 소스의 원자료가 들어 있어 `.gitignore` 대상이다. 공개 저장소에 올리지 않는다. 결과를 공유할 때는 집계 수치만 옮긴다.

## 6. 결과

**아직 측정하지 않았다.** 키를 등록한 뒤 첫 측정 결과를 아래 형식으로 기록한다. 측정 일시, 종목, 반복 횟수, LLM(제공자·모델·temperature), 스냅샷 기록 시각 범위를 함께 적는다.

| topology | 성공 | 시간(s) | LLM 호출 | 입력/출력 토큰 | 도구 호출(콜백 / 기록) | handoff | 커버리지(보고서 / 도구) | 숫자 근거 |
|---|---|---|---|---|---|---|---|---|
| single_agent | | | | | | | | |
| progressive | | | | | | | | |
| supervisor | | | | | | | | |

## 7. 해석할 때 주의할 점

- **모델 한계가 구조 차이를 덮을 수 있다.** 무료 소형 모델은 tool calling과 긴 지시 따르기가 약하다. 특히 `supervisor`는 LLM이 handoff 순서를 정해야 하므로 모델 성능에 가장 민감하다. 결과를 구조의 장단점으로 일반화하기 전에 모델을 바꿔 다시 잰다.
- **반복이 적으면 분산이 크다.** temperature를 0으로 고정해도 제공자 쪽 비결정성이 남고 LLM이 도구 호출 순서를 바꾼다. 같은 조건을 최소 3회 반복하고, 평균과 범위를 함께 적는다.
- **보고서 생성 조건이 비대칭이다.** `single_agent`는 근거가 부족해도 보고서를 쓴다. 그래서 성공률만 보면 단일 에이전트가 유리해 보일 수 있다. 커버리지와 숫자 근거 일치율을 함께 본다.
- **커버리지와 숫자 근거의 기준이 비대칭이다.** `progressive`·`supervisor`는 보고서에 들어간 전문가만 세고 그 도구 결과와만 대조한다. `single_agent`는 모든 도구 결과를 쓴다. 구조끼리 같은 기준으로 볼 때는 `tool_coverage`를 쓴다.
- **단계 한도가 완전히 같지는 않다.** `supervisor`의 전문가는 하위 그래프로 실행되어 각자 225단계까지 쓸 수 있고, `progressive`의 전문가는 25단계다. 단계 한도에 걸린 실행이 있으면 레코드의 `error`·`notes.excluded`로 확인한다.
- **분당 호출 제한을 켜면 시간 비교가 왜곡된다.** limiter가 호출을 기다리게 하므로, 호출이 많은 구조일수록 시간이 늘어난다. 이 경우 시간보다 LLM 호출 수와 토큰을 비교한다.
- **스냅샷 근사 일치.** replay에서 인자가 정확히 같지 않을 때, 회사명 표기처럼 이름 인자(`company_name` 등)만 다르면 같은 종목·같은 조건의 최근 기록을 돌려주고 `snapshot_fuzzy`로 센다. 도구가 읽지 않는 인자(`save_stock_chart`의 `chart_data`)는 비교에서 아예 빼므로 정확한 일치로 센다. 생략한 인자는 도구 기본값으로 채워 비교하므로 `period_days=20`을 생략한 호출과 명시한 호출은 같다. 그 밖의 인자(`stock_code`, `period_days` 등)가 다르면 누락(`missing`)이다.
- **비교에서 빼는 실행.** 다음 중 하나라도 해당하면 그 실행은 데이터 조건이 달랐던 것이므로 비교에서 뺀다.
  - 요약표의 `스냅샷 근사/누락/손상`이 하나라도 0이 아니다(`tool_calls.by_source`의 snapshot_fuzzy, missing, corrupt).
  - `스냅샷 기록 시각`(`tool_calls.recorded_at`의 최소·최대)이 한 번의 record 실행 범위를 넘는다. record 실행의 범위는 그 실행이 남긴 레코드들의 `started_at`과 `elapsed_s`로 확인한다. 범위를 넘으면 서로 다른 세션에서 받은 데이터가 섞인 것이다.
  - 같은 비교 묶음 안에서 `llm`(provider, 모델, temperature)이 다르다.
- **단일 에이전트의 컨텍스트 한계.** 14개 도구 결과가 한 컨텍스트에 쌓인다. 모델의 컨텍스트 창이 작으면 이 구조만 잘리거나 실패할 수 있고, 그것 자체가 분업의 이유가 될 수 있다.

## 8. 관련 코드

| 경로 | 역할 |
|---|---|
| `lab/tool_registry.py` | 9개 에이전트 모듈의 도구를 한 곳에서 모은다 |
| `lab/snapshot.py` | 도구 호출 기록(담당 에이전트, 데이터 시각 포함), 스냅샷 기록·재생 |
| `lab/topologies.py` | 세 구조의 실행 함수 |
| `lab/grounding.py` | 숫자 근거 일치율 |
| `lab/runner.py` | 1회 실행과 결과 레코드 |
| `scripts/run_experiment.py` | 실험 실행기 |
| `core/run_metrics.py` | LLM·도구 호출 계측 콜백 (handoff·인자 오류·usage 누락을 따로 센다) |
| `config/llm_factory.py` | LLM 생성, 실험 중 temperature 고정(`temperature_override`) |
| `core/agent_status.py` | 에이전트별 근거 데이터 판정 |
