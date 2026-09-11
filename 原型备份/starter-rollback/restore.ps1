# ============================================================
#  VocalVerse · 撤回"首页今日练习启动器"
#
#  用法（在项目根目录）：
#     powershell -ExecutionPolicy Bypass -File starter-rollback\restore.ps1
#  或右键本文件 →「使用 PowerShell 运行」
#
#  做了什么：
#    1) 用 starter-rollback/index.html.orig 覆盖回 index.html
#       （逐字节还原成改造前的"AI 输入框"版本，含 SHA256 校验）
#    2) 加 -All 时再把 starter-rollback\ 整个删掉
#
#  说明：本次改造只动了 index.html 一个文件（新增一段 .starter 的 CSS +
#        替换 hero 里那张卡片），所以还原只需要这一个副本。
#        脚本可重复执行；副本丢失时会明确报错，不会乱改文件。
# ============================================================
[CmdletBinding()]
param(
  [switch]$All
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot          # starter-rollback 的上一级 = 项目根
$index = Join-Path $root 'index.html'
$orig = Join-Path $PSScriptRoot 'index.html.orig'

Write-Host ""
Write-Host "  撤回 首页今日练习启动器" -ForegroundColor Cyan
Write-Host "  项目目录：$root"
Write-Host ""

if (-not (Test-Path $index)) { throw "找不到 index.html：$index" }
if (-not (Test-Path $orig)) { throw "找不到原始副本：$orig（没有它就不知道要还原成什么样，已中止）" }

$now = (Get-FileHash $index -Algorithm SHA256).Hash
$was = (Get-FileHash $orig -Algorithm SHA256).Hash

if ($now -eq $was) {
  Write-Host "  = index.html 与原始副本一致，无需还原" -ForegroundColor DarkGray
} else {
  Copy-Item $orig $index -Force
  $after = (Get-FileHash $index -Algorithm SHA256).Hash
  if ($after -eq $was) {
    Write-Host "  ✓ index.html 已还原为改造前的版本（SHA256 校验通过）" -ForegroundColor Green
  } else {
    throw "还原后校验不一致，请手动把 starter-rollback\index.html.orig 覆盖到 index.html"
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
Write-Host "  完成。刷新页面即可看到原来的输入框版首页。" -ForegroundColor Cyan
Write-Host ""
