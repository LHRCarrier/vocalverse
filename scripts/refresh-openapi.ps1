# ============================================================
# VocalVerse 契约刷新（docs/06 第 7 章：OpenAPI 构建期生成前端类型）
#
# 用途：后端契约变更后，一步完成「导出 Python/Java 契约快照 + 重新生成前端类型」。
# 前置：Python 服务已启动（默认 http://localhost:8000）、Java 服务已启动（默认 http://localhost:8080）。
# 用法：.\scripts\refresh-openapi.ps1
#       仅刷新单侧可用 -Base / -JavaBase 覆盖地址；Java 也可不启服务，改用
#       CONTRACT_SNAPSHOT_GENERATE=1 跑 ContractSnapshotTest 重写快照（仅限本地）。
# 之后：检查 git diff，将 快照 + 生成文件（+ 后端契约代码）一并提交；
#       CI 关卡会校验三者一致（python-ci 快照vs后端、java-ci 快照vs Java、frontend-ci 生成vs快照）。
# ============================================================
param(
    [string]$Base = "http://localhost:8000",
    [string]$JavaBase = "http://localhost:8080"
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$PythonSpec = Join-Path $Root 'apps\web\src\api\specs\python-openapi.json'
$JavaSpec = Join-Path $Root 'apps\web\src\api\specs\java-openapi.json'
$WebDir = Join-Path $Root 'apps\web'

Write-Host "1/4 导出后端 OpenAPI（$Base/openapi.json）→ $PythonSpec"
$resp = Invoke-WebRequest -Uri "$Base/openapi.json" -UseBasicParsing -TimeoutSec 10
# 刻意用 .NET 写入避免 BOM（PS5.1 的 Set-Content UTF8 带 BOM 会让 JSON 解析失败）
[System.IO.File]::WriteAllText($PythonSpec, $resp.Content, (New-Object System.Text.UTF8Encoding $false))

Write-Host "2/4 导出 Java 契约（$JavaBase/v3/api-docs）→ $JavaSpec"
$jresp = Invoke-WebRequest -Uri "$JavaBase/v3/api-docs" -UseBasicParsing -TimeoutSec 10
[System.IO.File]::WriteAllText($JavaSpec, $jresp.Content, (New-Object System.Text.UTF8Encoding $false))

Write-Host '3/4 重新生成前端类型（pnpm gen:api）'
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
Write-Host '  1) apps/web/src/api/specs/python-openapi.json   （Python 契约快照）'
Write-Host '  2) apps/web/src/api/specs/java-openapi.json     （Java 契约快照；java-ci 对账）'
Write-Host '  3) apps/web/src/api/generated/                  （生成类型 ×2）'
Write-Host '  4) 后端契约代码（若本次变更了 Python/Java 接口）'
