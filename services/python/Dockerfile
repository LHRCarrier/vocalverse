# Python 服务镜像（CPU + ffmpeg）
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# ffmpeg：WebM/opus → 16k WAV 转码必需（docs/06 第 12 章）
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# uv 安装依赖（锁文件冻结保证可复现；不允许回退分支掩盖 lock 失配）
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# ⚠️ 模型预下载进镜像（docs/06 §8 模型缓存 · 审计 R-11：容器网络到 HF 不可达 & 冷加载
# 500MB 超健康检查窗口；POC 备注 HF_DISABLE_XET=1 已规避）。权重严禁入库（.gitignore）——
# 由 scripts 层下载（本地 curl/CI step），缺失时本地构建会失败、CI 构建前置步骤补齐。
COPY .models-cache/huggingface /app/models/whisper-small

COPY . .

EXPOSE 8000
# --workers 1 显式声明（docs/06 §8：whisper 多 worker 各载 ~500MB 模型且并发收益为负）
# --limit-concurrency 10 = 全局限流闸（docs/19 P1-4 / 审计 R-10：应用层信号量之外的兜底护栏）
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--limit-concurrency", "10"]
