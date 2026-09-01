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
    jwt_secret: str = "vocalverse-dev-jwt-secret-0123456789abcdef"
    jwt_algorithm: str = "HS256"
    service_token: str = "change-me-internal-service-token"
    java_base_url: str = "http://localhost:8080"

    # LLM
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"

    # 语音
    asr_model: str = "small"  # faster-whisper 模型规格
    asr_device: str = "cpu"  # cpu | cuda
    asr_compute_type: str = "int8"
    tts_provider: str = "edge"  # edge | azure
    tts_voice: str = "en-US-JennyNeural"
    tts_rate: str = "+0%"
    azure_tts_key: str = ""  # 存在时切 Azure，见 docs/06 第 8 章
    ise_app_id: str = ""  # 讯飞评测 API（基线）
    ise_api_key: str = ""
    ise_api_secret: str = ""

    # 限制（见 docs/api/error-codes.md）
    max_upload_bytes: int = 20 * 1024 * 1024  # 20MB
    # 音频下界（40002）：挡住「空/近空录音」。前端停止键可用后，误触会产出 ~0ms 的 webm，
    # 落库即推进题目/回合且不可重来；1KB 约等于不到半秒的 opus，正常作答不会触到。
    min_upload_bytes: int = 1024
    max_speech_seconds: int = 60
    max_sing_seconds: int = 180
    max_dialog_seconds: int = 15  # 对话单轮录音上限（docs/14 §3.2）
    dialog_idle_seconds: int = 8  # 无录音救援触发（docs/14 §2.3）
    # 限流（docs/06 §7：30 次/时；POC 失败回退两调用时提高至 60）
    llm_rate_per_hour: int = 30
    asr_rate_per_hour: int = 60
    ise_rate_per_hour: int = 60
    tts_rate_per_hour: int = 60

    # 音频保留（合规：默认 24h 清理）
    audio_ttl_hours: int = 24
    audio_dir: str = "./data/audio"  # 本地卷存储（docs/06 §8）


@lru_cache
def get_settings() -> Settings:
    return Settings()
