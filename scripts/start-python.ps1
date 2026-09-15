# ============================================================
# 单独启动 Python :8000（带全套环境，防 ASR 模型脱绑的坑）
#
# 用法：
#   pwsh -File scripts/start-python.ps1              # 前台（Ctrl+C 停止）
#   pwsh -File scripts/start-python.ps1 -Detached    # 后台（写 local/dev-logs/，与 dev-up 同款）
#
# 为什么需要它（2026-09-10 踩坑 · 工作日志「自由对话 internal 复发」）：
#   dev-up.ps1 的环境注入只发生在它自己的进程里；手动 `uv run uvicorn` 会漏
#   APP_ASR_MODEL / HF_HUB_OFFLINE=1 → settings.asr_model="" → WhisperModel 按
#   repo_id 下载 → 离线失败（LocalEntryNotFoundError）→ 自由对话/评分 ASR 全报 internal。
#   本脚本与 dev-up.ps1 同款注入；要停：按端口杀 8000（`pwsh -File scripts/dev-up.ps1 stop` 亦可）。
# ============================================================
param([switch]$Detached)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$LogDir = Join-Path $Root "local\dev-logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

# --- HF 缓存（与 dev-up.ps1 同口径，2026-09-07 修正）：默认缓存有模型时不设 HF_HOME，
#     仅默认缓存缺失才切仓库 data/models（main.py setdefault 兜底）
if (-not $env:HF_HOME) {
    if (-not (Test-Path (Join-Path $env:USERPROFILE ".cache\huggingface\hub"))) {
        $env:HF_HOME = Join-Path $Root "data\models"
    }
}
if (-not $env:HF_HUB_OFFLINE) { $env:HF_HUB_OFFLINE = "1" }
if (-not $env:HF_HUB_DISABLE_XET) { $env:HF_HUB_DISABLE_XET = "1" }

# --- ASR 模型直载：本地完整快照（含 model.bin）→ APP_ASR_MODEL 直指该目录（完全绕开 HF/网络）
$ModelSnapshotRoot = Join-Path $env:USERPROFILE ".cache\huggingface\hub\models--Systran--faster-whisper-small\snapshots"
if (-not $env:APP_ASR_MODEL -and (Test-Path $ModelSnapshotRoot)) {
    $snap =
        Get-ChildItem $ModelSnapshotRoot -Directory -ErrorAction SilentlyContinue |
        Where-Object { Test-Path (Join-Path $_.FullName "model.bin") } |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($snap) { $env:APP_ASR_MODEL = $snap.FullName }
}

# --- 根 .env 注入（setdefault 语义：仅未显式设置时；空值跳过交给各服务 .env 层）
$EnvFile = Join-Path $Root ".env"
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$') {
            $name = $matches[1].TrimStart([char]0xFEFF)
            $val = $matches[2].Trim('"').Trim("'")
            if ($val -ne "" -and -not (Test-Path "env:$name")) {
                Set-Item -Path "env:$name" -Value $val
            }
        }
    }
}

$cmd = "Set-Location '$Root\services\python'; uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"
if ($Detached) {
    Start-Process -FilePath (Get-Command pwsh).Source -WindowStyle Hidden -WorkingDirectory "$Root\services\python" `
        -RedirectStandardOutput (Join-Path $LogDir "python-8000.out.log") `
        -RedirectStandardError (Join-Path $LogDir "python-8000.err.log") `
        -ArgumentList "-NoProfile", "-Command", $cmd
    Write-Host "python 已后台启动（日志：local/dev-logs/python-8000.{out,err}.log）。环境注入确认：APP_ASR_MODEL=$env:APP_ASR_MODEL"
} else {
    Invoke-Expression $cmd
}
