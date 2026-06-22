# 강의력 분석 서비스 — 멀티테넌트 Streamlit 앱
# KoNLPy(전처리)가 JVM 을 쓰므로 JRE 포함. ARM(t4g)·x86 모두 빌드됨.
FROM python:3.13-slim

# Java(KoNLPy/JPype) + 한글 폰트(matplotlib/PDF)
RUN apt-get update && apt-get install -y --no-install-recommends \
        default-jre-headless fonts-nanum curl \
    && rm -rf /var/lib/apt/lists/*

# Debian 의 JRE 경로(아키텍처별로 자동 링크). JPype 가 libjvm.so 를 찾도록.
ENV JAVA_HOME=/usr/lib/jvm/default-java
ENV PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt deploy/requirements-deploy.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-deploy.txt

# 앱 소스만 복사(.dockerignore 가 비공개 데이터·로컬 reports 제외)
COPY . /app

# 워크스페이스 데이터는 볼륨(/data)에 영속 — 컨테이너 교체에도 보존
ENV LECTURE_DATA_DIR=/data/workspaces
ENV LECTURE_QUOTA_MB=200
RUN mkdir -p /data/workspaces

EXPOSE 8503
HEALTHCHECK --interval=30s --timeout=5s \
    CMD curl -fs http://localhost:8503/_stcore/health || exit 1

CMD ["streamlit", "run", "service/app.py", \
     "--server.port=8503", "--server.address=0.0.0.0", \
     "--server.headless=true", "--server.enableCORS=false"]
