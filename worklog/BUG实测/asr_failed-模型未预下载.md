# BUG:练习功能报「管线提示:asr_failed」(whisper 模型未预下载 · 容器到 HF 不可达)

## 复现

1. `docker compose up -d --build` 全栈启动后,登录 → 建场景会话 → 上传音频回合(action=normal);
2. SSE 返回 `{"type":"error","code":"asr_failed"}`,前端呈现「管线提示:asr_failed」;
3. 容器日志(定论上下文):
   ```
   whisper 预热失败(不阻塞启动): Got: ConnectError: [Errno 111] Connection refused
   asr failed: Got: ConnectError: ... 无法找到 ... revision on the local disk
   ```
4. 修前验证:容器内 `curl https://huggingface.co` → `Failed to connect ... Could not connect to server`(容器网络到 HF 不通);`ls /root/.cache/huggingface` → 不存在。

## 根因(三层)

1. **模型权重不在容器内**:`/root/.cache/huggingface` 为空,WhisperModel(small) 每次调用都尝试从 HuggingFace Hub 下载(≈461MB);
2. **容器网络不可达 HF**:下载报 Errno 111/Connection refused(宿主直连可达,容器网络不通,无代理继承);
3. **POC 备注的 xet 401 未处理**:`HF_HUB_DISABLE_XET=1` 未设置(即使网络可达,新传输协议也 401).
   —— 正是**审计 R-11** 点名的既有欠账:「hf-cache 卷未挂、模型未预下载、冷加载 500MB 超健康检查窗口」(此前只验证过 action=start 无音频路径,ASR 真路径从未在容器内跑通过)。

## 修复(按 R-11 预案「模型预下载进镜像」)

1. **本地下载**(绕开本机 Python SSL 证书链缺陷):`curl --ssl-no-revoke` 下载 `Systran/faster-whisper-small` 四件套到 `services/python/.models-cache/huggingface/`(model.bin 483MB + config/tokenizer/vocabulary);
   - 发现:HF 仓库**无** `preprocessor_config.json`(下载会得 15 字节 "Entry not found",已剔除;faster-whisper 不需要它);
2. **Dockerfile**:`COPY .models-cache/huggingface /app/models/whisper-small`(构建上下文预下载;说明注释 docs/06 §8 · R-11 · 权重红线不入库);
3. **compose**:python-api `APP_ASR_MODEL: /app/models/whisper-small`(容器用镜像内副本;本地裸跑 `uvicorn` 仍走 'small' 联网,行为不变);
4. **CI(docker-build.yml)**:python-api 构建前增加「Fetch whisper model」步骤(GHA 网络直连 HF + `HF_HUB_DISABLE_XET=1`),否则 push 到 main 的 CI 构建会因 COPY 缺文件失败——workflow 已本地 `yaml.safe_load` 校验;

## 验证

1. `WhisperModel('.models-cache/huggingface', cpu, int8)` 本地加载 OK(仅一条无害的 preprocessor 警告,已随文件剔除消失);
2. 重建 python-api 镜像(模型进镜像层)→ 容器 healthy,启动无「预热失败」告警;
3. **真音频回合复现通过**:上传 1s 8kHz 正弦 WAV → SSE `turn_start → user_transcript → text_delta×15 → score_delta → audio_chunk×3 → meta_block → turn_end`,**零 error(asr_failed 消失)**;
4. 既有门禁不受影响(pytest/ruff 未动运行代码;compose/Dockerfile/workflow 仅部署面);

## 踩坑

1. **本机 Python SSL 证书链坏**(uv 自带 CPython 无本地 issuer)→ `requests/httpx/huggingface_hub` 全部 `CERTIFICATE_VERIFY_FAILED`,但 `curl --ssl-no-revoke` 直连正常——下载模型绕道 curl,不要用 Python 下载;
2. HF 仓库 API 返回 "Entry not found" 也是 HTTP 200 文本 → 误存为文件(15 字节)会留下脏文件,需按仓库文件清单核对;
3. 「只测过 start 无音频路径」= ASR 真路径零覆盖 → 本次教训:热路径验收必须含**真音频回合**(现存测试均为 Fake ASR;容器实机此前只有 action=start 冒烟)。
