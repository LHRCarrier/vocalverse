# ============================================================
# 手机联调 adb 隧道一键恢复（reverse 转发随 adb 连接丢失）
#
# 背景（2026-09-10）：打包壳隧道版（build-phone.ps1 -Ip localhost）的 App 走
# 手机 localhost:8080/8000，经 `adb reverse` 转发到电脑后端；但 reverse 转发
# **随 adb 连接存在**——断连重连（锁屏/无线调试掉线/重启/网络切换）后被清空，
# 手机上 App 就会 Failed to fetch（Connection refused）。
#
# 用法：
#   pwsh -File scripts/adb-tunnel.ps1            # 检查并补建 8080/8000
#   pwsh -File scripts/adb-tunnel.ps1 -Ports 8080,8000,5173
# ============================================================
param([int[]]$Ports = @(8080, 8000))
$ErrorActionPreference = "Stop"

$adb = Join-Path $env:LOCALAPPDATA "Android\Sdk\platform-tools\adb.exe"
if (-not (Test-Path $adb)) {
    Write-Host "找不到 adb：$adb —— 先装 Android SDK platform-tools 或设置 PATH。"
    exit 1
}

$devices = (& $adb devices 2>&1) | Select-Object -Skip 1 | Where-Object { $_ -match '\sdevice$' }
if (-not $devices) {
    Write-Host "⚠️ 无设备在线（adb devices 为空）——先连接手机（USB 调试或无线调试）再跑本脚本。"
    exit 1
}
$devices | ForEach-Object { Write-Host "设备在线：$_" }

$existing = (& $adb reverse --list 2>&1) -join "`n"
foreach ($p in $Ports) {
    if ($existing -match "tcp:$p\s+tcp:$p") {
        Write-Host "  [tcp:$p] 已在，跳过。"
    } else {
        & $adb reverse "tcp:$p" "tcp:$p" | Out-Null
        Write-Host "  [tcp:$p] 已重建。"
    }
}

Write-Host "=== 当前转发 ==="
& $adb reverse --list 2>&1
Write-Host "完成。手机 App 重试即可（无需重装包）。"
