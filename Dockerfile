# Multi-stage Dockerfile for tusimreport.
#
# 디자인 노트:
# - 베이스는 python:3.11-slim (3.11이 명시 타깃, 3.12는 CI matrix에서만 검증).
# - builder 스테이지에서 시스템 패키지(컴파일 도구)를 받고 wheel 캐시를 만들고,
#   runtime 스테이지는 chromium(셀레늄)과 cjk 폰트(matplotlib 한글)만 들고
#   final 이미지 크기를 줄인다.
# - tini를 PID 1로 두어 SIGTERM이 streamlit 자식 프로세스까지 전달되도록 한다.
# - non-root 사용자로 실행. .env는 docker run 시점에 마운트하거나 환경변수로 주입.

# ============== Stage 1: builder ==============
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

# 빌드 시점에만 필요한 컴파일 도구. lxml/pandas 휠이 다 없는 경우 대비.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY requirements.txt .
# wheel을 한 디렉토리에 모아 runtime 스테이지로 복사. 컴파일 도구가 final에
# 따라가지 않도록 격리하는 게 목적.
RUN pip wheel --wheel-dir /build/wheels -r requirements.txt

# ============== Stage 2: runtime ==============
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    # Streamlit 캐시/usage stat 비활성 — 첫 실행이 컨테이너 안에서 매번 새로
    # 생기는 걸 방지하기 위함.
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    # matplotlib backend을 코드뿐 아니라 컨테이너 레벨에서도 강제.
    MPLBACKEND=Agg \
    # Selenium이 chromium 바이너리를 찾도록 명시.
    CHROME_BIN=/usr/bin/chromium \
    CHROMEDRIVER=/usr/bin/chromedriver

# 런타임 의존성:
#   chromium, chromedriver — paxnet/dcinside 셀레늄 크롤러
#   fonts-noto-cjk         — matplotlib 한글 차트
#   tini                   — PID 1 zombie reaper
#   ca-certificates        — TLS verify=True (RSS 화이트리스트 이외)
RUN apt-get update && apt-get install -y --no-install-recommends \
        chromium \
        chromium-driver \
        fonts-noto-cjk \
        tini \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# non-root 사용자. UID 1000은 호스트 마운트와 가장 흔히 일치.
RUN groupadd -g 1000 app && useradd -u 1000 -g app -m -s /bin/bash app

WORKDIR /app

COPY --from=builder /build/wheels /tmp/wheels
RUN pip install --no-index --find-links=/tmp/wheels /tmp/wheels/*.whl \
    && rm -rf /tmp/wheels

# 코드는 마지막에 복사 — requirements 변경이 없으면 위 레이어 캐시 재사용.
COPY --chown=app:app . /app

USER app

EXPOSE 8501

# Streamlit 자체 healthcheck endpoint. 컨테이너 헬스 모니터링에 사용.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; \
        sys.exit(0 if urllib.request.urlopen('http://localhost:8501/_stcore/health', timeout=3).status==200 else 1)"

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["streamlit", "run", "main.py"]
