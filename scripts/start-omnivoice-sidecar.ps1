# OmniVoice 边车启动器（VocalVerse）。
#
# 为什么要有一个启动器，而不是让 README 写一段命令：
# "怎么起边车"的答案本来会散在三处 —— README 一段命令、.env 一处注释、
# 以及"你得先知道该用哪个 python"（OmniVoice 装在独立环境里，不在 python-api 的 venv）。
# 一条命令能起、起来时把关键事实打出来，比让人去拼三处信息强。
#
# 用法：
#   pwsh -File scripts/start-omnivoice-sidecar.ps1
#   pwsh -File scripts/start-omnivoice-sidecar.ps1 -Port 8766 -Dtype float32 -Preload
#   pwsh -File scripts/start-omnivoice-sidecar.ps1 -Fake          # 无 GPU 的链路冒烟
#
# ⚠️ 若用 Windows PowerShell 5.1 读本脚本：它按 GBK 读无 BOM 的 .ps1，
#    中文注释会被读成语法错误。请用 pwsh 7（本仓 .tool-versions/CI 同为 7）。
[CmdletBinding()]
param(
  [int]$Port = 8765,
  [ValidateSet('float16', 'float32')][string]$Dtype = 'float16',
  [string]$Host_ = '127.0.0.1',
  # 同步加载模型（默认后台加载，/health 先可用）
  [switch]$Preload,
  # 占位引擎：不加载权重、只出静音 WAV（无 GPU 机器与 CI 冒烟用）
  [switch]$Fake,
  # OmniVoice 快照目录（HF cache 根或具体 snapshot；不传就按顺序找）
  [string]$HfCache,
  # 装了 omnivoice 的 python。不传就按顺序找
  [string]$Python
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$server = Join-Path $root 'services/omnivoice-sidecar/server.py'
if (-not (Test-Path $server)) { throw "找不到 $server —— 请在仓库根运行本脚本" }

# ── 找 python ────────────────────────────────────────────────────────────────
# python 与权重的查找顺序**真源在 scripts/lib/omnivoice.ps1**（与 dev-up.ps1 共用一份，
# 各写一遍必然漂移）。`-Python` 作为最高优先的显式覆盖。
. (Join-Path $PSScriptRoot 'lib/omnivoice.ps1')
if ($Python) { $env:OMNIVOICE_PYTHON = $Python }
if ($HfCache) { $env:OMNIVOICE_HF_CACHE = $HfCache }

$py = Resolve-OmnivoicePython
if ($Fake) {
  # --fake 的**全部意义**就是在没有 omnivoice 环境的机器上验链路，所以这里不能要求
  # `import omnivoice` 成功 —— 退回"任意可用 python"（本仓 venv 优先，其次 PATH）。
  if (-not $py) {
    foreach ($c in @(
        (Join-Path $root 'services/python/.venv/Scripts/python.exe'),
        (Join-Path $root 'services/python/.venv/bin/python'),
        'python'
      )) {
      if ($c -eq 'python' -or (Test-Path -LiteralPath $c)) { $py = $c; break }
    }
  }
  if (-not $py) { throw "没找到任何可用 python（--Fake 也至少需要一个解释器）" }
  Write-Host "[1/4] python: $py"
  Write-Host "[2/4] --Fake：跳过依赖自检（不加载权重、不 import torch）"
} else {
  if (-not $py) {
    Write-Host "✗ 没找到装了 omnivoice 的 python。探测过的位置（scripts/lib/omnivoice.ps1）："
    foreach ($c in (Get-OmnivoicePythonCandidates)) { Write-Host "    $c" }
    Write-Host "  用 -Python <路径> 或设 `$env:OMNIVOICE_PYTHON 指过去；"
    Write-Host "  或自建：python -m venv .venv-omnivoice; .\.venv-omnivoice\Scripts\pip install omnivoice torch soundfile"
    Write-Host "  只想验证链路（不合成真音频）：加 -Fake。"
    exit 2
  }
  Write-Host "[1/4] python: $py"
  Write-Host "[2/4] 依赖自检通过（omnivoice 可导入）"
}

# ── 启动前先检查：它真的需要启动吗 ───────────────────────────────────────────
# 报错说"边车起了吗"、而它其实活得好好的，是最浪费时间的一类排查。
try {
  $h = Invoke-RestMethod "http://${Host_}:${Port}/health" -TimeoutSec 5
  Write-Host "[3/4] ⚠️ $Port 端口上**已经有一个边车在跑**："
  Write-Host ("        ok={0} device={1} dtype={2} sr={3} promptsCached={4}" -f `
      $h.ok, $h.device, $h.dtype, $h.sampleRate, $h.promptsCached)
  Write-Host "      如果是'合成很慢/超时'，先看下面这条，别急着重启："
  if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
    $g = (& nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu --format=csv,noheader) -join ' '
    Write-Host "      GPU 显存/利用率：$g"
    Write-Host "      ⚠️ 显存接近占满时权重会被换出到内存 ⇒ 冷合成要 9~18 秒（热了 ~1.7 秒）。"
    Write-Host "         根治是关掉占显存的程序，重启边车治不了。"
  }
  Write-Host "      确实要重启：先停掉旧进程，再跑本脚本。"
  exit 0
} catch {
  Write-Host "[3/4] $Port 上没有在跑的边车，继续启动"
}

# ── 权重位置 ────────────────────────────────────────────────────────────────
# 只在调用方没给时才猜：HF cache 下 models--k2-fsa--OmniVoice/snapshots/<rev>。
# ⚠️ 权重约 3.3 GB，**不入库**（红线）；换机器需要自己下载或拷一份。
# 查找顺序复用 lib 的真源（`-HfCache` → `$env:OMNIVOICE_HF_CACHE` → <仓库>/data/models
# → 本机已知环境 → HF 默认缓存）。
$cacheRoot = Resolve-OmnivoiceCache
if (-not $Fake) {
  if ($cacheRoot) {
    $env:OMNIVOICE_HF_CACHE = $cacheRoot
    Write-Host "[4/4] 权重缓存：$cacheRoot"
  } else {
    Write-Host "[4/4] ⚠️ 没找到本机 OmniVoice 快照 —— 将回落到仓库 id `k2-fsa/OmniVoice`（首次自动下载，需联网）"
    Write-Host "      探测过的位置（scripts/lib/omnivoice.ps1）："
    foreach ($c in (Get-OmnivoiceCacheCandidates)) { Write-Host "        $c" }
    Write-Host "      一键下载（默认走 hf-mirror.com 镜像，下到 <仓库>\data\models）："
    Write-Host "        pwsh -File scripts/fetch-omnivoice-weights.ps1"
    Write-Host "      复用它处已有缓存：-HfCache <HF 缓存根> 或 `$env:OMNIVOICE_HF_CACHE。"
  }
} else {
  Write-Host "[4/4] --Fake：不需要权重"
}

# 🔴 8 GB 卡上的关键开关（server.py 里也设了同样的默认，这里是双保险）。
#    实测：显存 7911 → 2772 MiB，冷合成 11493 → 2331 ms。
#    ⚠️ 它**必须在 CUDA 初始化之前**设好，所以放在启动进程的环境里而不是脚本内。
if (-not $env:PYTORCH_CUDA_ALLOC_CONF) { $env:PYTORCH_CUDA_ALLOC_CONF = 'expandable_segments:True' }

$argv = @($server, '--host', $Host_, '--port', "$Port", '--dtype', $Dtype)
if ($Preload) { $argv += '--preload' }
if ($Fake) { $argv += '--fake' }

Write-Host ""
Write-Host "启动：$py $($argv -join ' ')"
Write-Host "健康检查：curl http://${Host_}:${Port}/health"
Write-Host "模型加载约 7~8 秒；/health 先可用，ok=true 表示模型就绪。"
Write-Host "（主服务侧：APP_TTS_PROVIDER=auto 会自动优先用它，见 docs/06 §20）"
Write-Host ""
& $py @argv
