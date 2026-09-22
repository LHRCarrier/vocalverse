# OmniVoice 边车的公共解析（**真源**）：该用哪个 python、权重缓存在哪。
#
# 为什么要单独一个文件：`dev-up.ps1`（一键启动）与 `start-omnivoice-sidecar.ps1`（单独起）
# 都要这套顺序，各写一遍必然漂移 —— 本仓已经栽过一次同类坑（端口列表三处各写一遍，
# 加第四端必漏一处）。改顺序只改这里。
#
# 用法（两个脚本都用）：
#     . (Join-Path $PSScriptRoot 'lib/omnivoice.ps1')
#     $py    = Resolve-OmnivoicePython       # 可用 python 路径，找不到返回 $null
#     $cache = Resolve-OmnivoiceCache        # 权重缓存根，找不到返回 $null
#
# 覆盖口子（都优先于下面的内置候选）：
#     $env:OMNIVOICE_PYTHON      → 指定装了 omnivoice 的 python
#     $env:OMNIVOICE_HF_CACHE    → 指定权重缓存根
#     $env:OMNIVOICE_MODEL_DIR   → 直接指定权重快照目录（由边车自己读）

# 仓库根：本文件在 <repo>/scripts/lib/omnivoice.ps1
$script:OmnivoiceRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)

#: 候选 python（按顺序探测；`python` 交给 PATH）。**判据是 `import omnivoice` 成功**。
#: 第 4 条是本机已知的 dev 环境（非本仓资产，队友机器上不存在会自动跳过）——
#: 硬编码一条机器路径换来的是"用户本来就能跑却不被识别"，这个交换是划算的；
#: 要换机器用 `$env:OMNIVOICE_PYTHON` 覆盖，不用改这里。
function Get-OmnivoicePythonCandidates {
    $out = @()
    if ($env:OMNIVOICE_PYTHON) { $out += $env:OMNIVOICE_PYTHON }
    $out += (Join-Path $script:OmnivoiceRoot '.venv-omnivoice/Scripts/python.exe')
    $out += (Join-Path $script:OmnivoiceRoot '.venv-omnivoice/bin/python')
    $out += (Join-Path $script:OmnivoiceRoot 'services/python/.venv/Scripts/python.exe')
    $out += 'F:\WorkingL\VoiceStudio\OmniVoiceStudio-Data\env\project\.venv\Scripts\python.exe'
    $out += 'python'
    return $out
}

function Resolve-OmnivoicePython {
    foreach ($c in (Get-OmnivoicePythonCandidates)) {
        if (-not $c) { continue }
        if ($c -ne 'python' -and -not (Test-Path -LiteralPath $c)) { continue }
        # 探针要吃掉输出：python 不存在时 PowerShell 会写一坨错误，而这里只是"试一下"
        & $c -c "import omnivoice" *> $null
        if ($LASTEXITCODE -eq 0) { return $c }
    }
    return $null
}

#: 候选权重缓存根（HF 缓存结构：<root>/models--k2-fsa--OmniVoice/snapshots/<rev>/）。
#: 顺序与边车 `server.py:default_model_dir()` 保持一致：先本仓（fetch 脚本落点，
#: 下完即零配置），再本机已知环境，最后 HF 默认缓存。
function Get-OmnivoiceCacheCandidates {
    $out = @()
    if ($env:OMNIVOICE_HF_CACHE) { $out += $env:OMNIVOICE_HF_CACHE }
    $out += (Join-Path $script:OmnivoiceRoot 'data/models')
    $out += 'F:\WorkingL\VoiceStudio\OmniVoiceStudio-Data\data\models'
    $out += (Join-Path $env:USERPROFILE '.cache/huggingface/hub')
    if ($env:LOCALAPPDATA) { $out += (Join-Path $env:LOCALAPPDATA 'huggingface/hub') }
    return $out
}

#: 快照是否**看起来完整**：`config.json` + 至少一个根级 `*.safetensors`。
#: 下载可能中断（3.3 GB），只看"目录存在"会把半成品当可用权重 ⇒ 启动后 loadError，
#: 而调用方只看到"边车没就绪"，排查方向被带偏。
function Test-OmnivoiceSnapshot([string]$snap) {
    if (-not (Test-Path (Join-Path $snap 'config.json'))) { return $false }
    return [bool](Get-ChildItem -LiteralPath $snap -Filter '*.safetensors' -File -ErrorAction SilentlyContinue)
}

function Resolve-OmnivoiceCache {
    foreach ($c in (Get-OmnivoiceCacheCandidates)) {
        if (-not $c) { continue }
        $snaps = Join-Path $c 'models--k2-fsa--OmniVoice/snapshots'
        if (-not (Test-Path $snaps)) { continue }
        $ok = Get-ChildItem $snaps -Directory -ErrorAction SilentlyContinue | Where-Object {
            Test-OmnivoiceSnapshot $_.FullName
        }
        if ($ok) { return $c }
    }
    return $null
}

#: 找不到权重时的可读指引（两个脚本共用同一段话，避免口径漂移）
function Write-OmnivoiceWeightsHint {
    Write-Host "  ⏭ 跳过：没找到 OmniVoice 权重（约 3.28 GB，不入库）。任选其一："
    Write-Host "     ① 下载（默认走 hf-mirror.com 镜像，下到 <仓库>\data\models）："
    Write-Host "        pwsh -File scripts/fetch-omnivoice-weights.ps1"
    Write-Host "     ② 复用它处已有缓存：`$env:OMNIVOICE_HF_CACHE = '<HF 缓存根>'"
}
