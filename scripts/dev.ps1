# VocalVerse 一键启动（Windows PowerShell，幂等）
# 用法：.\scripts\dev.ps1            # docker compose 起全部服务
#       .\scripts\dev.ps1 -Dev      # 数据库/缓存用容器，Python 用本地 venv 热重载
param(
    [switch]$Dev
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot

function Test-Command($Name) {
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

Write-Host '== VocalVerse dev 启动 =='

# ---- 护栏 ----
if (-not (Test-Command 'docker')) { Write-Error '未找到 docker，请安装 Docker Desktop 并开启 WSL2' }
if ($Dev -and -not (Test-Command 'python')) { Write-Error '未找到 python，请安装 Python 3.12' }
if ($Dev -and -not (Test-Command 'node')) { Write-Error '未找到 node，请安装 Node 22 LTS' }

# ---- 端口检测（8080 常被占用）----
foreach ($port in 8000, 8080, 5173, 8088, 5432, 6379) {
    $listener = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if ($listener -and -not $Dev) {
        Write-Warning "端口 $port 已被占用（PID $($listener.OwningProcess)），请先释放"
    }
}

# ---- 一键起（不热更新）----
Push-Location $Root
try {
    docker compose up -d --build
    docker compose ps
    Write-Host ''
    Write-Host '  前端   http://localhost:8088'
    Write-Host '  Python http://localhost:8000/docs'
    Write-Host '  Java   http://localhost:8080/swagger-ui.html'
    Write-Host ''
    if ($Dev) {
        Write-Host '（-Dev 模式：以上为容器版本；另起本地热重载见各服务 README）'
    }
}
finally {
    Pop-Location
}
