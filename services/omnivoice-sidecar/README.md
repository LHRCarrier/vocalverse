# OmniVoice 边车服务（`services/omnivoice-sidecar/`）

> 本仓**唯一**的本地克隆音色合成入口。主服务 `services/python` 通过
> `POST /synthesize` 调它，客户端实现在 `app/audio/tts_omnivoice.py`。
> 引擎是 **k2-fsa/OmniVoice**（本机 GPU，权重不入库）。

---

## 1. 为什么是一个独立进程

`services/python`（FastAPI）要能在 **CPU 容器**里起（CI / 演示 / 队友机器），
而 OmniVoice 是 **torch + GPU** 的重依赖。两者不能同进程，只能走一个明确定义的边界：

```
services/python/app/audio/tts_omnivoice.py ──HTTP──> 本服务 ──GPU──> OmniVoice
```

边界选在这里的收益是**唯一一份音色定义**：练习热路径、读书听书、离线批量预合成
全部打同一个 `POST /synthesize`，不会出现「A 场景一把嗓子、B 场景另一把」。

**契约一致性由测试锁住**：`services/python/tests/test_omnivoice_sidecar.py`
用同一份请求体同时喂「客户端构造」与「服务端 `validate()`」，两边漂移即红。

## 2. 怎么起

```powershell
# ① 下权重（约 3.28 GB，不入库）。默认走 HF 镜像下到 <仓库>/data/models
pwsh -File scripts/fetch-omnivoice-weights.ps1
#    本机已有缓存就别下了，直接复制：-FromLocal <HF 缓存根>
#    只验链路/试网速：              -Only "config.json"

# ② 起边车（启动前会自检依赖、探端口、探权重）
pwsh -File scripts/start-omnivoice-sidecar.ps1
#    无 GPU / 只想验链路：          -Fake

# ③ 或者：随三端一起起（一键启动默认就会尝试边车，起不来只提示不阻塞）
pwsh -File scripts/dev-up.ps1 start          # 含边车；不想起加 -NoVoice
```

**权重查找顺序**（边车与 `dev-up.ps1` 同一套）：`OMNIVOICE_MODEL_DIR` →
`OMNIVOICE_HF_CACHE` → **`<仓库>/data/models`**（即上面 ① 的默认落点，**下完即零配置**）
→ `~/.cache/huggingface/hub` 等 HF 默认缓存 → 仓库 id（首次自动下载，内网通常不通）。
判据是「快照里要有 `config.json` + 至少一个 `*.safetensors`」——**下载到一半的目录不会被当成可用权重**。

手工起（想自己控制参数时）：

```powershell
<python> services/omnivoice-sidecar/server.py --port 8765 --dtype float16
#   --host 127.0.0.1 --port 8765
#   --model-dir <HF 快照目录或仓库 id>
#   --device cuda|cpu   --dtype float16|float32   --preload   --fake
# 环境变量：OMNIVOICE_HOST / _PORT / _MODEL_DIR / _HF_CACHE / _DEVICE / _DTYPE / _PYTHON
```

健康检查：`curl http://127.0.0.1:8765/health` → `ok=true` 表示模型就绪
（模型加载约 7~10s；`/health` 在加载完成前就可用，所以能区分「没起」和「起了但还在加载」）。
**主服务只认 `ok=true`** —— 加载窗口内它会继续用 edge，不会撞 503。

主服务侧不需要额外配置：`APP_TTS_PROVIDER` 默认 `auto`，链首就是本引擎；
它**探测 `/health` 且要求 `ok=true`**（5s TTL 缓存），边车没起或没加载完就自动回落 kitten/edge。

**「用哪个 python / 权重在哪」的真源**：`scripts/lib/omnivoice.ps1`，
被 `start-omnivoice-sidecar.ps1` 与 `dev-up.ps1` 共用（各写一遍必然漂移）。
查找顺序（都可用环境变量覆盖，优先级最高）：

| | python（判据 `import omnivoice` 成功） | 权重缓存根 |
|---|---|---|
| 1 | `$env:OMNIVOICE_PYTHON` | `$env:OMNIVOICE_HF_CACHE` |
| 2 | `<repo>/.venv-omnivoice/Scripts/python.exe`（README 推荐位置） | **`<repo>/data/models`**（fetch 脚本落点） |
| 3 | `<repo>/services/python/.venv/Scripts/python.exe` | 本机已知 dev 环境（VoiceStudio 缓存） |
| 4 | 本机已知 dev 环境（VoiceStudio 应用 venv） | `~/.cache/huggingface/hub` |
| 5 | `python`（PATH） | `%LOCALAPPDATA%\huggingface\hub` |

> 换机器只需要设 `$env:OMNIVOICE_PYTHON` / `$env:OMNIVOICE_HF_CACHE`，不必改脚本。

## 3. 依赖与权重（**权重不入库**）

| 项 | 说明 |
|---|---|
| Python 环境 | OmniVoice + torch + soundfile，**不装在 `services/python/.venv`**（那是 CPU 运行时）。单独建一个环境，用 `-Python` 或 `OMNIVOICE_PYTHON` 指过来 |
| 模型权重 | 约 **3.28 GB**（`model.safetensors` 2.45 GB + `audio_tokenizer/model.safetensors` 806 MB 等）；用 `scripts/fetch-omnivoice-weights.ps1` 下到 `<仓库>/data/models`（gitignored），或 `-FromLocal` 从别人机器拷 |
| 音色参考件 | `data/seed/voices/`（`VOICES.json` + 4 个 wav，合计约 1.9 MB，**随仓库入库**）；主服务侧 `APP_VOICE_REFS_DIR` **留空即自动用它** |

> ⚠️ **欠账**：没有"一键装好环境"的脚本。换机器要自己让 `import omnivoice` 成立
> （建 venv + `pip install omnivoice torch soundfile`）。**权重**已经有一键脚本
> （`scripts/fetch-omnivoice-weights.ps1`，镜像默认 `hf-mirror.com`，本机实测 huggingface.co 直连超时）。
> `-Fake` 可以在没有环境的机器上先把链路跑通，但**不能**验证音质。

## 4. HTTP 接口

```
GET  /health
     → {ok, service, version, engine, model, device, dtype, sampleRate, promptsCached, loadError}

POST /synthesize
     {
       "text": "要合成的文本",
       "language": "zh" | "en",                       // 白名单，不猜
       "mode": "clone" | "design" | "auto",           // 必须显式给
       "ref": { "audioBase64": "...", "text": "参考件对应的文本" },   // clone 必填
       "instruct": "male, middle-aged, american accent",             // design 必填
       "seed": 42,
       "format": "wav" | "mp3",                       // 默认 wav
       "numStep": 16, "guidanceScale": 2.0, "speed": 1.0             // 可选，默认即定稿参数
     }
     → 音频字节；响应头 X-Omnivoice-Sample-Rate / -Elapsed-Ms / -Prompt-Cache(hit|miss) / -Mode
     错误体 {"error": {"code", "message"}}；code 可机读
     （REF_TEXT_REQUIRED / INSTRUCT_IN_CLONE / BAD_MODE / REF_TOO_LARGE / SYNTHESIS_REJECTED …）
```

### 四条刻意的设计（每条都有理由，别"顺手改回去"）

1. **`mode` 必须显式给，不给就报错，不猜。** 猜错的表现是"我要克隆，它却按设计模式
   随机抽了一把嗓子"——而且不报错。
2. **clone 模式下给 `instruct` 会 400。** 克隆的说话人条件来自参考件，instruct 只是
   「这把参考件当初怎么造出来的」来源记录，发给模型没有意义。**静默忽略比报错坏得多。**
3. **参考文本必须外部给，不做自动转写。** 自动转写要额外加载 ASR 权重，且结果随模型
   漂移——那等于音色每天在变。参考文本是**音色定义的一部分**。
4. **参考件走 base64 放进 JSON**，既不传路径也不用 multipart。传路径 = 引入"文件被换掉"
   这类**静默变声**的可能；multipart = 边车要多一个解析依赖。

### 只用标准库

本服务**不 import fastapi / uvicorn / python-multipart**：依赖应当是上游模型本身，
而不是某个把模型打包进去的应用；上游依赖里没有 web 框架 ⇒ 用 `http.server` 才能保证
"装好上游就能跑"。参考件用 base64 也是同一个理由。

### 并发是一条 GPU 队列

模型单例、GPU 一块，合成请求用一把锁**串行化**（`Engine._lock`）。
并发跑同一份权重只会互相抢显存，不会更快——锁是故意的。

### 克隆条件缓存

`create_voice_clone_prompt()` 要过一遍音频 tokenizer（约 0.3~0.8 s），而参考件是
**不变的**（字节就是嗓子的身份）⇒ 按 `sha256(参考件字节) + 参考文本` 缓存，命中率天然 100%。
缓存不落盘：纯内存派生数据，重启重算即可。

### 8 GB 卡上的一个开关

`PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` 在 `server.py` 顶部
（`setdefault`，import torch 之前）与启动器里各设一次。实测：显存 7911 → 2772 MiB，
冷合成 11493 → 2331 ms。它省下的主要是**缓存分配器的碎片与预留**；不设的后果不是跑不起来，
而是权重被换出到内存 → 冷合成 9~18 秒 → 撞调用方超时。

## 5. 验收

| 验什么 | 怎么验 |
|---|---|
| 服务能不能起、契约对不对 | `pwsh -File scripts/start-omnivoice-sidecar.ps1 -Fake` + `curl /health` |
| **客户端与校验逻辑是否一致** | `cd services/python && uv run pytest tests/test_omnivoice_sidecar.py -q` |
| 真机能不能出声 | `GET /health` → `ok:true`；再走一次 `/tts` 或读书「听这句」 |
| 端到端（GPU） | 起边车后 `get_tts_client().provider_id` 应为 `omnivoice`，`/tts` 的 `media_type` 为 `audio/wav` |

> GPU 侧的**音质**判据（与定稿参考件是否等价、跨文本是否同一把嗓子）需要在有 GPU 的机器上
> 单独验；本仓 CI 只覆盖契约与链路形状。
