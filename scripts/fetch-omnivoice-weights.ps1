# OmniVoice 权重下载/复用（VocalVerse）。
#
# 为什么需要它：权重约 **3.28 GB**（`model.safetensors` 2.45 GB + `audio_tokenizer/model.safetensors`
# 806 MB + tokenizer/config），**不入库**（红线）。但队友要跑本地克隆音色就得有它，而
# `huggingface.co` 在内网直连不通（实测超时）—— 所以这里给一条确定的路：
#
#   ① 本机已有缓存 → 直接复制（最快，零网络）
#   ② 否则走 HF 镜像下载（默认 hf-mirror.com，实测可达）
#
# 默认下载到 **`<仓库根>/data/models`**（已在 .gitignore）：边车的权重解析顺序里
# 第 3 位就是这个位置，所以**用本脚本下完即零配置**（`start-omnivoice-sidecar.ps1`
# 与 `dev-up.ps1 -WithVoice` 都会自动找到它）。
#
# 用法：
#   pwsh -File scripts/fetch-omnivoice-weights.ps1                     # 下到 <仓库>/data/models
#   pwsh -File scripts/fetch-omnivoice-weights.ps1 -FromLocal D:\hf\hub # 从本机已有缓存复制
#   pwsh -File scripts/fetch-omnivoice-weights.ps1 -Only "config.json"  # 只下一个文件（验证链路/试网速）
#   pwsh -File scripts/fetch-omnivoice-weights.ps1 -Endpoint https://huggingface.co   # 能直连时用官方
#   pwsh -File scripts/fetch-omnivoice-weights.ps1 -Check               # 只体检，不下载
#
# ⚠️ 用 pwsh 7（Windows PowerShell 5.1 会因无 BOM 的 UTF-8 中文注释报语法错）。
[CmdletBinding()]
param(
  # HF 缓存根（会生成 models--k2-fsa--OmniVoice/snapshots/<rev>/ 结构）
  [string]$Dest,
  [string]$Repo = 'k2-fsa/OmniVoice',
  # 下载源。内网直连 huggingface.co 实测超时，故默认走镜像；能直连时用 -Endpoint https://huggingface.co
  [string]$Endpoint = 'https://hf-mirror.com',
  # 从本机已有的 HF 缓存根复制（不给则自动扫常见位置）
  [string]$FromLocal,
  # 只下载匹配这些 glob 的文件（逗号分隔）；用于先验证链路/试网速
  [string]$Only,
  # 重新下载（默认已完整就跳过）
  [switch]$Force,
  # 只体检已有权重，不下载
  [switch]$Check
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
if (-not $Dest) { $Dest = Join-Path $Root 'data\models' }
$SnapRoot = Join-Path $Dest ("models--" + ($Repo -replace '/', '--') + "\snapshots")

# ── 权重完整性判据（按本仓实测的定稿 revision）───────────────────────────────
# 判据是「存在 + 不小于下限」而不是「字节数完全相等」：上游换 revision 时字段会变，
# 而"少了 806MB 的 audio_tokenizer"这种半成品才是要拦住的真问题。
$Required = @(
  @{ Path = 'config.json';                       MinBytes = 0 },
  @{ Path = 'tokenizer.json';                    MinBytes = 1MB },
  @{ Path = 'model.safetensors';                 MinBytes = 2GB },
  @{ Path = 'audio_tokenizer/model.safetensors'; MinBytes = 500MB }
)

function Get-LatestSnapshot([string]$root) {
  if (-not (Test-Path $root)) { return $null }
  $revs = Get-ChildItem $root -Directory -ErrorAction SilentlyContinue |
  Sort-Object Name -Descending
  if (-not $revs) { return $null }
  return $revs[0].FullName
}

function Get-RealLength([string]$path) {
  # ⚠️ HF 缓存里 snapshots/<rev>/xxx 是指向 blobs/ 的**符号链接**，
  #    对链接取 .Length 会得到 0 —— 直接用它做体检会把完整权重误判成"缺失"。
  $item = Get-Item -LiteralPath $path -Force
  if ($item.LinkType -and $item.Target) {
    $target = @($item.Target)[0]
    if (-not [System.IO.Path]::IsPathRooted($target)) {
      $target = Join-Path (Split-Path -Parent $item.FullName) $target
    }
    return (Get-Item -LiteralPath $target -Force).Length
  }
  return $item.Length
}

function Test-Weights([string]$snap) {
  $missing = @()
  $total = 0
  foreach ($r in $Required) {
    $p = Join-Path $snap $r.Path
    if (-not (Test-Path $p)) { $missing += "$($r.Path)（缺失）"; continue }
    $len = Get-RealLength $p
    $total += $len
    if ($r.MinBytes -gt 0 -and $len -lt $r.MinBytes) {
      $missing += ("{0}（{1:N1} MB < 下限 {2:N1} MB）" -f $r.Path, ($len / 1MB), ($r.MinBytes / 1MB))
    }
  }
  return [pscustomobject]@{ Ok = ($missing.Count -eq 0); Missing = $missing; Total = $total }
}

function Show-Snapshot([string]$snap) {
  Write-Host "  快照：$snap"
  foreach ($r in $Required) {
    $p = Join-Path $snap $r.Path
    if (Test-Path $p) {
      Write-Host ("    {0,-38} {1,14:N0} B" -f $r.Path, (Get-RealLength $p))
    } else {
      Write-Host ("    {0,-38} {1}" -f $r.Path, '缺失') -ForegroundColor Yellow
    }
  }
}

Write-Host "== OmniVoice 权重 =="
Write-Host "  仓库：$Repo"
Write-Host "  目标：$Dest"

$existing = Get-LatestSnapshot $SnapRoot
if ($existing) {
  $v = Test-Weights $existing
  if ($v.Ok -and -not $Force) {
    Write-Host "  [1/3] 已存在且完整，跳过下载。" -ForegroundColor Green
    Show-Snapshot $existing
    Write-Host ""
    Write-Host "合计约 {0:N2} GB。直接起边车即可：" -f ($v.Total / 1GB)
    Write-Host "  pwsh -File scripts/start-omnivoice-sidecar.ps1"
    exit 0
  }
  if ($Force) { Write-Host "  [1/3] -Force：忽略已有副本，重新下载。" }
  else { Write-Host "  [1/3] 已有副本不完整：$($v.Missing -join '；')" -ForegroundColor Yellow }
} else {
  Write-Host "  [1/3] 目标位置暂无副本。"
}

if ($Check) {
  Write-Host "  -Check：只体检不下载，退出。" -ForegroundColor Yellow
  if ($existing) { Show-Snapshot $existing }
  exit 1
}

New-Item -ItemType Directory -Force -Path $Dest | Out-Null

# ── 路径一：从本机已有缓存复制（优先，零网络）────────────────────────────────
# 自动扫描常见 HF 缓存位置；也可显式 -FromLocal。
$scan = @()
if ($FromLocal) { $scan += $FromLocal }
if ($env:OMNIVOICE_HF_CACHE) { $scan += $env:OMNIVOICE_HF_CACHE }
$scan += (Join-Path $env:USERPROFILE '.cache/huggingface/hub')
if ($env:LOCALAPPDATA) { $scan += (Join-Path $env:LOCALAPPDATA 'huggingface/hub') }

$srcSnap = $null
foreach ($c in $scan) {
  if (-not $c) { continue }
  $s = Get-LatestSnapshot (Join-Path $c ("models--" + ($Repo -replace '/', '--') + "\snapshots"))
  if ($s -and (Test-Weights $s).Ok) { $srcSnap = $s; $srcRoot = $c; break }
}

if ($srcSnap -and -not $Force) {
  Write-Host "  [2/3] 发现本机已有完整缓存，直接复制（不走网络）：" -ForegroundColor Green
  Write-Host "        源：$srcSnap"
  $dst = Join-Path $Dest ("models--" + ($Repo -replace '/', '--'))
  # robocopy 的返回码 0~7 都是成功（>=8 才是失败），别用 $LASTEXITCODE -ne 0 判错
  & robocopy $srcRoot $Dest ("models--" + ($Repo -replace '/', '--')) /E /NFL /NDL /NJH /NJS /R:1 /W:1 | Out-Null
  if ($LASTEXITCODE -ge 8) { throw "robocopy 复制失败（exit=$LASTEXITCODE）" }
  Write-Host "        已复制到：$dst"
} else {
  # ── 路径二：下载 ──────────────────────────────────────────────────────────
  Write-Host "  [2/3] 下载（源 $Endpoint；约 3.28 GB，视网速 5~60 分钟）..."

  # 找一个能 import huggingface_hub 的 python：优先本仓 venv（已随 faster-whisper 装上），
  # 其次 OMNIVOICE_PYTHON，最后 `uv run --with`。**不引入新依赖**。
  $pyCandidates = @()
  if ($env:OMNIVOICE_PYTHON) { $pyCandidates += $env:OMNIVOICE_PYTHON }
  $pyCandidates += (Join-Path $Root 'services/python/.venv/Scripts/python.exe')
  $pyCandidates += (Join-Path $Root 'services/python/.venv/bin/python')

  $py = $null
  foreach ($c in $pyCandidates) {
    if (-not (Test-Path $c)) { continue }
    & $c -c "import huggingface_hub" 2>$null
    if ($LASTEXITCODE -eq 0) { $py = $c; break }
  }
  if (-not $py) {
    $uv = Get-Command uv -ErrorAction SilentlyContinue
    if ($uv) {
      Write-Host "        本仓 venv 里没有 huggingface_hub，改用 uv 临时装（uv run --with）"
      $py = '__UV__'
    } else {
      throw "没找到可用 python（需要能 import huggingface_hub）。先跑 scripts/dev-up.ps1 生成 services/python/.venv，或装 uv。"
    }
  }

  $script = @'
import os, sys
from huggingface_hub import snapshot_download
dest, repo, only = sys.argv[1], sys.argv[2], sys.argv[3]
allow = [p.strip() for p in only.split(",") if p.strip()] or None
path = snapshot_download(repo_id=repo, cache_dir=dest, allow_patterns=allow)
print("SNAPSHOT=" + path)
'@

  $env:HF_ENDPOINT = $Endpoint
  $env:HF_HUB_DISABLE_TELEMETRY = '1'
  $env:HF_HUB_ENABLE_HF_TRANSFER = '0'  # 不额外要求 hf_transfer，普通 HTTP 就够

  $tmp = Join-Path $env:TEMP ("vv-fetch-omnivoice-{0}.py" -f ([guid]::NewGuid().ToString('N').Substring(0, 8)))
  Set-Content -Path $tmp -Value $script -Encoding utf8
  try {
    if ($py -eq '__UV__') {
      & uv run --with huggingface_hub python $tmp $Dest $Repo $Only
    } else {
      & $py $tmp $Dest $Repo $Only
    }
    if ($LASTEXITCODE -ne 0) { throw "下载失败（exit=$LASTEXITCODE）。可换 -Endpoint 或重跑（断点续传）。" }
  } finally {
    Remove-Item $tmp -Force -ErrorAction SilentlyContinue
  }
}

# ── 收尾：体检 ──────────────────────────────────────────────────────────────
Write-Host "  [3/3] 体检："
$snap = Get-LatestSnapshot $SnapRoot
if (-not $snap) { throw "下载/复制完成但没找到快照目录：$SnapRoot" }
$v = Test-Weights $snap
Show-Snapshot $snap
if (-not $v.Ok) {
  Write-Host ""
  Write-Host "✗ 权重不完整：$($v.Missing -join '；')" -ForegroundColor Red
  Write-Host "  重跑本脚本可续传；若反复失败，用 -FromLocal <已下好的 HF 缓存根> 从别人机器拷。" -ForegroundColor Red
  exit 1
}
Write-Host ""
Write-Host ("✓ 权重就绪（合计约 {0:N2} GB）" -f ($v.Total / 1GB)) -ForegroundColor Green
Write-Host "  边车会自动找到它（<仓库>/data/models 是默认查找位置之一），直接起："
Write-Host "    pwsh -File scripts/start-omnivoice-sidecar.ps1"
Write-Host "  或随三端一起起："
Write-Host "    pwsh -File scripts/dev-up.ps1 start -WithVoice"
