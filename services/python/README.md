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

## 关键约定（详见 docs/06）

- CI 零真实 API Key：ASR/TTS/评分/LLM 走 `app/audio/base.py` 接口 + `app/audio/stubs.py` Fake
- 语音热路径直连 Python（前端→Python 8000；Java 只做管理端 8080）
- 录音默认不持久化，音频 24h TTL；红线：密钥/真实数据/模型权重/原始音频不入库
