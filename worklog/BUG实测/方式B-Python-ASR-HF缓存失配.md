# 方式 B Python ASR 500（HF 模型缓存失配）· BUG 实测记录

> 对应模块：入学测试评分链路 `POST /api/v1/placement/items/{id}/audio` → `faster-whisper` ASR（方式 B 本地 uvicorn :8000）
> 记录规则：**复现过程 / 根因 / 修复过程 / 修复情况 / 踩坑记录**，带时间与负责人（与 `VocalVerse工作日志.md` 同约定）。

---

## BUG：提交录音 → `HTTP 500`，前端报「Python（语音/LLM）服务不可达 (HTTP 500, /api/v1/placement/items/1/audio)」

- **发现时间**：2026-09-04（方式 B 三端联调：Java/前端已按 README 起好，Python 服务在跑，仅录音提交 500）
- **负责人**：Faust-sudo
- **严重级别**：P1（入学测试核心流程不可用）
- **表面现象**：uvicorn 日志尾部 `httpx/_transports/default.py` + `httpcore/_sync/connection_pool.py` 栈（**同步客户端的栈**）；散落一行被截断的报错文案「cal disk. Please check your internet connection and try again.」

### 复现过程（2026-09-04，20 秒即复现）

方式 B 无任何 HF 环境变量的场景下，直接加载模型：

```powershell
& services\python\.venv\Scripts\python.exe -c "from faster_whisper import WhisperModel; WhisperModel('small', device='cpu', compute_type='int8')"
```

实际结果：

```
huggingface_hub.errors.LocalEntryNotFoundError: Got: ConnectError: [SSL: CERTIFICATE_VERIFY_FAILED]
certificate verify failed: unable to get local issuer certificate (_ssl.c:1010)
An error happened while trying to locate the files on the Hub, and we cannot find the appropriate
snapshot folder for the specified revision on the local disk. Please check your internet connection
and try again.
```

### 根因分析

| 事实 | 说明 |
|---|---|
| 服务能起、首请求 500 | `main.py` 的 `_prewarm_asr()` 预热失败**只 `logger.warning` 不阻塞启动**（docs/06 §8 有意为之）——问题被压到首个真实请求才爆炸 |
| 模型其实在本机 | `data/models/hub/models--Systran--faster-whisper-small` **完整存在**（model.bin 483MB + tokenizer + vocab，宿主预下载；方式 B 本地约定走 `data/models`；容器侧约定本是 hf-cache 卷（docs/06 §8），compose 当前未落地——K03 未闭合） |
| 但本地进程找不到 | 本地 uvicorn **无 `HF_HOME`/`HF_HUB_OFFLINE`**（容器侧约定为 hf-cache 卷承载 HF 默认缓存路径（docs/06 §8），但 compose 当前未注入任何 HF_* 变量、亦无 hf-cache 卷——K03 未闭合；方式 B 没有任何等价注入）→ huggingface_hub 1.29 走默认缓存 `%USERPROFILE%\.cache\huggingface`（里面只有 Qwen，无 whisper） |
| 联网下载失败 | huggingface.co **被墙**（本机 SSL 握手即失败，2026-09-04 实测；仓库 worklog 另有 xet 通道 401 记录）→ `snapshot_download` 抛 `LocalEntryNotFoundError`（链出 httpcore **同步** httpx `ConnectError`） |
| 为什么是 500 | `score_item` 里 `await asr.transcribe(data)` **无 try/except**（ISE 有、LLM judge 有 fail-open，唯独 ASR 裸奔）→ 异常直达 ASGI → 500 |

一句话：**方式 B 缺「HF 缓存环境约定」的注入，whisper 去查了一个没有模型、又连不上网的缓存路径。**

### 修复过程（2026-09-04 · Faust-sudo）

1. **`services/python/app/main.py`**：进程入口处 `os.environ.setdefault` HF 变量——`HF_HOME=<仓库>/data/models`、`HF_HUB_OFFLINE=1`、`HF_HUB_DISABLE_XET=1`（docs/06 §8 本地缓存约定；必须在任何 huggingface_hub 导入之前；用户进程已显式设置时尊重之。**09-04 深夜复审整改**：容器布局 `/app/app/main.py` 无「仓库根」（`parents[3]` 越界）→ 自动跳过 `HF_HOME`/`HF_HUB_OFFLINE` 注入，维持 hf-cache 卷默认路径，不破坏容器首次下载流程）。
2. **`scripts/dev-up.ps1`**：启动 Python 前显式注入同款三变量（方式 B 本地口径；仅在用户未显式设置时注入，与 main.py setdefault 同语义；日志可见、可查）。
3. **`README.md` FAQ**：新增「本地 ASR 500 / `LocalEntryNotFoundError` / httpx 连接错误」行，指向本文档与 docs/06 §8 约定。

### 修复情况（2026-09-04 验证）

删除全部 HF 环境变量后冷起 `uvicorn app.main:app --port 8001`（验证隔离实例），全链路实测：

| 检查项 | 结果 |
|---|---|
| 应用启动（readyz） | ✓ `{"code":0,"status":"ready","asr":"small","tts":"edge"}` |
| `POST /api/v1/placement/items/1/audio`（edge-tts 合成英语语音） | ✓ `code=0` |
| ASR 转写 | ✓ `"Hello, my name is Alex and I like reading English books."`（逐词正确） |
| 评分返回 | ✓ pron 90.0 / flu 86.0 / wpm 203.7（Fake ISE，未配 Key 属预期） |
| 验证数据 | ✓ 测试 attempt 已从库中删除（DELETE 1） |

### 踩坑记录

1. **httpx 栈先分「同步/异步」**：`httpcore/_sync/connection_pool.py` + `default.py` 的 `HTTPTransport` = **同步客户端**；应用代码里全是 `AsyncClient` → 直接锁定第三方库（这里是 huggingface_hub 1.29 的**同步 `httpx.Client`**，`utils/_http.py::default_client_factory`）。别再应用层代码里瞎找。
2. **被截断的报错文案可以「按原文反查」**：「…local disk. Please check your internet connection and try again.」→ 在 site-packages 里 grep `internet connection` 精准命中 `huggingface_hub/_snapshot_download.py:375`（`LocalEntryNotFoundError`），一句话定位根因。
3. **预热吞异常 ≠ 系统健康**：`_prewarm_asr` 失败只告警，让「模型加载不了」从启动可见性里消失；**凡预热/降级路径，失败至少留下可搜索的关键词**（本次 WARN 只有一行「whisper 预热失败」且可能被 `--reload` 日志冲掉）。
4. **容器/本地口径不同 = 隐性契约缺口**：容器侧约定（hf-cache 卷 + HF 默认缓存路径，docs/06 §8）与方式 B 本地（仓库 `data/models` + offline）是**两套口径**；本仓库 compose 当前**并未**注入 HF 三件套（K03 未闭合项），方式 B 文档此前也未言明 → 每次本地联调必踩。修复应落在**代码默认值**（`setdefault` 尊重显式覆盖，且按布局区分注入），而不是再写一行文档让每个人记。
5. **ASR 是唯一没有 fail-open 的环节**：ISE/LLM 失败都降级继续，ASR 失败直接 500——语义上（ASR 是评分根基、无转写则无评分）可以接受，但报错应可被前端友好呈现；当前前端拿到的是「服务不可达（HTTP 500）」误导文案，后续可考虑给 ASR 失败一个明确的错误码（如 5xxxx 服务端暂不可用）而非裸 500。

### 复审整改（2026-09-04 深夜 · LHRCarrier 复审）

- **P0**：`Path(__file__).resolve().parents[3]` 在容器布局（Dockerfile `WORKDIR /app` + `COPY . .` → `/app/app/main.py`，parents 只有 3 级）越界抛 `IndexError` → 容器导入即崩、方式 A 全栈不可用；已改 `try/except IndexError` 布局感知（容器布局跳过 `HF_HOME`/`HF_HUB_OFFLINE` 注入）。复现：`python -c "from pathlib import Path; Path('/app/app/main.py').resolve().parents[3]"` → `IndexError: 3`。
- **表述失实**：本文初版多处「容器由 compose 注入 HF 三件套（挂载 ./data/models）」与仓库事实不符（compose/Dockerfile 无任何 HF_* 变量，docs/06 §8 为 hf-cache 卷约定；审计 K03 明言）——已全仓更正为「方式 B 本地 = 仓库 data/models；容器 = hf-cache 卷 + 默认路径（compose 未注入，K03 未闭合，另立整改）」。
- **配套**：`dev-up.ps1` 改为仅在未显式设置时注入；`.gitignore` 补 `data/models/`（模型权重红线）；主日志补本条整改记录。
