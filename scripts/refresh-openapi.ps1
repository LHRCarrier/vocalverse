# ============================================================
# VocalVerse 契约刷新（docs/06 第 7 章：OpenAPI 构建期生成前端类型）
#
# 用途：后端契约变更后，一步完成「导出 OpenAPI 快照 + 重新生成前端类型」。
# 前置：Python 服务已启动（默认 http://localhost:8000，可用 -Base 覆盖）。
# 用法：.\scripts\refresh-openapi.ps1
# 之后：检查 git diff，将 快照 + 生成文件（+ 后端契约代码）一并提交；
#       CI 双关卡会校验二者与后端一致（python-ci 快照 vs 后端、frontend-ci 生成 vs 快照）。
# ============================================================
param(
    [string]$Base = "http://localhost:8000"
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$SpecPath = Join-Path $Root 'apps\web\src\api\specs\python-openapi.json'
$WebDir = Join-Path $Root 'apps\web'

Write-Host "1/2 导出后端 OpenAPI（$Base/openapi.json）→ $SpecPath"
$resp = Invoke-WebRequest -Uri "$Base/openapi.json" -UseBasicParsing -TimeoutSec 10
# 刻意用 .NET 写入避免 BOM（PS5.1 的 Set-Content UTF8 带 BOM 会让 JSON 解析失败）
[System.IO.File]::WriteAllText($SpecPath, $resp.Content, (New-Object System.Text.UTF8Encoding $false))

Write-Host '2/2 重新生成前端类型（pnpm gen:api）'
Push-Location $WebDir
try {
    pnpm gen:api
    if ($LASTEXITCODE -ne 0) { throw "pnpm gen:api 失败（exit=$LASTEXITCODE）" }
}
finally {
    Pop-Location
}

Write-Host ''
Write-Host '完成。请检查 git diff 后提交：'
Write-Host '  1) apps/web/src/api/specs/python-openapi.json   （快照）'
Write-Host '  2) apps/web/src/api/generated/python-api.d.ts   （生成类型）'
Write-Host '  3) 后端契约代码（若本次变更了 Python 路由/DTO）'
