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

    # =========================================================================
    # 推荐系统（local/31 §4.4 配置汇总 + local/32 六维拷问修订；依据 local/26~32）
    # 注意：env 前缀 APP_（APP_SKILL_WINDOW_SIZE 等）；所有值进配置，不写死。
    # =========================================================================

    # ---- 体系一：用户水平动态评价（user_skill_state 更新） ----
    skill_window_size: int = 10  # 有效评分样本窗口（local/27 §2；local/32 A-4.3 维持 10）
    skill_min_samples: int = 5  # 冷启动退出阈值（n<5 时定档分主导）
    skill_blend_placement: float = 0.7  # 冷启动期定档分起始权重（w(n)=max(0.3, 0.7-0.1n)）
    skill_blend_step: float = 0.1  # 每样本权重衰减步长
    skill_placement_holdout: float = 0.15  # 满窗后定档分残余权重（f）
    skill_placement_floor: float = 0.10  # 权重下限（local/32 A-4.1：防 f 无限衰减架空定档锚定）
    skill_forgetting_halflife_days: float = 60.0  # 遗忘半衰期（天）
    skill_confidence_min: float = 0.35  # 推荐定级回退阈值 CONF_MIN（< 此值回退 cefr_level）
    skill_band_hysteresis: float = 3.0  # 滞回带 [thr-h,thr)：升即时/降需 <thr-h（local/30 §7）
    skill_difficulty_normalize: bool = True  # 练习分难度归一化开关（素材共标校正）
    skill_slump_streak: int = 2  # 连续降级触发低谷保护的次数（local/32 A-3.2）
    skill_slump_cooldown_days: int = 7  # 低谷冻结时长（天，冻结期内档位不动）
    skill_trend_window: int = 5  # 趋势响应窗口（近N vs 前N，local/32 A-4.3）
    skill_trend_threshold: float = 5.0  # 趋势切换阈值（均值差 ≥ 此值才切窗口）
    skill_max_downgrade_per_update: float = 5.0  # 单次水平降幅钳制（|Δ低| ≤ 此值；升不限速）
    skill_callback_enabled: bool = False  # 动态档回写 Java（默认关=考试专属；开则带重试队列）
    skill_callback_retry_max: int = 6  # 回调重试上限（local/32 A-2.1）
    skill_callback_backoff_base_s: int = 5  # 回调重试退避基数（秒）
    reconcile_schedule_s: int = 30  # 对账/重试轮询间隔（秒）

    # ---- 体系二：素材难度评价（material_difficulty） ----
    material_difficulty_lambda: float = 0.5  # 场景难度聚合 λ（mean + λ·(max-mean)，local/27 §1）
    difficulty_w_vocab: float = 0.4  # 场景词汇维度权重（local/32 A-1.3 三维度：口语输出负荷为主）
    difficulty_w_syntax: float = 0.2  # 场景句法维度权重（A-1.3 补全）
    difficulty_w_pron: float = 0.4  # 场景发音维度权重
    shadow_w_wps: float = 0.4  # 影子跟读：语速权重（local/28 §2.2）
    shadow_w_pause: float = 0.3  # 停顿密度权重
    shadow_w_link: float = 0.3  # 连读密度权重
    calibration_min_n: int = 30  # 标定触发阈值：样本数（local/28 §3.3）
    calibration_min_users: int = 5  # 标定触发阈值：去重用户数
    calibration_max_user_share: float = 0.3  # 标定触发阈值：单用户样本占比上限
    calibration_kappa: float = 10.0  # 贝叶斯先验伪计数
    calibration_cap: int = 500  # 标定样本上限（防极端样本量压垮先验）
    skill_anchor_score: float = 75.0  # 达标线 S≥75（与 anchor_rate 成对变更）
    skill_anchor_rate: float = 0.75  # 达标率锚点（难度 = 达标率0.75 的能力分）

    # ---- 体系三：匹配/推荐（recommend_*） ----
    rec_cache_ttl_s: int = 3600  # 推荐缓存 TTL（local/32 A-2.4 改 1h + 主动失效）
    rec_limit_scenes: int = 6  # 场景推荐条数
    rec_limit_shadow: int = 3  # 影子跟读推荐条数
    review_gap_days: int = 7  # 复习席间隔窗口（天；已练且 ≥ 此天数才进复习席）
    review_ratio: float = 0.33  # 复习席占比（limit 的 1/3）
    review_mastery_threshold: float = 0.8  # 复习席触发：mastered 占比 ≥ 此值（local/32 A-4.4）


@lru_cache
def get_settings() -> Settings:
    return Settings()
