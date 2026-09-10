# ============================================================
# VocalVerse 开发服务一键起停（方式 B 的分离式封装，2026-09-04）
#
# 背景：uvicorn/mvn/pnpm 作为「终端批次任务」跑时，关终端会弹
# 「Terminate batch job (Y/N)?」且服务随会话死亡；本脚本用
# Start-Process 以**独立进程**启动（日志落 local/dev-logs/，
# gitignored），服务与终端解耦——重启电脑后重跑一次即可。
#
# 用法（pwsh 7，Windows PowerShell 5.1 会因 UTF-8 解析报错）：
#   pwsh -File scripts/dev-up.ps1 start    # 启动三端 + 健康等待（默认动作）
#   pwsh -File scripts/dev-up.ps1 status   # 查看监听与健康
#   pwsh -File scripts/dev-up.ps1 stop     # 按端口杀三端
#
# 管理端控制台（docs/50 · apps/admin）**默认不启动**，需要时显式加开关：
#   pwsh -File scripts/dev-up.ps1 start -WithConsole     # 三端 + 控制台 :5174
#   pwsh -File scripts/dev-up.ps1 status -WithConsole    # 连带列出 5174
#   pwsh -File scripts/dev-up.ps1 stop  -WithConsole     # 连带杀 5174
# 为什么做成开关而不是并进默认：控制台是独立 pnpm 项目，首次要 `pnpm install`（几十秒）、
# 还要有自己的管理员账号，把它塞进默认动作会拖慢所有组员的日常三端启动。
# 控制台需要 **Java 与 Python 都在**（它有两个上游代理：/manage→8080、/api/v1→8000），
# 所以它只能跟三端一起起，不能单独起。
#
# 数据库/缓存：start 里自动拉起——5432/6379 未监听时执行
# `docker compose up -d postgres redis` 并等待 healthy（2026-09-05，
# 修「电脑睡眠/重启后容器被引擎杀掉 → Java 起不来」的坑）；
# Docker Desktop 未运行会尝试自动启动（找不到引擎则提示后继续）。
# ============================================================
param(
    [ValidateSet("start", "stop", "status")]
    [string]$Action = "start",
    # 是否连带管理端控制台（:5174）。见上方用法说明。
    [switch]$WithConsole
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$LogDir = Join-Path $Root "local\dev-logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

# 受管端口（status / stop 都遍历它）。三端恒定；控制台按 -WithConsole 追加 ——
# **这里是一处真源**：此前三处各写一遍 `8000, 8080, 5173`，加第四端必然漏掉其中一处
# （漏 status 就"看不到它在跑"，漏 stop 就"杀了三端还剩一个占着端口"）。
$Ports = @(8000, 8080, 5173)
if ($WithConsole) { $Ports += 5174 }

# 控制台密钥自检（仅 -WithConsole 时）：见根 `.env.example` 的长注释 ——
# Java 读 VOICEVERSE_CONSOLE_JWT_SECRET、Python 读 APP_CONSOLE_JWT_SECRET，两者必须同值；
# 只配一个的后果是 Python 侧控制台端点**静默全量 401**（Java 会回退用 JWT_SECRET 签）。
# 这里只**警告**不中止：回退期（Java 侧留空）本身是设计允许的中间状态。
function Test-ConsoleSecret {
    $java = $env:VOICEVERSE_CONSOLE_JWT_SECRET
    $py = $env:APP_CONSOLE_JWT_SECRET
    if ($py -and -not $java) {
        Write-Host "  [console] ⚠️ APP_CONSOLE_JWT_SECRET 已配但 VOICEVERSE_CONSOLE_JWT_SECRET 为空："
        Write-Host "      Java 会回退用 JWT_SECRET 签控制台令牌，而 Python 用 APP_CONSOLE_JWT_SECRET 验签"
        Write-Host "      → 运维 / LLM trace / 书籍 / 媒体等 Python 侧控制台端点会全量 401（且不提示原因）。"
        Write-Host "      处置：在根 .env 里把两个键配成同一个值（≥32 字节）。"
    } elseif ($java -and $py -and $java -ne $py) {
        Write-Host "  [console] ⚠️ 两个控制台密钥**不一致**：Java 签发 / Python 验签必然 401。"
    } elseif ($java -and -not $py) {
        Write-Host "  [console] ⚠️ VOICEVERSE_CONSOLE_JWT_SECRET 已配但 APP_CONSOLE_JWT_SECRET 为空："
        Write-Host "      Python 侧将回退/拒绝（见 services/python/.env.example），控制台运维域可能不可用。"
    }
}

# HF 缓存约定（docs/06 §8 · 方式 B 本地，2026-09-04 修复；与容器 hf-cache 卷约定为两套口径，
# 容器侧由 compose/镜像承载——当前未注入属 K03 未闭合项，另立整改）：
# huggingface 被墙 → 默认走仓库 data/models 本地缓存（宿主预下载 faster-whisper-small）。
# 不设则首次 ASR 尝试联网下载 → 连接/SSL 失败 → /placement/items/*/audio 500。
# 仅在用户未显式设置时注入（与 main.py setdefault 同语义，尊重显式覆盖）。
# 2026-09-07 修正：**默认 HF 缓存（%USERPROFILE%\.cache\huggingface）已有模型时不再注入
# HF_HOME**（此前无条件注入 data/models——该目录缺失时 HF 绕开已下载模型 → 预热失败、ASR 全挂）；
# 仅当默认缓存也不存在时才切仓库目录（新机/净环境兜底）。
if (-not $env:HF_HOME) {
    if (-not (Test-Path (Join-Path $env:USERPROFILE ".cache\huggingface\hub"))) {
        $env:HF_HOME = Join-Path $Root "data\models"
    }
}
if (-not $env:HF_HUB_OFFLINE) { $env:HF_HUB_OFFLINE = "1" }
if (-not $env:HF_HUB_DISABLE_XET) { $env:HF_HUB_DISABLE_XET = "1" }

# 本地模型直载（2026-09-07 修复：huggingface_hub 新版对缓存快照做「完整性校验」，被墙环境下
# 下载不完整即拒绝加载（"incomplete: file(s) missing"），且 HF_ENDPOINT/缓存状态差异难以稳定。
# → faster-whisper 支持**本地目录路径**加载：找到含 model.bin 的完整快照，设 APP_ASR_MODEL 直指
# 该目录（完全绕过 HF 缓存/网络）；找不到才回退默认（联网/仓库预下载口径）。
# 用户显式设置了 APP_ASR_MODEL 则尊重（此分支只在未设置时执行）。
# 实测（2026-09-07）：VoiceStudio 的 models--Systran--faster-whisper-large-v3 可直载可用，
# 但 CPU int8 RTF≈5.6（5.8s 音频需 32s）不满足对话「3~5s 反馈」→ 不默认启用；如需精听/离线
# 标注可显式设 APP_ASR_MODEL=<该目录 snapshots/<rev>>。turbo（deepdml-ct2）缺 tokenizer 不可用。
$ModelSnapshotRoot = Join-Path $env:USERPROFILE ".cache\huggingface\hub\models--Systran--faster-whisper-small\snapshots"
if (-not $env:APP_ASR_MODEL -and (Test-Path $ModelSnapshotRoot)) {
    $snap = Get-ChildItem $ModelSnapshotRoot -Directory -ErrorAction SilentlyContinue |
        Where-Object { Test-Path (Join-Path $_.FullName "model.bin") } |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($snap) { $env:APP_ASR_MODEL = $snap.FullName }
}

# 根 .env 注入（2026-09-07 部署踩坑：Java application.yml 用 `${JWT_SECRET:}`，方式 B 本地
# 的 Maven 子进程不读 .env —— 无键时 JwtService P0-9 fail-fast 拒绝启动（8080 起不来），
# 而 Python 侧 pydantic-settings 自己读 .env 故不受影响）。setdefault 语义：仅未显式设置时注入。
$EnvFile = Join-Path $Root ".env"
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        # TrimStart(BOM)：Windows 记事本保存的 .env 首行带 BOM，直接匹配会把 BOM 并进键名。
        # **空值键跳过**（2026-09-07 踩坑：根 .env 的 APP_DEEPSEEK_API_KEY 留空，注入后环境变量
        # 空串优先级高于 pydantic env_file（services/python/.env 的真 key）→ LLM 静默走 Fake！
        # 空值 = 未配置语义，交给各服务自己的 .env 层取值。
        if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$') {
            $name = $matches[1].TrimStart([char]0xFEFF)
            $val = $matches[2].Trim('"').Trim("'")
            if ($val -ne "" -and -not (Test-Path "env:$name")) {
                Set-Item -Path "env:$name" -Value $val
            }
        }
    }
}

function Get-PortPid([int]$Port) {
    $c = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($c) { [int[]]$c.OwningProcess | Select-Object -Unique } else { @() }
}

function Start-Detached($Name, [string]$Cmd, [string]$WorkDir) {
    $out = Join-Path $LogDir "$Name.out.log"
    $err = Join-Path $LogDir "$Name.err.log"
    $pwsh = (Get-Command pwsh).Source
    Start-Process -FilePath $pwsh -WindowStyle Hidden -WorkingDirectory $WorkDir `
        -RedirectStandardOutput $out -RedirectStandardError $err `
        -ArgumentList "-NoProfile", "-Command", $Cmd
    Write-Host ("  [{0}] detached started -> {1}" -f $Name, (Split-Path $out -Leaf))
}

function Test-Health($Name, [string]$Url, [string]$Kind = "json") {
    try {
        if ($Kind -eq "json") { $r = Invoke-RestMethod -Uri $Url -TimeoutSec 4; return ($r -ne $null) }
        else { return ((Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 4).StatusCode -eq 200) }
    } catch { return $false }
}

function Test-DockerEngine {
    & docker info *> $null
    return ($LASTEXITCODE -eq 0)
}

# 自动拉起数据库/缓存（2026-09-05：主机睡眠/重启后 Docker 引擎恢复时
# 常把容器杀掉 → 5432/6379 无监听 → Java HikariPool 建连失败，见工作日志）
function Wait-DockerBase {
    if ((Get-PortPid 5432).Count -gt 0 -and (Get-PortPid 6379).Count -gt 0) {
        Write-Host "  [docker] postgres/redis 已在运行，跳过。"
        return
    }

    if (-not (Test-DockerEngine)) {
        $dd = "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe"
        if (Test-Path $dd) {
            Write-Host "  [docker] Docker 引擎未就绪，正在启动 Docker Desktop..."
            Start-Process $dd
            $dl = (Get-Date).AddSeconds(90)
            while ((Get-Date) -lt $dl -and -not (Test-DockerEngine)) { Start-Sleep -Seconds 3 }
        }
        if (-not (Test-DockerEngine)) {
            Write-Host "  [docker] ⚠️ Docker 引擎仍不可用：请先手动启动 Docker Desktop 后再重跑 start。"
            Write-Host "      （继续：三端照启，Java 可能因连不上 DB 而失败）"
            return
        }
    }

    Push-Location $Root
    try {
        Write-Host "  [docker] 容器未就绪，docker compose up -d postgres redis ..."
        & docker compose up -d postgres redis | ForEach-Object { Write-Host "    $_" }
        if ($LASTEXITCODE -ne 0) {
            Write-Host "  [docker] ⚠️ docker compose up 失败（exit=$LASTEXITCODE）。"
            Write-Host "      排查：docker compose ps / docker compose logs postgres"
            return
        }
        $dl = (Get-Date).AddSeconds(90)
        do {
            Start-Sleep -Seconds 3
            $t = (& docker compose ps --format "{{.Service}}:{{.Status}}" postgres redis 2>$null) -join "`n"
        } until (($t -match "postgres:.*healthy" -and $t -match "redis:.*healthy") -or $t -match "Exited|unhealthy" -or (Get-Date) -gt $dl)
        if ($t -match "postgres:.*healthy" -and $t -match "redis:.*healthy") {
            Write-Host "  [docker] postgres/redis healthy。"
        } else {
            Write-Host "  [docker] ⚠️ 容器未恢复 healthy（90s 超时/异常）：$($t -replace "`n", "  ")"
            Write-Host "      排查：docker compose ps / docker logs vocalverse-postgres-1"
        }
    }
    finally { Pop-Location }
}

switch ($Action) {
    "status" {
        foreach ($p in $Ports) {
            $pids = Get-PortPid $p
            $ok = $pids.Count -gt 0
            Write-Host ("  {0,5}: {1}" -f $p, ($(if ($ok) { "LISTENING (pid {0})" -f ($pids -join ',') } else { "down" })))
        }
        Write-Host "  health: python="(Test-Health py "http://127.0.0.1:8000/readyz")""
        Write-Host "  health: java="(Test-Health java "http://127.0.0.1:8080/api/v1/ping")""
        # vite 默认绑 localhost（::1），127.0.0.1 会 refused（2026-09-04 踩坑）
        Write-Host "  health: vite="(Test-Health vite "http://localhost:5173" "web")""
        if ($WithConsole) {
            Write-Host "  health: console="(Test-Health console "http://localhost:5174" "web")""
        }
        break
    }
    "stop" {
        foreach ($p in $Ports) {
            foreach ($procId in (Get-PortPid $p)) {
                Write-Host "  killing $procId (port $p)..."
                taskkill /PID $procId /T /F | Out-Null
            }
        }
        Write-Host "  done。日志保留在 local/dev-logs/"
        break
    }
    default {
        Write-Host "== 数据库/缓存（Docker，自动拉起）=="
        Wait-DockerBase

        Write-Host "== 启动 Python :8000（uvicorn --reload）=="
        if ((Get-PortPid 8000).Count -eq 0) {
            # --host 0.0.0.0（2026-09-10）：方案 B 打包壳里 Web 直接调 http://<局域网IP>:8000，
            # 只绑 127.0.0.1 时手机连不到（本地 health 检查仍走 127.0.0.1，不受影响）
            Start-Detached "python-8000" "Set-Location '$Root\services\python'; uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000" "$Root\services\python"
        } else { Write-Host "  已在运行，跳过。" }

        Write-Host "== 启动 Java :8080（mvn spring-boot:run）=="
        if ((Get-PortPid 8080).Count -eq 0) {
            Start-Detached "java-8080" "Set-Location '$Root\services\java'; mvn spring-boot:run" "$Root\services\java"
        } else { Write-Host "  已在运行，跳过。" }

        Write-Host "== 启动 Vite :5173（pnpm dev）=="
        if ((Get-PortPid 5173).Count -eq 0) {
            Start-Detached "vite-5173" "Set-Location '$Root\apps\web'; pnpm dev" "$Root\apps\web"
        } else { Write-Host "  已在运行，跳过。" }

        if ($WithConsole) {
            Write-Host "== 启动管理端控制台 :5174（pnpm dev）=="
            Test-ConsoleSecret
            $AdminDir = Join-Path $Root "apps\admin"
            # 独立 pnpm 项目（本仓**没有**根 workspace），首次必须先 install，否则 vite 起不来
            if (-not (Test-Path (Join-Path $AdminDir "node_modules"))) {
                Write-Host "  [console] 未安装依赖，先 pnpm install（首次约 30~60s）..."
                Push-Location $AdminDir
                try {
                    & pnpm install
                    if ($LASTEXITCODE -ne 0) {
                        Write-Host "  [console] ⚠️ pnpm install 失败（exit=$LASTEXITCODE），跳过控制台启动。"
                    }
                }
                finally { Pop-Location }
            }
            if ((Get-PortPid 5174).Count -eq 0 -and (Test-Path (Join-Path $AdminDir "node_modules"))) {
                Start-Detached "console-5174" "Set-Location '$AdminDir'; pnpm dev" $AdminDir
                Write-Host "      入口 http://localhost:5174（需已 bootstrap 管理员账号，见 services/java/.env.example）"
            } elseif ((Get-PortPid 5174).Count -gt 0) { Write-Host "  已在运行，跳过。" }
        }

        Write-Host "== 健康等待（python≈8s / vite≈10s / java≈30-60s）=="
        $deadline = (Get-Date).AddSeconds(120)
        $py = $false; $vt = $false; $jv = $false; $cs = -not $WithConsole
        while ((Get-Date) -lt $deadline -and -not ($py -and $vt -and $jv -and $cs)) {
            if (-not $py) { $py = Test-Health py "http://127.0.0.1:8000/readyz" }
            if (-not $vt) { $vt = Test-Health vite "http://localhost:5173" "web" }
            if (-not $jv) { $jv = Test-Health java "http://127.0.0.1:8080/api/v1/ping" }
            if (-not $cs) { $cs = Test-Health console "http://localhost:5174" "web" }
            if (-not ($py -and $vt -and $jv -and $cs)) { Start-Sleep -Seconds 3 }
        }
        Write-Host ("  python(8000): {0}  vite(5173): {1}  java(8080): {2}" -f $py, $vt, $jv)
        if ($WithConsole) { Write-Host ("  console(5174): {0}" -f $cs) }
        if (-not ($py -and $vt -and $jv -and $cs)) {
            Write-Host "  ⚠️ 有服务未就绪，看日志：local/dev-logs/*.err.log（数据库容器看上方 [docker] 提示 / docker compose ps）"
        }
        Write-Host "  完成。服务与终端已解耦：关终端不再提示 Terminate batch job。"
        break
    }
}
