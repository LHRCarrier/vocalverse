# VocalVerse 声语界

> AI 英语口语训练 + 英文歌练唱评分平台 —— 以"说得好、唱得准"为目标的智能发音教练

VocalVerse 面向不同年龄段英语学习者，基于大模型场景扮演（AI 数字人对话）+ 语音识别/合成/评分技术，提供：

- **口语陪练**：生活/工作/学习场景模拟对话，AI 数字人实时互动，发音、语法、流利度多维度评分
- **英文歌练唱**：英文歌曲跟唱，音准、节奏、发音逐句评分（本项目特色扩展）
- **个性化学习**：入学测试 + 学习画像 + 推荐算法，自动生成学习路径
- **可视化报表**：口语/唱歌成绩多维度分析与趋势展示

## 技术栈

| 层 | 技术 |
|---|---|
| 前端 | **Vue 3 + TypeScript(strict) + Vite 6 + pnpm**（Web 端；移动端以 PWA/响应式覆盖，原生 App 列为扩展） |
| Python 服务 | **FastAPI**：ASR（faster-whisper small/int8/CPU）、TTS（edge-tts，Azure 备胎）、讯飞评测（发音评分基线）+ wav2vec2 微调（门禁化自研加分项）、唱歌评分（pyin + DTW）、DeepSeek LLM 场景扮演 Agent、推荐（sklearn） |
| Java 服务 | **Spring Boot 3.3 / Java 21**（薄管理端）：用户管理、场景/歌曲库 CRUD、工单、JWT 签发 |
| 大模型 | DeepSeek API（场景扮演、语法判定、评分报告生成） |
| 模型训练 | **PyTorch**（CPU 推理；云 GPU 训练隔离环境）+ **Scikit-learn**（推荐、水平预测） |
| 数据 | PostgreSQL（Alembic 唯一 schema 真源）· Redis（会话/缓存/限流） |
| 部署 | Docker Compose（python 8000 / java 8080 / web 8088 / pg 5432 / redis 6379） |

## 快速开始（Windows）

```powershell
.\scripts\bootstrap.ps1    # 工具链自检（node/pnpm/python/uv/jdk/maven/docker/ffmpeg）
.\scripts\dev.ps1          # docker compose 一键起全部服务
# 前端 http://localhost:8088 · Python API http://localhost:8000/docs · Java http://localhost:8080/swagger-ui.html
```

本地热重载（推荐 M2 起）：Python 用 venv + uvicorn，前端 pnpm dev，见各服务 README。

## 仓库结构

```
apps/web/         前端（Vue3+TS+Vite6；录音 / SSE / 埋点）
services/python/  语音管线 + LLM Agent + 推荐（FastAPI；Alembic 唯一 schema 真源）
services/java/    薄管理端（Spring Boot；JWT 签发）
infra/            部署与 nginx 配置
scripts/          dev.ps1 / bootstrap.ps1（Windows 一键）
docs/             00~05 规划文档 + 06 技术框架决策（ADR 唯一权威）+ api/ 契约
```

## 文档索引

| 文档 | 内容 |
|---|---|
| `docs/00-案例原始要求.md` | 案例 #7 docx 原文（选题总表、案例功能、开发语言、技术点，逐字转录） |
| `docs/01-选题依据.md` | 课程案例 #7 原文要点 + 扩展方向（唱歌评分） |
| `docs/02-功能规划.md` | 功能模块清单与 MVP 砍范围建议 |
| `docs/03-技术选型.md` | 技术方案、API 选型、云 GPU 预算 |
| `docs/04-分工与里程碑.md` | 三人分工与阶段里程碑（M1~M4） |
| `docs/05-GitHub协作规范.md` | 分支保护、PR 流程、commit 规范 |
| **`docs/06-技术框架决策.md`** | **ADR 权威文档**：双子代理拷问产出 + 组长拍板（拓扑/版本/CI/契约/音频/指标口径/评分公式/合规），与 00~05 冲突以本文档为准 |

## 里程碑（详见 docs/04、docs/06）

1. **M1 骨架**（第 1 周）：本仓库脚手架 + 三端 CI + 语音三件套 stub 联调
2. **M2 MVP**（第 2-3 周）：口语闭环（注册→入学测试→场景对话→录音→评分→建议→报告）
3. **M3 特色**（第 4-5 周）：唱歌评分做深（音准/节奏/发音）+ 推荐/报表演示化 + 四指标看板；（门禁）wav2vec2 微调
4. **M4 联调**（第 6 周）：性能 p95 达标、演示脚本、答辩材料

## 红线（公开仓库）

API Key、密码、真实用户数据、训练集原始文件、模型权重、原始音频、商用音乐 **严禁入库**；密钥只进 `.env`（已 gitignore）。
