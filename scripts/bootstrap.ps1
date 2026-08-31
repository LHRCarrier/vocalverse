# VocalVerse 开发环境自检（Windows PowerShell）
# 用法：.\scripts\bootstrap.ps1
$ErrorActionPreference = 'Continue'

function Check($name, $cmd, $expected) {
    $found = Get-Command $cmd -ErrorAction SilentlyContinue
    if (-not $found) {
        Write-Host "[缺] $name —— 未安装 ($expected)"
    }
    else {
        $version = & $cmd --version 2>$null | Select-Object -First 1
        Write-Host "[有] $name —— $version"
    }
}

Write-Host '== VocalVerse 工具链自检 =='
Check 'Node'   'node'   '需 >= 22（.nvmrc）'
Check 'pnpm'   'pnpm'   '需 >= 9（npm i -g pnpm@9）'
Check 'Python' 'python' '需 3.12（.python-version）'
Check 'uv'     'uv'     '需安装：powershell -c "irm https://astral.sh/uv/install.ps1 | iex"'
Check 'Java'   'java'   '需 21 (Temurin)'
Check 'Maven'  'mvn'    '需 3.9（mvn -N wrapper:wrapper 生成 mvnw）'
Check 'Docker' 'docker' '需 Docker Desktop + WSL2'
Check 'git'    'git'    '需 git（core.autocrlf input + core.longpaths true）'
Check 'ffmpeg' 'ffmpeg' '需安装：winget install ffmpeg'

Write-Host ''
Write-Host '提示：'
Write-Host '  1. 敏感信息一律放各服务 .env（已 gitignore），公开仓库严禁密钥'
Write-Host '  2. pre-commit 安装：pip install pre-commit && pre-commit install'
Write-Host '  3. WSL2 内存建议 .wslconfig 设 memory=8GB（Docker Desktop 资源）'
