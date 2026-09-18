# ============================================================
#  VocalVerse · 撤回 "showcase 页面改成真实 App 界面" 这次改动
#
#  用法（在项目根目录）：
#     powershell -ExecutionPolicy Bypass -File showcase-rollback\restore.ps1
#  或右键本文件 →「使用 PowerShell 运行」
#
#  做了什么：
#    1) 用备份覆盖回两个被改的文件（SHA256 校验）：
#         showcase.html                ← showcase-rollback\showcase.html.orig
#         js\showcase-interactions.js  ← showcase-rollback\showcase-interactions.js.orig
#    2) 加 -All 时再把本次新增的素材目录和本目录一起删掉：
#         assets\app-shots\（9 张 app 截图）+ showcase-rollback\
#
#  说明：本次改动只涉及上面两个文件 + 一个新增素材目录，其它文件一律未动。
#        脚本可重复执行；备份缺失时会明确报错，不会乱改文件。
# ============================================================
[CmdletBinding()]
param(
  [switch]$All
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot          # showcase-rollback 的上一级 = 项目根

Write-Host ""
Write-Host "  撤回 showcase 页面改动" -ForegroundColor Cyan
Write-Host "  项目目录：$root"
Write-Host ""

$pairs = @(
  @{ now = (Join-Path $root 'showcase.html');                 orig = (Join-Path $PSScriptRoot 'showcase.html.orig') },
  @{ now = (Join-Path $root 'js\showcase-interactions.js');   orig = (Join-Path $PSScriptRoot 'showcase-interactions.js.orig') }
)

foreach ($p in $pairs) {
  $name = $p.now.Replace("$root\", '')
  if (-not (Test-Path $p.orig)) { throw "找不到备份：$($p.orig)（没有它就无法还原，已中止）" }
  if (-not (Test-Path $p.now)) { Write-Host "  ! $name 不存在，跳过" -ForegroundColor Yellow; continue }

  if ((Get-FileHash $p.now -Algorithm SHA256).Hash -eq (Get-FileHash $p.orig -Algorithm SHA256).Hash) {
    Write-Host "  = $name 与备份一致，无需还原" -ForegroundColor DarkGray
  } else {
    Copy-Item $p.orig $p.now -Force
    if ((Get-FileHash $p.now -Algorithm SHA256).Hash -eq (Get-FileHash $p.orig -Algorithm SHA256).Hash) {
      Write-Host "  ✓ $name 已还原（SHA256 校验通过）" -ForegroundColor Green
    } else {
      throw "还原后校验不一致：$name"
    }
  }
}

if ($All) {
  $shots = Join-Path $root 'assets\app-shots'
  if (Test-Path $shots) { Remove-Item -Recurse -Force $shots; Write-Host "  ✓ 已删除 assets\app-shots\（本次新增的 9 张截图）" -ForegroundColor Green }
  Set-Location $root
  Remove-Item -Recurse -Force $PSScriptRoot
  Write-Host "  ✓ 已删除 showcase-rollback\（-All）" -ForegroundColor Green
} else {
  Write-Host "  = 保留了 assets\app-shots\ 与 showcase-rollback\" -ForegroundColor DarkGray
  Write-Host "    想连新增素材一起清掉，加 -All 再跑一次。" -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "  完成。刷新页面即可看到改动前的 showcase。" -ForegroundColor Cyan
Write-Host ""
