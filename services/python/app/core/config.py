"""集中配置（Pydantic Settings，读取 APP_ 前缀环境变量）。

约定（见 docs/06 第 11 章）：
- 根 .env（gitignored）+ 本目录 .env.example（占位符）
- `APP_TESTING=true` 时注入 Fake 音频/LLM 客户端，CI 零真实 API Key
- 密钥三档策略（docs/19 P0-9，组内拍板 2026-09-07）：testing → 固定测试值；
  development → 缺值仅告警；production → 缺值启动即失败（公开仓库不出现可用密钥）。
"""

from functools import lru_cache
from warnings import warn

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# 测试档固定值（docs/19 P0-9：CI 零真实 Key，docs/06 §5/§6 纪律；仅 APP_TESTING=true 生效）
TEST_JWT_SECRET = "vocalverse-test-jwt-secret-0123456789abcdef"
TEST_SERVICE_TOKEN = "vocalverse-test-internal-service-token"
# 控制台令牌测试值：与学习者令牌**不同**（docs/50 §4.1 双密钥），也是 audience 闸门的回归样本
TEST_CONSOLE_JWT_SECRET = "vocalverse-test-console-jwt-secret-0123456789"


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
    # 默认空串 + 三档校验（_resolve_secrets；docs/19 P0-9：禁止仓库出现可用密钥）
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    service_token: str = ""
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
    # 读书域 · 听书（docs/45 §5 · docs/46 B-3/B-4）：
    # - provider：auto（kitten 可用→kitten，否则 edge）/ edge / kitten；
    # - voice_models_dir：本地模型目录（默认空=不探测 kitten；填入 VoiceStudio
    #   models 目录（如 F:\WorkingL\VoiceStudio\OmniVoiceStudio-Data\data\models）
    #   即启用本地引擎；模型权重红线不入库，只做运行时引用；
    # - 听书 bucket 独立于 /tts（60/时）：听书一章 ~200 句，只扣真实合成
    #   次数（缓存命中 0 扣；prepared 按章扣 1），600/时留足余量。
    reading_tts_provider: str = "auto"  # auto | edge | kitten
    reading_tts_rate_per_hour: int = 600
    voice_models_dir: str = ""
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
    # 语言点命中（docs/14 §3.5）：规则通道（词序包含）权威；LLM 兜底命中默认**关闭**
    # （2026-09-07 真实 LLM 上线后误标「已使用」——宁漏勿误，需要语义级命中再开）。
    meta_llm_hits_enabled: bool = False
    # 限流（docs/06 §7：30 次/时；POC 失败回退两调用时提高至 60 - 沿用值不变）
    llm_rate_per_hour: int = 30
    asr_rate_per_hour: int = 60
    # 2026-09-09 唱歌 P0 D3 拍板：ISE 桶对齐 ADR 口径 30/h（R-16 闭合）
    ise_rate_per_hour: int = 30
    tts_rate_per_hour: int = 60
    # 唱歌独立子资源桶（docs/06 §7 注记 2026-09-09）：整首跟唱评分计 1 次/用户/时
    sing_rate_per_hour: int = 5
    # TTS 预合成缓存（docs/44 P1-B）：每键 TTL 与容量上限（写入时按 mtime 裁剪最旧）。
    # TTL 默认 24h 与 audio_ttl_hours 同窗；容量兜底防长时间运行/多参数组合撑爆磁盘。
    tts_cache_ttl_s: int = 86400
    tts_cache_max_mb: int = 512
    # SSE 心跳间隔（R-18 / 审计 R-18：协议上限 30s，取 15s 留一倍余量；
    # 静默 ≥ 此值推 ': ping' 注释行，防中间代理断流/客户端误判死链；0=关闭心跳）
    sse_heartbeat_seconds: float = 15.0

    # =========================================================================
    # 唱歌（docs/06 §9.4 + 2026-09-09 P0 D1~D7；local/唱歌P0六项实施计划书）
    # =========================================================================
    # 参考旋律提取器：pyin（librosa，65~800Hz/frame 2048/hop 512/清浊门限）；fake 仅测试
    pitch_extractor: str = "pyin"
    # 清浊叠加门限（0=只用 librosa voiced_flag，默认）：真人歌声 voicing prob 偏低
    # （2026-09-09 实测用户录音 max 0.43~0.76 / mean 0.01~0.04），叠加高门限会整句误判
    # 清音 → 全句 no_pitch；仅在需要更激进剔除静音时调高（0.2~0.3）。
    pitch_voicing_threshold: float = 0.0
    pitch_extract_concurrency: int = 2  # 提取并行信号量（与 whisper/ISE/sing 相互独立）
    pitch_extract_scan_interval_s: int = 60  # lifespan 周期扫描间隔（秒）
    pitch_extract_max_attempts: int = 3  # 单 job 重试上限（超限置 failed，不再自动重建）
    # 发音=整首抽样句（D3）：默认前 3 句 + weak 句优先；0 = 关闭发音维度（发音分 None）
    sing_pron_samples: int = 3
    sing_concurrency: int = 2  # 唱歌评分并发信号量（docs/06 §8⑤：CPU 密集排队不雪崩）

    # 音频保留（合规：默认 24h 清理）
    audio_ttl_hours: int = 24
    audio_dir: str = "./data/audio"  # 本地卷存储（docs/06 §8）

    # =========================================================================
    # 媒体（社区 S3 · docs/47 §4.1）：图片/视频/头像上传与读取
    # 存储口径与音频一致（本地卷 + 预留对象存储抽象，docs/06 §8）；
    # ⚠️ 视频上限改动必须同步 apps/web/nginx.conf 的 client_max_body_size
    #    （网关先于 Python 生效，否则容器链路 >20MB 直接 nginx 413 且响应非 Envelope，
    #     见 docs/48 B3）。
    # =========================================================================
    media_dir: str = "./data/media"
    # 视频 64MB（图片/头像沿用 max_upload_bytes 20MB）
    media_max_video_bytes: int = 64 * 1024 * 1024
    media_rate_per_hour: int = 60  # 上传限流桶（docs/47 §4.1）
    media_max_items_per_post: int = 9  # 单帖图片数上限（Java 侧同口径校验）
    media_max_dimension: int = 8192  # 宽/高上界
    media_max_duration_s: int = 600  # 视频时长上界（秒）
    # Java 只允许引用本前缀的媒体 URL（拒绝外链，docs/47 §4.3）
    media_url_prefix: str = "/api/v1/media/"

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

    # =========================================================================
    # LLM 框架层（docs/26：对齐 ai4u 分层；⑤前缀稳定 + ⑥学习者画像注入，docs/24）
    # 注意：env 前缀 APP_（APP_LEARNER_INJECTION_ENABLED 等）
    # =========================================================================
    learner_injection_enabled: bool = True  # ⑥ 画像注入总开关（默认开，可一键关闭回退）
    learner_max_items: int = 3  # 画像注入条数上限（≤3 防过度纠正，docs/24 拍板 P4）
    learner_cache_ttl_s: int = 900  # 画像进程内缓存 TTL（15min；会话收尾主动失效兜底）
    learner_word_error_window: int = 20  # 词级错误聚合窗口（最近 N 条 dialog attempt）

    # ---- Agent Lab（test-only 前端测试台，docs/26 §8；默认关闭，生产禁止开启） ----
    agent_lab_enabled: bool = False  # APP_AGENT_LAB_ENABLED=true 时注册 /api/v1/agent-lab/*

    # ---- 流利度特征测试台（test-only 前端联调页，docs/06 §9.3；默认关闭，生产禁止开启） ----
    fluency_preview_enabled: bool = False  # 开启时注册 /api/v1/fluency-preview/*

    # ---- 影子跟读测试台（test-only 前端联调页，DoD ④；默认关闭，生产禁止开启） ----
    shadow_preview_enabled: bool = False  # 开启时注册 /api/v1/shadow-preview/*

    # =========================================================================
    # 管理端控制台 · 运维/遥测（docs/50 §13.2；开关登记见 docs/06 §17，由组长登记）
    # 注意：env 前缀 APP_（APP_LLM_TRACE_ENABLED / APP_OPS_TELEMETRY_ENABLED 等）
    # =========================================================================

    # ---- 采集开关 ----
    # 结构采集（span 树/耗时/token/错误）默认开：不落正文，隐私风险低，是调优的基本盘。
    llm_trace_enabled: bool = True  # APP_LLM_TRACE_ENABLED
    # 内容捕获（prompt/response 正文）默认**关**：prompt 里可能带用户原话，属隐私敏感面；
    # 与 docs/06 §9.7「只存评分/转写/元数据」一致，开启属受控例外（另见 recorder 硬禁采清单）。
    llm_trace_content_capture: bool = False  # APP_LLM_TRACE_CONTENT_CAPTURE
    # 指标采集器（60s 桶）与预警评估；关掉后控制台 ops 端点返回 46014（前端可读降级）。
    ops_telemetry_enabled: bool = True  # APP_OPS_TELEMETRY_ENABLED

    # ---- 采集参数（阈值口径见 docs/50 §7.5 / §8.3，非开关、不进功能位登记表） ----
    llm_trace_sample_rate: float = 1.0  # 采样率（1.0=全采；<1 时按 trace 维度随机丢）
    llm_trace_content_max_chars: int = 128000  # 单条内容上限（对齐 DSH 默认），超出截断
    ops_telemetry_interval_s: int = 60  # 采集桶宽（秒），对齐 docs/50 §8.4
    llm_trace_retention_days: int = 30  # trace/span 保留期（docs/50 §9.3）
    llm_span_content_retention_hours: int = 72  # 内容保留期（比结构短，独立清理）
    ops_metric_retention_days: int = 7  # 指标样本保留期

    # ---- 控制台令牌（Java 签发，与学习者令牌**双密钥 + 双 audience**） ----
    # 空串 = 控制台端点一律 46001（fail-closed）：宁可控制台不可用，不可用学习者密钥冒充。
    # 不在 production 强制必填：控制台是独立部署面，缺省只影响控制台自身（其余端点不受累）。
    console_jwt_secret: str = ""  # APP_CONSOLE_JWT_SECRET（生产必须与 APP_JWT_SECRET 不同）
    console_jwt_audience: str = "vocalverse-console"  # APP_CONSOLE_JWT_AUDIENCE
    console_jwt_issuer: str = "vocalverse-java"  # APP_CONSOLE_JWT_ISSUER
    console_rate_per_min: int = 300  # 控制台账号限流（docs/50 §8.5）

    @model_validator(mode="after")
    def _resolve_secrets(self) -> "Settings":
        """密钥三档（docs/19 P0-9）：testing 固定测试值 / development 缺值告警 / production 强制。

        - testing：回退固定测试值 → CI 零真实 Key（docs/06 §5/§6），本地无 Java 联调照常；
        - development：缺值仅 warn（本地 .env 惯例提供,不改"缺 .env 也能起"体验；
          注意：缺值鉴权将失败——config 不再静默给默认密钥）；
        - production：缺值直接抛错（fail-fast,公开仓库不出现任何可用密钥）。
        """
        if self.testing:
            if not self.jwt_secret:
                object.__setattr__(self, "jwt_secret", TEST_JWT_SECRET)
            if not self.service_token:
                object.__setattr__(self, "service_token", TEST_SERVICE_TOKEN)
            if not self.console_jwt_secret:
                object.__setattr__(self, "console_jwt_secret", TEST_CONSOLE_JWT_SECRET)
        elif self.app_env == "production":
            if not self.jwt_secret:
                raise ValueError("APP_JWT_SECRET 必填：production 禁默认密钥（docs/19 P0-9）")
            if not self.service_token:
                raise ValueError("APP_SERVICE_TOKEN 必填：production 禁默认密钥（docs/19 P0-9）")
            if self.console_jwt_secret and self.console_jwt_secret == self.jwt_secret:
                # docs/50 §4.1：控制台令牌与学习者令牌必须双密钥——同密钥时 audience 校验
                # 就是唯一闸门，一旦缺席即可越权，故在启动期直接拒绝。
                raise ValueError(
                    "APP_CONSOLE_JWT_SECRET 不得与 APP_JWT_SECRET 相同（docs/50 §4.1）"
                )
        else:  # development / 其余
            if not self.jwt_secret:
                warn("APP_JWT_SECRET 未设置（development 档）：JWT 验签将失败", stacklevel=2)
            if not self.service_token:
                warn("APP_SERVICE_TOKEN 未设置（development 档）：内部委托将被拒", stacklevel=2)
            if not self.console_jwt_secret:
                warn(
                    "APP_CONSOLE_JWT_SECRET 未设置（development 档）：控制台端点将 46001",
                    stacklevel=2,
                )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
