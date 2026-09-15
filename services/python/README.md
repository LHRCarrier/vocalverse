# VocalVerse Python API —— 本地开发与 CI 说明

## 开发（Windows）

```powershell
# 前置：Python 3.12、uv（https://docs.astral.sh/uv/）、ffmpeg（winget install ffmpeg）
cd services/python
uv sync              # 首次生成 uv.lock（CI 使用 --frozen，锁文件必须入库）
cp .env.example .env # 填写密钥
python -m uvicorn app.main:app --reload --port 8000
# 文档：http://localhost:8000/docs
```

> 注意：`torch` 通过 `pyproject.toml` 的 pytorch-cpu index 安装 CPU 版，未装 CUDA。

## 测试

```powershell
uv run pytest -m "not gpu" -q   # CI 同款
```

## 迁移（Alembic 唯一 schema 真源）

```powershell
uv run alembic revision --autogenerate -m "init"   # 首迁移
uv run alembic upgrade head
```

## 基准脚本（va-09：语音链路分阶段基准，答辩「3~5s 反馈」证据）

`../../scripts/bench/pipeline_bench.py`——分阶段计时 upload → ffmpeg → ASR(words) →
LLM ttfa → TTS 首声 → 排播，输出 mean/p50/p95/RTF + 峰值内存 + 预算判定。

```powershell
# 真实基准（faster-whisper small + DeepSeek + edge-tts；需 .env 密钥与本地模型）
uv run python ../../scripts/bench/pipeline_bench.py --speech --runs 3 --check-budget
# CI/冒烟（Fake 客户端，零模型零 Key；CI 门禁同款）
uv run python ../../scripts/bench/pipeline_bench.py --fake --runs 3 --check-budget
```

判定：RTF ≤0.6 → 演示话术「3~5s 反馈」；0.6~0.8 → 「5~8s」（docs/06 §8 延迟表口径）。

## 关键约定（详见 docs/06）

- CI 零真实 API Key：ASR/TTS/评分/LLM 走 `app/audio/base.py` 接口 + `app/audio/stubs.py` Fake
- 语音热路径直连 Python（前端→Python 8000；Java 只做管理端 8080）
- 录音默认不持久化，音频 24h TTL；红线：密钥/真实数据/模型权重/原始音频不入库
