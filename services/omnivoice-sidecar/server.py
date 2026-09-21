"""OmniVoice 边车服务 —— 本仓**唯一**的本地克隆音色合成入口。

═══════════════════════════════════════════════════════════════════════════════
【它解决什么】

主服务（`services/python`）是「文本 → 音频」的调用方，但它**不能**把 OmniVoice 装进
自己的进程：那是 torch + GPU 的重依赖，而 python-api 要能在 CPU 容器里起（CI/演示）。
两者只能走一个明确定义的进程边界，边界选在这里：

    services/python/app/audio/tts_omnivoice.py  --HTTP-->  本服务  --GPU-->  OmniVoice

调用契约见「HTTP 接口」一节；客户端与校验逻辑的**一致性由测试锁住**
（`services/python/tests/test_omnivoice_sidecar.py`：用同一份请求体喂两边）。

【音色不是一个 id】

音色 = **参考件（wav 字节） + 参考文本 + seed** 三个量，全部由调用方给死：

- 参考件走 base64 放进 JSON（**不传路径**）：传路径会引入"文件被换掉"这类静默变声；
- 参考文本**必须外部给**，不做自动转写 —— 那要额外加载 ASR 权重，而且结果随模型漂移，
  等于音色每天变；
- clone 模式下给 instruct 直接 400 —— 静默忽略比报错坏得多。

本服务刻意**不引入任何音色库 id / profile id**：一旦有 id，音色又变成"厂商侧的不透明
指针"，换引擎即作废、复现不出来。

【刻意只用标准库】

不 import fastapi / uvicorn / python-multipart：依赖应当是上游模型（`k2-fsa/OmniVoice`），
而不是"某个把模型打包进去的应用"。上游依赖里没有 web 框架 ⇒ 用 `http.server` 才能保证
"装好上游就能跑"；参考件用 base64 而非 multipart，也是同一个理由。

【并发：一条 GPU 队列】

模型是单例、GPU 只有一块。合成请求用一把锁串行化 —— 并发跑同一份权重只会互相抢显存，
不会更快。**这把锁是故意的。**

【--fake：没有 GPU 也能验证链路】

`--fake` 用占位引擎出可解析的静音 WAV，不 import torch、不加载权重。用途：CI 与开发机
冒烟"客户端 → 边车 → 音频字节 → 落盘/时长"整条链路（GPU 行为仍需真机验证）。

用法：
    <装了 omnivoice 的 python> services/omnivoice-sidecar/server.py
    可选：--host 127.0.0.1 --port 8765 --model-dir <HF 快照目录或仓库 id>
          --device cuda|cpu --dtype float16|float32 --preload --fake
    仓库根的一键启动器：`pwsh -File scripts/start-omnivoice-sidecar.ps1`

HTTP 接口：
    GET  /health       → {ok, engine, model, device, dtype, sampleRate, promptsCached, loadError}
    POST /synthesize   → 音频字节；请求体
        {text, language: "zh"|"en", mode: "clone"|"design"|"auto",
         ref: {audioBase64, text},           # clone 必填
         instruct,                           # design 必填
         seed, format: "wav"|"mp3", numStep, guidanceScale, speed}
        响应头：X-Omnivoice-Sample-Rate / -Elapsed-Ms / -Prompt-Cache / -Mode
        错误体：{"error": {"code": "...", "message": "..."}}
═══════════════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import io
import json
import os
import struct
import sys
import threading
import time
import traceback
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Optional

try:  # pytest 等捕获 stdout 时对象没有 reconfigure；控制台编码只是可读性优化，失败无妨
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

# ═══════════════════════════════════════════════════════════════════════════
# 🔴 **必须在 import torch / 初始化 CUDA 之前设**，所以放在文件最顶端。
#
# `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` —— 这一个开关在 8 GB 卡上
# 就是「能用」与「不能用」的分界。上游实测（同一台机、同一份权重）：
#
#   显存占用      7911 MiB（96.6%，几乎占满）  →  2772 MiB（33.9%）
#   第 1 次合成   11493 ms                     →  2331 ms
#   第 3 次合成    1685 ms                     →  1502 ms
#
# 省下 5.1 GB。原来那 7.4 GB **大部分不是真实用量，是 PyTorch 缓存分配器的
# 碎片与预留** —— 后果不是"跑不起来"，而是更阴的**权重被换出到内存**：
# 冷合成要 9~18 秒把权重换回来，于是动不动撞上调用方超时。
# 当时误判成"桌面程序占了显卡"，实测桌面全部加起来只有 504 MiB —— 真凶是这个设置。
#
# ⚠️ 只在调用方没自己设过时才填（`setdefault`）：留一个显式覆盖的口子，
#    否则换了机器/换了 torch 版本想调都调不动。
# ⚠️ 老版本 torch 不认识这个键时会**打印一条 warning 然后忽略**，不会崩 ——
#    所以它可以安全地默认开着。
# ═══════════════════════════════════════════════════════════════════════════
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

SERVER_NAME = "vocalverse-omnivoice-sidecar"
VERSION = "1.0.0"

# 只在克隆模式下把参考件转成说话人条件；步数/引导/语速沿用定稿参数，
# 改这里等于换引擎行为 —— 既有音色验收数据会当场失效。
DEFAULT_NUM_STEP = 16
DEFAULT_GUIDANCE_SCALE = 2.0
DEFAULT_SPEED = 1.0

# 输出容器。**默认 wav**：无压缩、解码最简单，且本仓本地引擎统一按 wav 处理
# （MediaType/缓存目录/时长估算都按容器分派）。
# ⚠️ 编解码走 libsndfile（soundfile 自带 LAME 支持），**不引入 ffmpeg 依赖** ——
#    边车的依赖越少，"换台机器能不能跑"这件事越确定。
FORMATS = {"wav": ("WAV", "PCM_16", "audio/wav"), "mp3": ("MP3", "MPEG_LAYER_III", "audio/mpeg")}
DEFAULT_FORMAT = "wav"

# 语言：契约用 ISO 码（zh/en），模型接受码或全名，这里只做**白名单校验**，
# 不做"猜语言" —— 猜错会静默换一种发音方式，属于最难查的那类故障。
LANG_ALLOWED = {"zh", "en"}

MAX_TEXT_CHARS = 4096
MAX_REF_BYTES = 8 * 1024 * 1024  # 参考件上限 8 MB（≈ 24 kHz 单声道 16bit 的 2.8 分钟）
MAX_BODY_BYTES = 16 * 1024 * 1024


class SynthError(Exception):
    """带 HTTP 状态码的合成错误。写路径大声失败：绝不用兜底音频冒充成功。"""

    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def _decode_ref_audio(ref_bytes: bytes) -> tuple[Any, int]:
    """参考件字节 → ``(float32 单声道 tensor[1, N], sample_rate)``。

    解不开按**调用方输入错**报 400（不是 500）：参考件来自请求体，格式不对是调用方的事。
    两套克隆 API 都要它（打包版拿去建 prompt，上游版直接传给 `generate`），故独立成函数。
    """
    import soundfile as sf  # noqa: PLC0415
    import torch  # noqa: PLC0415

    try:
        wav, sr = sf.read(io.BytesIO(ref_bytes), always_2d=True, dtype="float32")
    except Exception as exc:  # noqa: BLE001
        raise SynthError(
            400, "REF_AUDIO_UNDECODABLE", f"参考件解不开（需要 wav/flac/ogg）：{exc}"
        ) from exc
    mono = wav.mean(axis=1)
    return torch.from_numpy(mono).unsqueeze(0), int(sr)


# ---------------------------------------------------------------------------
# 引擎
# ---------------------------------------------------------------------------


class Engine:
    """OmniVoice 单例 + 克隆条件缓存。**所有 GPU 访问都在 `self._lock` 里**。"""

    def __init__(self, model_dir: str, device: str, dtype: str):
        self.model_dir = model_dir
        self.device = device
        self.dtype = dtype
        self.model: Any = None
        self.sample_rate: int = 0
        self.loaded = False
        self.load_error: Optional[str] = None
        self._lock = threading.Lock()
        # 克隆条件缓存：sha256(参考件字节) + 参考文本 → VoiceClonePrompt。
        # 建一次 prompt 要过一遍音频 tokenizer（实测约 0.3~0.8 s），
        # 而参考件是**不变的**（字节就是嗓子的身份）⇒ 缓存命中率天然 100%。
        self._prompts: dict[str, Any] = {}

    # -- 加载 ---------------------------------------------------------------

    def load(self) -> None:
        """加载模型。**刻意兼容两套上游 API 形状**（见下），不做假设。

        实测（2026-09-21）两条并存的实现，签名与调用方式都不同：

        | | 上游 `k2-fsa/OmniVoice`（PyPI `omnivoice` / GitHub） | VoiceStudio 打包版（`omnivoice` 0.5.1，editable） |
        |---|---|---|
        | 导入 | `from omnivoice import OmniVoice` | `from omnivoice.models.omnivoice import OmniVoice` |
        | 加载 | `from_pretrained(dir, device_map="cuda:0", dtype=torch.float16)` | `from_pretrained(dir, torch_dtype=torch.float16)` + `.to("cuda")` |
        | 克隆 | `generate(text=…, ref_audio=(wav, sr), ref_text=…)` | `create_voice_clone_prompt(…)` → `generate(voice_clone_prompt=…)` |

        只支持一种的后果很实：队友按上游 README 装好后边车直接崩。故这里**按能力探测**
        （导入回退 + `from_pretrained` 关键字回退 + `generate` 参数过滤），而不是写死一种。
        """
        import torch  # noqa: PLC0415  延迟导入：--help 不该拖起 torch

        try:
            from omnivoice import OmniVoice  # noqa: PLC0415  上游公开 API
        except ImportError:  # pragma: no cover - 打包版的模块布局
            from omnivoice.models.omnivoice import OmniVoice  # noqa: PLC0415

        t0 = time.time()
        model = self._from_pretrained(OmniVoice, torch)
        self.model = model
        self.sample_rate = int(
            getattr(model, "sampling_rate", None)
            or getattr(model, "sample_rate", None)
            or 24000
        )
        self.loaded = True
        print(
            f"[{SERVER_NAME}] 模型就绪：{self.model_dir} device={self.device} "
            f"dtype={self.dtype} sr={self.sample_rate} 用时 {time.time() - t0:.1f}s "
            f"（克隆 API：{'prompt' if hasattr(model, 'create_voice_clone_prompt') else 'ref_audio'}）",
            flush=True,
        )

    def _from_pretrained(self, cls: Any, torch: Any) -> Any:
        """按可用关键字回退加载（不同上游版本的 `from_pretrained` 签名不一致）。"""
        dtype = torch.float16 if self.dtype == "float16" else torch.float32
        attempts: list[dict[str, Any]] = []
        if self.device == "cuda":
            attempts.append({"device_map": "cuda:0", "dtype": dtype})  # 上游 README 示例
            attempts.append({"torch_dtype": dtype})  # 打包版
        attempts.append({})  # 谁都不认就裸调，交给上游默认（通常是 CPU/float32）

        last: Exception | None = None
        for kwargs in attempts:
            try:
                model = cls.from_pretrained(self.model_dir, **kwargs)
            except TypeError as exc:  # 关键字不被接受 → 试下一个
                last = exc
                continue
            # 只有没交给 device_map 时才自己搬设备：device_map 已经放好了，
            # 再 .to() 在 accelerate 管理的模型上会报错。
            if "device_map" not in kwargs and self.device == "cuda":
                model = model.to("cuda")
            model.eval()
            return model
        raise SynthError(500, "ENGINE_LOAD_FAILED", f"from_pretrained 全部签名都不匹配：{last}")

    # -- 克隆条件 -----------------------------------------------------------

    def _prompt_for(self, ref_bytes: bytes, ref_text: str):
        key = hashlib.sha256(ref_bytes).hexdigest() + "|" + ref_text
        hit = self._prompts.get(key)
        if hit is not None:
            return hit, True

        tensor, sr = _decode_ref_audio(ref_bytes)
        # 走 (waveform, sample_rate) 元组而不是临时文件：参考件是内存里的字节，
        # 落盘会引入"路径上的文件被换掉"这一类静默错误。
        prompt = self.model.create_voice_clone_prompt(
            ref_audio=(tensor, sr), ref_text=ref_text, preprocess_prompt=True
        )
        self._prompts[key] = prompt
        return prompt, False

    # -- 合成 ---------------------------------------------------------------

    def _uses_clone_prompt(self) -> bool:
        """本模型走哪套克隆 API？

        - `create_voice_clone_prompt` 存在 → 打包版：先把参考件转成说话人条件再 `generate`；
        - 不存在 → 上游版：`generate(ref_audio=(waveform, sr), ref_text=…)` 直接传参考件。
        """
        return hasattr(self.model, "create_voice_clone_prompt")

    def _generate_kwargs(self, gen_kwargs: dict[str, Any]) -> dict[str, Any]:
        """按 `generate` 的**实际签名**过滤参数（两套上游接受的调参项并不相同）。

        `num_step` / `guidance_scale` / `denoise` 这些是打包版才有的调参；上游版直接传会
        `TypeError`。有 `**kwargs` 就全放行，否则只保留签名里出现的键 —— 被丢掉的键记一条
        日志（不是静默：音质调参没生效调用方要能看见）。
        """
        import inspect  # noqa: PLC0415

        try:
            params = inspect.signature(self.model.generate).parameters
        except (TypeError, ValueError):  # pragma: no cover - 不可内省就原样传
            return gen_kwargs
        if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
            return gen_kwargs
        kept = {k: v for k, v in gen_kwargs.items() if k in params}
        dropped = sorted(set(gen_kwargs) - set(kept))
        if dropped:
            print(
                f"[{SERVER_NAME}] 注意：当前 OmniVoice 的 generate() 不接受 {dropped}，已忽略"
                f"（换上游实现时这些定稿调参可能不生效）",
                flush=True,
            )
        return kept

    def synthesize(self, req: dict[str, Any]) -> tuple[bytes, dict[str, Any]]:
        import numpy as np  # noqa: PLC0415
        import soundfile as sf  # noqa: PLC0415
        import torch  # noqa: PLC0415

        mode = req["mode"]
        text = req["text"]
        language = req.get("language")
        seed = req.get("seed")
        fmt = req.get("format") or DEFAULT_FORMAT
        num_step = int(req.get("numStep") or DEFAULT_NUM_STEP)
        guidance_scale = float(
            DEFAULT_GUIDANCE_SCALE if req.get("guidanceScale") is None else req["guidanceScale"]
        )
        speed = float(DEFAULT_SPEED if req.get("speed") is None else req["speed"])

        gen_kwargs: dict[str, Any] = {
            "text": text,
            "language": language,
            "num_step": num_step,
            "guidance_scale": guidance_scale,
            "speed": speed,
            "denoise": True,
            "postprocess_output": True,
            "preprocess_prompt": True,
        }

        with self._lock:
            if not self.loaded:
                raise SynthError(503, "ENGINE_NOT_LOADED", "模型尚未加载完成")

            cache = "n/a"
            if mode == "clone":
                ref_bytes, ref_text = req["ref"]["audio"], req["ref"]["text"]
                if self._uses_clone_prompt():
                    prompt, cached = self._prompt_for(ref_bytes, ref_text)
                    cache = "hit" if cached else "miss"
                    gen_kwargs["voice_clone_prompt"] = prompt
                else:
                    # 上游 API：参考件以 (waveform, sample_rate) 直接交给 generate
                    gen_kwargs["ref_audio"] = _decode_ref_audio(ref_bytes)
                    gen_kwargs["ref_text"] = ref_text
            elif mode == "design":
                gen_kwargs["instruct"] = req["instruct"]

            # 🔴 种子必须显式设：设计模式**没有任何说话人条件**，
            #    不固定种子时每次现抽一把嗓子（实测同一 instruct 连生 3 次 f0 抖 8~33 Hz）。
            if seed is not None:
                torch.manual_seed(int(seed))
            t0 = time.time()
            try:
                outs = self.model.generate(**self._generate_kwargs(gen_kwargs))
            except ValueError as exc:
                # instruct 词表外的 token、参考件为空等，都是**调用方输入错**，不是 500
                raise SynthError(400, "SYNTHESIS_REJECTED", str(exc)) from exc
            elapsed_ms = int((time.time() - t0) * 1000)

            # 输出归一：打包版返回 torch.Tensor，上游示例返回 numpy 数组（`audio[0]`）。
            sample = outs[0] if isinstance(outs, (list, tuple)) else outs
            if hasattr(sample, "detach"):  # torch.Tensor
                arr = sample.detach().cpu().float().numpy()
            else:  # numpy.ndarray / 可转数组
                arr = np.asarray(sample, dtype="float32")
            arr = np.squeeze(arr)
            if arr.ndim > 1:  # 多声道 → 单声道（本服务契约是 mono）
                arr = arr.mean(axis=0) if arr.shape[0] < arr.shape[-1] else arr.mean(axis=-1)
            if arr.ndim == 0:
                raise SynthError(500, "SYNTHESIS_FAILED", "模型返回了标量而非音频波形")

            buf = io.BytesIO()
            container, subtype, _mime = FORMATS[fmt]
            sf.write(buf, arr, self.sample_rate, format=container, subtype=subtype)
            audio = buf.getvalue()

        return audio, {
            "sampleRate": self.sample_rate,
            "elapsedMs": elapsed_ms,
            "promptCache": cache,
            "mode": mode,
            "format": fmt,
        }


class FakeEngine:
    """`--fake`：不 import torch、不加载权重，只出**可解析的静音 WAV**。

    存在的理由：GPU 只在少数机器上有，而"客户端 → 边车 → 音频字节 → 落盘/估时长"
    这条链路必须在任何机器（含 CI）上可验证。它**不模拟音质**，只保证契约与容器正确。
    """

    def __init__(self, model_dir: str, device: str, dtype: str):
        self.model_dir = model_dir or "(fake)"
        self.device = "fake"
        self.dtype = dtype
        self.sample_rate = 24000
        self.loaded = False
        self.load_error: Optional[str] = None
        self._lock = threading.Lock()
        self._prompts: dict[str, Any] = {}

    def load(self) -> None:
        self.loaded = True
        print(f"[{SERVER_NAME}] --fake 已就绪（不加载权重，仅用于链路冒烟）", flush=True)

    def synthesize(self, req: dict[str, Any]) -> tuple[bytes, dict[str, Any]]:
        if (req.get("format") or DEFAULT_FORMAT) != "wav":
            raise SynthError(400, "BAD_FORMAT", "fake 模式只支持 format=wav（无 libsndfile 编码器）")
        t0 = time.time()
        with self._lock:
            if not self.loaded:
                raise SynthError(503, "ENGINE_NOT_LOADED", "引擎尚未就绪")
            if req["mode"] == "clone":
                self._prompts.setdefault(
                    hashlib.sha256(req["ref"]["audio"]).hexdigest() + "|" + req["ref"]["text"],
                    True,
                )
            # 时长按文本长度估（约 15 字/秒，夹在 0.3~10s）：让下游时长估算有真实输入
            seconds = max(0.3, min(10.0, len(req["text"]) / 15.0))
            frames = int(self.sample_rate * seconds)
            buf = io.BytesIO()
            with wave.open(buf, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(self.sample_rate)
                wf.writeframes(struct.pack(f"<{frames}h", *([0] * frames)))
            audio = buf.getvalue()
        return audio, {
            "sampleRate": self.sample_rate,
            "elapsedMs": int((time.time() - t0) * 1000),
            "promptCache": "hit" if req["mode"] == "clone" and len(self._prompts) else "n/a",
            "mode": req["mode"],
            "format": "wav",
        }


# ---------------------------------------------------------------------------
# 请求校验
# ---------------------------------------------------------------------------


def _require_str(body: dict[str, Any], key: str) -> str:
    v = body.get(key)
    if not isinstance(v, str) or not v.strip():
        raise SynthError(400, "BAD_REQUEST", f"{key} 必须是非空字符串")
    return v


def validate(body: Any) -> dict[str, Any]:
    """校验并把请求规范化成引擎要的形状。

    ⚠️ 三种模式**互斥且显式**：不给 mode 就报错，不猜。
       猜错的表现是"我明明要克隆，它却按设计随机抽了一把嗓子" —— 而且不报错。
    """
    if not isinstance(body, dict):
        raise SynthError(400, "BAD_REQUEST", "请求体必须是 JSON 对象")

    text = _require_str(body, "text")
    if len(text) > MAX_TEXT_CHARS:
        raise SynthError(400, "TEXT_TOO_LONG", f"text 超过 {MAX_TEXT_CHARS} 字")

    language = body.get("language")
    if language is not None:
        language = str(language).strip().lower()
        if language not in LANG_ALLOWED:
            raise SynthError(
                400, "BAD_LANGUAGE", f"language 只接受 {sorted(LANG_ALLOWED)}，收到 {language!r}"
            )

    mode = body.get("mode")
    if mode not in ("clone", "design", "auto"):
        raise SynthError(400, "BAD_MODE", "mode 必须是 clone / design / auto 之一（刻意不猜）")

    fmt = body.get("format") or DEFAULT_FORMAT
    if fmt not in FORMATS:
        raise SynthError(400, "BAD_FORMAT", f"format 只接受 {sorted(FORMATS)}，收到 {fmt!r}")

    ref = body.get("ref")
    instruct = body.get("instruct")

    if mode == "clone":
        if not isinstance(ref, dict):
            raise SynthError(400, "REF_REQUIRED", "clone 模式必须给 ref.audioBase64 与 ref.text")
        raw = ref.get("audioBase64")
        if not isinstance(raw, str):
            raise SynthError(400, "REF_REQUIRED", "clone 模式必须给 ref.audioBase64")
        try:
            # 注意：空串要**落到下面的 REF_EMPTY**（"没给这个字段" 与 "给了一个空的"
            # 是两种不同的调用方错误，报同一个码会让排查少一条线索）。
            audio = base64.b64decode(raw, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise SynthError(
                400, "REF_NOT_BASE64", f"ref.audioBase64 不是合法 base64：{exc}"
            ) from exc
        if not audio:
            raise SynthError(400, "REF_EMPTY", "参考件是空的")
        if len(audio) > MAX_REF_BYTES:
            raise SynthError(400, "REF_TOO_LARGE", f"参考件超过 {MAX_REF_BYTES} 字节")
        ref_text = ref.get("text")
        if not isinstance(ref_text, str) or not ref_text.strip():
            # 不让它走自动转写：那需要额外加载 ASR 权重，而且结果不可复现 ——
            # 参考文本是**音色定义的一部分**，必须由调用方给死。
            raise SynthError(400, "REF_TEXT_REQUIRED", "clone 模式必须给 ref.text（不做自动转写）")
        if instruct:
            # clone 模式把 instruct 送给模型是**没有意义**的（说话人条件来自参考件）。
            # 与其静默忽略，不如报错：调用方以为 instruct 生效而实际没生效，是最坏的形态。
            raise SynthError(
                400,
                "INSTRUCT_IN_CLONE",
                "clone 模式下不接受 instruct（它是参考件的来源记录，不是运行参数）；"
                "要按 instruct 现场设计嗓音请用 mode=design",
            )
        return {
            "mode": "clone",
            "text": text,
            "language": language,
            "format": fmt,
            "seed": body.get("seed"),
            "numStep": body.get("numStep"),
            "guidanceScale": body.get("guidanceScale"),
            "speed": body.get("speed"),
            "ref": {"audio": audio, "text": ref_text.strip()},
        }

    if mode == "design":
        if not isinstance(instruct, str) or not instruct.strip():
            raise SynthError(400, "INSTRUCT_REQUIRED", "design 模式必须给 instruct")
        if ref is not None:
            raise SynthError(400, "REF_IN_DESIGN", "design 模式下不接受 ref；克隆请用 mode=clone")
        return {
            "mode": "design",
            "text": text,
            "language": language,
            "format": fmt,
            "instruct": instruct.strip(),
            "seed": body.get("seed"),
            "numStep": body.get("numStep"),
            "guidanceScale": body.get("guidanceScale"),
            "speed": body.get("speed"),
        }

    # auto：什么都不给，模型自己挑一把嗓子。只给联调/试听用，产品路径不走它。
    if ref is not None or instruct:
        raise SynthError(400, "AUTO_EXCLUSIVE", "auto 模式不给 ref / instruct")
    return {
        "mode": "auto",
        "text": text,
        "language": language,
        "format": fmt,
        "seed": body.get("seed"),
        "numStep": body.get("numStep"),
        "guidanceScale": body.get("guidanceScale"),
        "speed": body.get("speed"),
    }


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


class Handler(BaseHTTPRequestHandler):
    server_version = f"{SERVER_NAME}/{VERSION}"
    protocol_version = "HTTP/1.1"
    engine: Any  # 由 build_server 注入

    # -- 工具 ---------------------------------------------------------------

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _error(self, err: SynthError) -> None:
        self._json(err.status, {"error": {"code": err.code, "message": err.message}})

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
        # 默认实现往 stderr 打一行；这里加上服务名，便于分辨"排队"与"卡住"
        sys.stderr.write(f"[{SERVER_NAME}] {fmt % args}\n")

    # -- 路由 ---------------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802
        if self.path.split("?")[0] in ("/health", "/healthz"):
            e = self.engine
            self._json(
                200,
                {
                    "ok": e.loaded,
                    "service": SERVER_NAME,
                    "version": VERSION,
                    "engine": "omnivoice",
                    "model": e.model_dir,
                    "device": e.device,
                    "dtype": e.dtype,
                    "sampleRate": e.sample_rate,
                    "promptsCached": len(e._prompts),
                    "loadError": e.load_error,
                },
            )
            return
        self._error(SynthError(404, "NOT_FOUND", f"没有这个路径：{self.path}"))

    def do_POST(self) -> None:  # noqa: N802
        if self.path.split("?")[0] != "/synthesize":
            self._error(SynthError(404, "NOT_FOUND", f"没有这个路径：{self.path}"))
            return

        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0:
            self._error(SynthError(411, "LENGTH_REQUIRED", "缺少 Content-Length"))
            return
        if length > MAX_BODY_BYTES:
            self._error(SynthError(413, "BODY_TOO_LARGE", f"请求体超过 {MAX_BODY_BYTES} 字节"))
            return

        raw = self.rfile.read(length)
        try:
            body = json.loads(raw.decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            self._error(SynthError(400, "BAD_JSON", f"请求体不是合法 JSON：{exc}"))
            return

        try:
            req = validate(body)
            audio, meta = self.engine.synthesize(req)
        except SynthError as err:
            self._error(err)
            return
        except Exception as exc:  # noqa: BLE001
            # 引擎内部炸了：**如实报 500 并把栈打进日志**，
            # 不返回任何"占位音频"—— 那会把"能不能出声"这个唯一的事实也毁掉。
            traceback.print_exc()
            self._error(SynthError(500, "SYNTHESIS_FAILED", f"{type(exc).__name__}: {exc}"))
            return

        self.send_response(200)
        self.send_header("Content-Type", FORMATS[meta["format"]][2])
        self.send_header("Content-Length", str(len(audio)))
        self.send_header("X-Omnivoice-Sample-Rate", str(meta["sampleRate"]))
        self.send_header("X-Omnivoice-Elapsed-Ms", str(meta["elapsedMs"]))
        self.send_header("X-Omnivoice-Prompt-Cache", str(meta["promptCache"]))
        self.send_header("X-Omnivoice-Mode", str(meta["mode"]))
        self.end_headers()
        self.wfile.write(audio)


def build_server(args: argparse.Namespace) -> tuple[ThreadingHTTPServer, Any]:
    engine = FakeEngine(args.model_dir, args.device, args.dtype) if args.fake else Engine(
        args.model_dir, args.device, args.dtype
    )
    handler = type("BoundHandler", (Handler,), {"engine": engine})
    httpd = ThreadingHTTPServer((args.host, args.port), handler)
    httpd.daemon_threads = True
    return httpd, engine


def detect_device(want: str) -> str:
    if want != "auto":
        return want
    try:
        import torch  # noqa: PLC0415

        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:  # noqa: BLE001
        return "cpu"


def repo_root() -> Optional[str]:
    """仓库根（本文件位于 `<root>/services/omnivoice-sidecar/server.py`）。

    ⚠️ 本服务刻意只用标准库，因此不能 import `app.core.paths`（那是主服务的模块）。
    这里按固定层级回推：裸跑与容器都一样（`services/omnivoice-sidecar/` 这段路径是仓库结构）。
    """
    try:
        return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    except Exception:  # noqa: BLE001
        return None


def _looks_like_model(snap: str) -> bool:
    """快照是否**看起来完整**：至少有 config.json + 一个根级 *.safetensors。

    为什么要判：下载可能中断（3.3 GB，断点续传前就是个半成品目录）。只看"目录存在"
    会把这种半成品当成可用权重，结果是启动后 `loadError` 而调用方只看到"边车没就绪"。
    """
    if not os.path.isfile(os.path.join(snap, "config.json")):
        return False
    try:
        return any(name.endswith(".safetensors") for name in os.listdir(snap))
    except OSError:
        return False


def _snapshot_under(cache_root: str, repo_id: str) -> Optional[str]:
    """`<cache_root>/models--<org>--<name>/snapshots/<rev>` 里最新的**完整**快照；没有则 None。"""
    if not cache_root or not os.path.isdir(cache_root):
        return None
    snaps = os.path.join(cache_root, "models--" + repo_id.replace("/", "--"), "snapshots")
    if not os.path.isdir(snaps):
        return None
    revs = sorted(
        (d for d in os.listdir(snaps) if os.path.isdir(os.path.join(snaps, d))), reverse=True
    )
    for rev in revs:
        candidate = os.path.join(snaps, rev)
        if _looks_like_model(candidate):
            return candidate
    return None


def default_model_dir() -> str:
    """权重目录解析顺序（先本机、先本仓，最后才联网）。

    1. `OMNIVOICE_MODEL_DIR`：直接指定快照目录（最高优先，显式覆盖）；
    2. `OMNIVOICE_HF_CACHE`：指定的 HF 缓存根；
    3. **`<仓库根>/data/models`**：本仓约定位置 —— `scripts/fetch-omnivoice-weights.ps1`
       默认就下载到这里，因此**用该脚本下完即零配置**（`data/models/` 已在 .gitignore）；
    4. `~/.cache/huggingface/hub`、`%LOCALAPPDATA%/huggingface/hub`：HF 客户端默认缓存；
    5. 都找不到 → 回落仓库 id，交给上游首次自动下载（需联网，通常不适用于内网）。
    """
    env = os.environ.get("OMNIVOICE_MODEL_DIR")
    if env:
        return env

    candidates: list[str] = []
    cache = os.environ.get("OMNIVOICE_HF_CACHE")
    if cache:
        candidates.append(cache)
    root = repo_root()
    if root:
        candidates.append(os.path.join(root, "data", "models"))
    home = os.path.expanduser("~")
    candidates.append(os.path.join(home, ".cache", "huggingface", "hub"))
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        candidates.append(os.path.join(local_appdata, "huggingface", "hub"))

    for candidate in candidates:
        found = _snapshot_under(candidate, "k2-fsa/OmniVoice")
        if found:
            return found
    return "k2-fsa/OmniVoice"


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description="VocalVerse · OmniVoice 边车服务")
    p.add_argument("--host", default=os.environ.get("OMNIVOICE_HOST", "127.0.0.1"))
    p.add_argument("--port", type=int, default=int(os.environ.get("OMNIVOICE_PORT", "8765")))
    p.add_argument("--model-dir", default=default_model_dir())
    p.add_argument("--device", default=os.environ.get("OMNIVOICE_DEVICE", "auto"))
    p.add_argument(
        "--dtype",
        default=os.environ.get("OMNIVOICE_DTYPE", "float16"),
        choices=["float16", "float32"],
    )
    p.add_argument(
        "--preload", action="store_true", help="启动时同步加载模型（默认后台线程加载，健康检查先可用）"
    )
    p.add_argument(
        "--fake",
        action="store_true",
        help="占位引擎：不 import torch / 不加载权重，只出静音 WAV（链路冒烟与 CI 用）",
    )
    args = p.parse_args(argv)
    if args.fake:
        args.device = "fake"
    else:
        args.device = detect_device(args.device)

    httpd, engine = build_server(args)

    def _load() -> None:
        try:
            engine.load()
        except Exception as exc:  # noqa: BLE001
            engine.load_error = f"{type(exc).__name__}: {exc}"
            traceback.print_exc()

    if args.preload:
        _load()
    else:
        threading.Thread(target=_load, name="model-load", daemon=True).start()

    print(
        f"[{SERVER_NAME}] 监听 http://{args.host}:{args.port}  "
        f"（device={args.device} model={args.model_dir} "
        f"预加载={'是' if args.preload else '后台'}{' FAKE' if args.fake else ''}）",
        flush=True,
    )
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print(f"[{SERVER_NAME}] 收到中断，退出", flush=True)
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
