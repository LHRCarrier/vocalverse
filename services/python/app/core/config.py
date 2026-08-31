"""集中配置（Pydantic Settings，读取 APP_ 前缀环境变量）。

约定（见 docs/06 第 11 章）：
- 根 .env（gitignored）+ 本目录 .env.example（占位符）
- `APP_TESTING=true` 时注入 Fake 音频/LLM 客户端，CI 零真实 API Key
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="APP_",
        env_file=(".env", ".env.local"),
        extra="ignore",
    )

    # 运行模式
    app_env: str = "development"  # development | test | production
    testing: bool = False
    log_level: str = "INFO"

    # 数据库 / 缓存
    database_url: str = "sqlite+pysqlite:///./vocalverse_dev.db"
    redis_url: str = "redis://localhost:6379/0"
    redis_required: bool = False  # False → 内存 fallback，省 Redis 也能起

    # 鉴权（Java 签发，Python 验签；内部调用 service-token）
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    service_token: str = "change-me-internal-service-token"

    # LLM
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"

    # 语音
    asr_model: str = "small"  # faster-whisper 模型规格
    asr_device: str = "cpu"  # cpu | cuda
    asr_compute_type: str = "int8"
    tts_provider: str = "edge"  # edge | azure
    azure_tts_key: str = ""  # 存在时切 Azure，见 docs/06 第 8 章
    ise_app_id: str = ""  # 讯飞评测 API（基线）
    ise_api_key: str = ""
    ise_api_secret: str = ""

    # 限制（见 docs/api/error-codes.md）
    max_upload_bytes: int = 20 * 1024 * 1024  # 20MB
    max_speech_seconds: int = 60
    max_sing_seconds: int = 180

    # 音频保留（合规：默认 24h 清理）
    audio_ttl_hours: int = 24


@lru_cache
def get_settings() -> Settings:
    return Settings()
