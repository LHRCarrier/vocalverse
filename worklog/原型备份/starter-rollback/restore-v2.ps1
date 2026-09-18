# ============================================================
#  VocalVerse · 撤回"首页功能全览卡片"（v3 → v2）
#
#  用法（在项目根目录）：
#     powershell -ExecutionPolicy Bypass -File starter-rollback\restore-v2.ps1
#  或右键本文件 →「使用 PowerShell 运行」
#
#  做了什么：
#     用 starter-rollback/index.html.rec-v2 覆盖回 index.html，
#     把首页那张卡从「5 个模块一行铺开的功能全览」还原成
#     v2 的「Speaking / Singing 分段 + 个性化推荐 + Also try chips」。
#
#  说明：本次改造只动了 index.html 一个文件（.starter 那一段 CSS、
#        hero 里那张卡片、以及页尾一段已失效的分段切换脚本），
#        所以还原只需要这一个副本。脚本带 SHA256 校验，可重复执行；
#        副本丢失时会明确报错，不会乱改文件。
#
#  与 restore.ps1 的区别：
#        restore.ps1      → 还原成更早的「AI 输入框」版（index.html.orig）
#        restore-v2.ps1   → 还原成「分段 + 推荐」版（index.html.rec-v2）← 本脚本
# ============================================================
[CmdletBinding()]
param(
  [switch]$All
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot          # starter-rollback 的上一级 = 项目根
$index = Join-Path $root 'index.html'
$snapshot = Join-Path $PSScriptRoot 'index.html.rec-v2'

Write-Host ""
Write-Host "  撤回 首页功能全览卡片（回到 v2 分段 + 推荐版）" -ForegroundColor Cyan
Write-Host "  项目目录：$root"
Write-Host ""

if (-not (Test-Path $index)) { throw "找不到 index.html：$index" }
if (-not (Test-Path $snapshot)) { throw "找不到 v2 副本：$snapshot（没有它就不知道要还原成什么样，已中止）" }

$now = (Get-FileHash $index -Algorithm SHA256).Hash
$was = (Get-FileHash $snapshot -Algorithm SHA256).Hash

if ($now -eq $was) {
  Write-Host "  = index.html 已经与 v2 副本一致，无需还原" -ForegroundColor DarkGray
} else {
  Copy-Item $snapshot $index -Force
  $after = (Get-FileHash $index -Algorithm SHA256).Hash
  if ($after -eq $was) {
    Write-Host "  ✓ index.html 已还原为 v2 版（SHA256 校验通过）" -ForegroundColor Green
  } else {
    throw "还原后校验不一致，请手动把 starter-rollback\index.html.rec-v2 覆盖到 index.html"
  }
}

if ($All) {
  Set-Location $root
  Remove-Item -Recurse -Force $PSScriptRoot
  Write-Host "  ✓ 已删除 starter-rollback\（-All）" -ForegroundColor Green
} else {
  Write-Host "  = 保留了 starter-rollback\（想连它一起删，加 -All 再跑一次）" -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "  完成。刷新页面即可看到 Speaking / Singing 切换的推荐版卡片。" -ForegroundColor Cyan
Write-Host ""
