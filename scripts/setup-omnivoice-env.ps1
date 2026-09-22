# OmniVoice 边车环境一键安装（VocalVerse）。
#
# 为什么要有它：边车依赖 **torch + 上游 OmniVoice**，这是重依赖（CUDA 版约 3~5 GB），
# **不能装进 services/python/.venv**（那是 CPU 运行时，要能在 CI/演示容器里起）。
# 而"怎么装"的答案散在三处（README 一段命令、边车的依赖自检报错、以及"该用哪个
# python 版本"），队友照着做容易装进错的环境或装成 CPU 版。
#
# 装到哪：默认 **`<仓库>/.venv-omnivoice`** —— 这个位置 `scripts/lib/omnivoice.ps1`
# 会**优先搜索**，所以装完 `scripts/dev-up.ps1 start` 就直接认得，无需再配任何东西。
#
# 装什么（按上游 k2-fsa/OmniVoice 官方 README 的顺序：**先 torch，再 omnivoice**）
#   1. torch==2.8.0+cu128 + torchaudio==2.8.0+cu128   （-Torch cpu 则装 CPU 版）
#   2. omnivoice（PyPI 稳定版；-FromSource 装 GitHub 最新源码）
#   3. soundfile（写 WAV 用）
#
# 用法：
#   pwsh -File scripts/setup-omnivoice-env.ps1                       # CUDA 版（默认）
#   pwsh -File scripts/setup-omnivoice-env.ps1 -Torch cpu            # 只跑 CPU（慢，仅应急）
#   pwsh -File scripts/setup-omnivoice-env.ps1 -FromSource           # 装 GitHub 源码版
#   pwsh -File scripts/setup-omnivoice-env.ps1 -IndexUrl https://pypi.tuna.tsinghua.edu.cn/simple
#   pwsh -File scripts/setup-omnivoice-env.ps1 -Force                # 重建（-Force 会删旧环境）
#
# ⚠️ 用 pwsh 7（Windows PowerShell 5.1 会因无 BOM 的 UTF-8 中文注释报语法错）。
[CmdletBinding()]
param(
  # 目标 venv（默认 <仓库>/.venv-omnivoice —— lib 里的首选搜索位置）
  [string]$VenvDir,
  # 基座 Python 版本（交给 uv 自取解释器）
  [string]$PythonVersion = '3.12',
  # cuda = 装 +cu128 轮子（需要 NVIDIA 驱动）；cpu = 装 CPU 轮子（慢，仅应急）
  [ValidateSet('cuda', 'cpu')][string]$Torch = 'cuda',
  # PyTorch 轮子索引（CUDA 版必须从这里取，PyPI 上没有 +cu128 本地版本号）
  [string]$TorchIndex = 'https://download.pytorch.org/whl/cu128',
  [string]$TorchVersion = '2.8.0',
  # PyPI 索引（留空 = 官方 pypi.org）。国内可换清华/阿里镜像。
  [string]$IndexUrl,
  # 装 GitHub 最新源码而不是 PyPI 稳定版
  [switch]$FromSource,
  [switch]$Force
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
if (-not $VenvDir) { $VenvDir = Join-Path $Root '.venv-omnivoice' }
$venvPy = Join-Path $VenvDir 'Scripts/python.exe'
if (-not (Test-Path $venvPy)) { $venvPy = Join-Path $VenvDir 'bin/python' }

$uv = Get-Command uv -ErrorAction SilentlyContinue
if (-not $uv) {
  throw "没找到 uv。本仓的 Python 依赖一律走 uv（见 README「一次性准备」）：https://docs.astral.sh/uv/"
}
$uv = $uv.Source

$indexArgs = @()
if ($IndexUrl) { $indexArgs += @('--index-url', $IndexUrl) }

$torchLabel = if ($Torch -eq 'cuda') { "$TorchVersion+cu128" } else { $TorchVersion }
Write-Host '== OmniVoice 边车环境 =='
Write-Host "  目标：$VenvDir"
Write-Host "  torch：$torchLabel"
Write-Host "  索引：$(if ($IndexUrl) { $IndexUrl } else { 'https://pypi.org/simple（官方）' })"

# ── 已就绪就跳过（幂等；-Force 才重建）────────────────────────────────────────
if ((Test-Path $venvPy) -and -not $Force) {
  $probe = & $venvPy -c "import omnivoice, torch, soundfile; print('OK', torch.__version__, torch.cuda.is_available())" 2>&1
  if ($LASTEXITCODE -eq 0) {
    Write-Host "  [1/4] 环境已存在且可用，跳过安装：$probe" -ForegroundColor Green
    Write-Host ''
    Write-Host '直接起边车即可（lib 会优先找到这个环境）：'
    Write-Host '  pwsh -File scripts/dev-up.ps1 start'
    exit 0
  }
  Write-Host '  [1/4] 已有环境但不可用（缺包或装坏）→ 继续安装；要重建加 -Force。' -ForegroundColor Yellow
} else {
  Write-Host '  [1/4] 新建环境…'
}

# 解释器位置：uv 在 Windows 建 Scripts/、POSIX 建 bin/。**不要建完立刻断言**——
# 实测（2026-09-21）`uv venv` 返回后目标文件偶尔还不可见（本机沙箱/文件系统可见性延迟），
# 一次 Test-Path 就抛错会把"其实建好了"误报成失败。故轮询 + 失败时打印目录内容便于定位。
function Resolve-VenvPython([string]$dir) {
  $cands = @((Join-Path $dir 'Scripts/python.exe'), (Join-Path $dir 'bin/python'))
  for ($i = 0; $i -lt 10; $i++) {
    foreach ($c in $cands) { if (Test-Path -LiteralPath $c) { return $c } }
    Start-Sleep -Milliseconds 300
  }
  return $null
}

$venvArgs = @('venv', '--python', $PythonVersion)
if ($Force) { $venvArgs += '--clear' }
$venvArgs += $VenvDir
& $uv @venvArgs
if ($LASTEXITCODE -ne 0) { throw "uv venv 失败（exit=$LASTEXITCODE）" }

$venvPy = Resolve-VenvPython $VenvDir
if (-not $venvPy) {
  Write-Host "✗ 建好了 $VenvDir 但找不到解释器。目录实际内容：" -ForegroundColor Red
  Get-ChildItem -LiteralPath $VenvDir -Force -ErrorAction SilentlyContinue |
    ForEach-Object { Write-Host "    $($_.Mode) $($_.Name)" }
  throw "找不到 $VenvDir 下的 python 解释器（期望 Scripts/python.exe 或 bin/python）"
}

$env:VIRTUAL_ENV = $VenvDir
$env:UV_PROJECT_ENVIRONMENT = $VenvDir

# ── ① torch（**必须先行**：omnivoice 依赖它，且 CUDA 轮子只能从 pytorch 索引取）──
Write-Host '  [2/4] 安装 torch（CUDA 版约 2~3 GB，视网速 5~20 分钟）…'
$torchSpecs = if ($Torch -eq 'cuda') {
  @("torch==$TorchVersion+cu128", "torchaudio==$TorchVersion+cu128")
} else {
  @("torch==$TorchVersion", "torchaudio==$TorchVersion")
}
$torchArgs = @('pip', 'install', '--python', $venvPy) + $torchSpecs + $indexArgs
if ($Torch -eq 'cuda') { $torchArgs += @('--extra-index-url', $TorchIndex) }
& $uv @torchArgs
if ($LASTEXITCODE -ne 0) {
  throw "torch 安装失败（exit=$LASTEXITCODE）。CUDA 版失败时先确认显卡驱动/网络；应急可加 -Torch cpu。"
}

# ── ② omnivoice ③ soundfile ──────────────────────────────────────────────────
$omniSpec = if ($FromSource) { 'git+https://github.com/k2-fsa/OmniVoice.git' } else { 'omnivoice' }
Write-Host "  [3/4] 安装 $omniSpec + soundfile…"
$omniArgs = @('pip', 'install', '--python', $venvPy, $omniSpec, 'soundfile') + $indexArgs
& $uv @omniArgs
if ($LASTEXITCODE -ne 0) { throw "omnivoice 安装失败（exit=$LASTEXITCODE）" }

# ── ④ 自检：版本 + CUDA + 能 import 到 OmniVoice ─────────────────────────────
Write-Host '  [4/4] 自检…'
$check = @'
import importlib, sys
ok = True
try:
    import torch, soundfile  # noqa: F401
except Exception as e:
    print("FAIL import torch/soundfile:", e); ok = False
else:
    print(f"torch {torch.__version__}  cuda_available={torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print("  GPU:", torch.cuda.get_device_name(0))
try:
    import omnivoice
    print("omnivoice", getattr(omnivoice, "__version__", "?"), "from", omnivoice.__file__)
    from omnivoice import OmniVoice  # 上游公开 API
    print("OmniVoice 可导入；支持 create_voice_clone_prompt:", hasattr(OmniVoice, "create_voice_clone_prompt"))
except Exception as e:
    print("FAIL import omnivoice:", e); ok = False
sys.exit(0 if ok else 1)
'@
$tmp = Join-Path $env:TEMP ("vv-omni-check-{0}.py" -f ([guid]::NewGuid().ToString('N').Substring(0, 8)))
Set-Content -Path $tmp -Value $check -Encoding utf8
try { & $venvPy $tmp; $checkExit = $LASTEXITCODE } finally { Remove-Item $tmp -Force -ErrorAction SilentlyContinue }

if ($checkExit -ne 0) {
  Write-Host ''
  Write-Host '✗ 自检未通过 —— 环境不可用，别急着起边车。常见原因：' -ForegroundColor Red
  Write-Host '  · CUDA 版 torch 装了但驱动太旧（torch.cuda.is_available() 为 False）→ 升级 NVIDIA 驱动，或临时 -Torch cpu'
  Write-Host '  · 网络半途断 → 重跑本脚本（幂等，会续装）'
  exit 1
}

Write-Host ''
Write-Host '✓ 环境就绪' -ForegroundColor Green
Write-Host "  $venvPy"
Write-Host ''
Write-Host '下一步（lib 会自动优先用这个环境，无需配置）：'
Write-Host '  pwsh -File scripts/dev-up.ps1 start            # 连同三端一起起（含边车）'
Write-Host '  pwsh -File scripts/start-omnivoice-sidecar.ps1 # 只起边车'
Write-Host '  权重还没下？ pwsh -File scripts/fetch-omnivoice-weights.ps1'
