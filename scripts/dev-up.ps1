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
# 前置：Docker Desktop 已起且 `docker compose up -d postgres redis`
#       已 healthy（脚本不负责数据库容器）。
# ============================================================
param(
    [ValidateSet("start", "stop", "status")]
    [string]$Action = "start"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$LogDir = Join-Path $Root "local\dev-logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

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

switch ($Action) {
    "status" {
        foreach ($p in 8000, 8080, 5173) {
            $pids = Get-PortPid $p
            $ok = $pids.Count -gt 0
            Write-Host ("  {0,5}: {1}" -f $p, ($(if ($ok) { "LISTENING (pid {0})" -f ($pids -join ',') } else { "down" })))
        }
        Write-Host "  health: python="(Test-Health py "http://127.0.0.1:8000/readyz")""
        Write-Host "  health: java="(Test-Health java "http://127.0.0.1:8080/api/v1/ping")""
        # vite 默认绑 localhost（::1），127.0.0.1 会 refused（2026-09-04 踩坑）
        Write-Host "  health: vite="(Test-Health vite "http://localhost:5173" "web")""
        break
    }
    "stop" {
        foreach ($p in 8000, 8080, 5173) {
            foreach ($procId in (Get-PortPid $p)) {
                Write-Host "  killing $procId (port $p)..."
                taskkill /PID $procId /T /F | Out-Null
            }
        }
        Write-Host "  done。日志保留在 local/dev-logs/"
        break
    }
    default {
        Write-Host "== 启动 Python :8000（uvicorn --reload）=="
        if ((Get-PortPid 8000).Count -eq 0) {
            Start-Detached "python-8000" "Set-Location '$Root\services\python'; uv run uvicorn app.main:app --reload --port 8000" "$Root\services\python"
        } else { Write-Host "  已在运行，跳过。" }

        Write-Host "== 启动 Java :8080（mvn spring-boot:run）=="
        if ((Get-PortPid 8080).Count -eq 0) {
            Start-Detached "java-8080" "Set-Location '$Root\services\java'; mvn spring-boot:run" "$Root\services\java"
        } else { Write-Host "  已在运行，跳过。" }

        Write-Host "== 启动 Vite :5173（pnpm dev）=="
        if ((Get-PortPid 5173).Count -eq 0) {
            Start-Detached "vite-5173" "Set-Location '$Root\apps\web'; pnpm dev" "$Root\apps\web"
        } else { Write-Host "  已在运行，跳过。" }

        Write-Host "== 健康等待（python≈8s / vite≈10s / java≈30-60s）=="
        $deadline = (Get-Date).AddSeconds(120)
        $py = $false; $vt = $false; $jv = $false
        while ((Get-Date) -lt $deadline -and -not ($py -and $vt -and $jv)) {
            if (-not $py) { $py = Test-Health py "http://127.0.0.1:8000/readyz" }
            if (-not $vt) { $vt = Test-Health vite "http://localhost:5173" "web" }
            if (-not $jv) { $jv = Test-Health java "http://127.0.0.1:8080/api/v1/ping" }
            if (-not ($py -and $vt -and $jv)) { Start-Sleep -Seconds 3 }
        }
        Write-Host ("  python(8000): {0}  vite(5173): {1}  java(8080): {2}" -f $py, $vt, $jv)
        if (-not ($py -and $vt -and $jv)) {
            Write-Host "  ⚠️ 有服务未就绪，看日志：local/dev-logs/*.err.log（Docker Desktop 起了吗？）"
        }
        Write-Host "  完成。服务与终端已解耦：关终端不再提示 Terminate batch job。"
        break
    }
}
