# ============================================================
# 无线调试一键重连 + 补 reverse 转发（手机联调入口，2026-09-09）
#
# 为什么需要它（都是实测踩过的坑）：
#   1) 无线调试的「连接端口」会轮换——重开无线调试开关 / 重启 / 息屏重连后，
#      端口就换了；对着旧端口重试只会得到 10061（对方 RST）。
#      例：38313 → 41835 就是一次轮换（配对本身仍然有效，不用重新 pair）。
#   2) `adb mdns services` 在校园网/隔离网下经常发现不到任何服务（本机实测为空），
#      所以本脚本主路径是「按 IP 扫端口」，mDNS 只当快速通道。
#   3) `adb reverse tcp:8080/8000` 随 adb 连接存亡——断连重连后转发被清空，
#      打包壳（壳内基址 http://localhost:8000 / http://localhost:8080）立刻 Failed to fetch。
#   4) 无线调试页里会出现两条同一设备（IP 直连 + mDNS 条目），
#      不清理就会报 `adb: more than one device/emulator`，后续 adb 命令全废。
#   5) 手机掉线后 adb 会留下 `offline` 条目，此时连同一端口会失败——
#      每轮先 disconnect 掉坏记录（实测：清掉后立刻连上同一个端口）。
#   6) 手机息屏/打盹时 ping 能通但 TCP 握手被丢（表现为 10060），
#      所以按轮重试而不是一次定生死；扫描超时给足 800ms。
#
# 用法：
#   pwsh -File scripts/phone-reconnect.ps1                     # 用默认 IP，扫默认端口段
#   pwsh -File scripts/phone-reconnect.ps1 -Ip 10.133.37.207
#   pwsh -File scripts/phone-reconnect.ps1 -ScanFrom 30000 -ScanTo 50000 -ScanTimeoutMs 600
#   pwsh -File scripts/phone-reconnect.ps1 -NoReverse          # 只连接，不动转发
#   pwsh -File scripts/phone-reconnect.ps1 -ConnectPort 41835  # 已知端口时跳过扫描
#   pwsh -File scripts/phone-reconnect.ps1 -Retries 5 -RetryDelaySec 8   # 手机爱打盹时多试几轮
#
# 前提（手机侧人工确认，脚本无法代做）：
#   · 无线调试总开关是开的（关掉时端口无人监听，脚本扫不到任何东西）；
#   · 手机与电脑同一个 WLAN，且手机没走蜂窝（可先在手机上 ping 电脑验证）；
#   · 配对关系仍然有效（本脚本不做配对；需要配对时先 adb pair <IP>:<配对端口> <配对码>）。
# ============================================================
[CmdletBinding()]
param(
    # 手机 IP 会随网络切换变化（实测 10.133.37.207 → 10.133.33.148）。
    # 设备已在线时本参数不影响（脚本直接复用 adb devices 里的条目）；
    # 走扫描路径时请填无线调试页显示的 IP。
    [string]$Ip = '10.133.33.148',
    [int]$ConnectPort = 0,
    [int]$ScanFrom = 30000,
    [int]$ScanTo = 50000,
    [int]$ScanTimeoutMs = 600,
    [int]$ScanParallel = 512,
    [int[]]$Ports = @(8080, 8000),
    [int]$Retries = 2,
    [int]$RetryDelaySec = 5,
    [switch]$NoReverse
)

$ErrorActionPreference = 'Continue'

function Write-Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg) { Write-Host "    [OK] $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "    [!] $msg" -ForegroundColor Yellow }

# ---------- 0. 定位 adb ----------
$adb = Join-Path $env:LOCALAPPDATA 'Android\Sdk\platform-tools\adb.exe'
if (-not (Test-Path $adb)) {
    $cmd = Get-Command adb -ErrorAction SilentlyContinue
    if ($cmd) { $adb = $cmd.Source }
}
if (-not ($adb -and (Test-Path $adb))) {
    Write-Host "找不到 adb（期望 $env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe）——先装 Android SDK platform-tools。" -ForegroundColor Red
    exit 1
}
Write-Host "adb：$adb"
Write-Host "目标：$Ip（端口段 $ScanFrom-$ScanTo，超时 ${ScanTimeoutMs}ms，并发 $ScanParallel）"

function Get-AdbDevices {
    param([string]$Filter)
    $lines = (& $adb devices 2>&1) | Select-Object -Skip 1 | Where-Object { $_ -match '\s(device|offline|unauthorized)$' }
    if ($Filter) { $lines = $lines | Where-Object { $_ -like "$Filter*" } }
    return @($lines)
}

# adb devices 一行（或多行）-> 序列号首列
function Split-Serial {
    param([Parameter(ValueFromPipeline = $true)][string]$Line)
    process {
        if (-not $Line) { return }
        ($Line -split '\s+')[0]
    }
}

# 清理 offline/unauthorized 残留记录
function Clear-StaleDevices {
    $stale = Get-AdbDevices | Where-Object { $_ -match '\s(offline|unauthorized)$' }
    foreach ($s in $stale) {
        $serial = Split-Serial $s
        Write-Warn "清理残留记录（$s）"
        $null = & $adb disconnect $serial 2>&1
    }
}

# 手机是否在网（ICMP 预检，省掉一次白扫：手机打盹时扫 2 万个端口要 ~1 分钟）
function Test-PhoneAlive {
    try {
        $p = New-Object System.Net.NetworkInformation.Ping
        for ($i = 0; $i -lt 3; $i++) {
            $r = $p.Send($Ip, 1500)
            if ($r.Status -eq 'Success') { return $true }
        }
    } catch { }
    return $false
}

# 扫一轮端口：返回开放端口数组
function Scan-Ports {
    $found = [System.Collections.Concurrent.ConcurrentBag[int]]::new()
    $total = $ScanTo - $ScanFrom + 1
    for ($base = $ScanFrom; $base -le $ScanTo; $base += $ScanParallel) {
        $end = [Math]::Min($base + $ScanParallel - 1, $ScanTo)
        $jobs = @()
        for ($p = $base; $p -le $end; $p++) {
            $client = [System.Net.Sockets.TcpClient]::new()
            $jobs += [pscustomobject]@{
                Port   = $p
                Client = $client
                Task   = $client.ConnectAsync($Ip, $p)
            }
        }
        $tasks = @($jobs | ForEach-Object { $_.Task })
        $null = [System.Threading.Tasks.Task]::WaitAll($tasks, $ScanTimeoutMs)
        foreach ($j in $jobs) {
            if ($j.Client.Connected) { $found.Add($j.Port) }
            $j.Client.Dispose()
        }
        $done = $end - $ScanFrom + 1
        Write-Progress -Activity '扫描无线调试端口' -Status "$done/$total" -PercentComplete ([int](100 * $done / $total))
    }
    Write-Progress -Activity '扫描无线调试端口' -Completed
    return @($found | Sort-Object -Unique)
}

# 一轮发现：mDNS → 端口扫描 → adb connect；成功返回 endpoint 字符串
function Find-PhoneEndpoint {
    Clear-StaleDevices

    $svc = (& $adb mdns services 2>&1) | Where-Object { $_ -match '_adb-tls-connect' }
    if ($svc) {
        foreach ($s in $svc) {
            $ep = Split-Serial $s
            Write-Host "    mDNS 发现：$ep"
            $r = (& $adb connect $ep 2>&1) -join ' '
            if ($r -match 'connected to|already connected') { return $ep }
            Write-Host "      $r"
        }
    } else {
        Write-Host '    mDNS 无发现（校园网/隔离网下常见），转端口扫描'
    }

    if (-not (Test-PhoneAlive)) {
        Write-Warn 'ICMP 不通（手机息屏/掉网/走了蜂窝），本轮跳过扫描——把手机叫醒再试'
        return $null
    }

    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $ports = Scan-Ports
    Write-Host "    扫描耗时 $([int]$sw.Elapsed.TotalSeconds)s，开放端口：$(if ($ports) { $ports -join ', ' } else { '（无）' })"
    foreach ($p in $ports) {
        $r = (& $adb connect "$Ip`:$p" 2>&1) -join ' '
        Write-Host "    connect $Ip`:$p -> $r"
        if ($r -match 'connected to|already connected') { return "$Ip`:$p" }
    }
    return $null
}

# ---------- 1. 已在线？ ----------
Write-Step '检查是否已有在线设备'
$target = $null
$online = @(Get-AdbDevices | Where-Object { $_ -match '\sdevice$' })
if ($online.Count -gt 0) {
    $online | ForEach-Object { Write-Ok "已在线：$_" }
    # 注意：$online[0] 在只有一台设备时 $online 是字符串，索引会取到首字符（'1'）——先强制成数组再取
    $target = Split-Serial $online[0]
    Write-Host "    复用已有连接：$target"
} else {
    if ($ConnectPort -gt 0) {
        Write-Step "直接使用指定端口 $Ip`:$ConnectPort"
        Clear-StaleDevices
        $r = (& $adb connect "$Ip`:$ConnectPort" 2>&1) -join ' '
        Write-Host "    $r"
        if ($r -match 'connected to|already connected') { $target = "$Ip`:$ConnectPort" }
    }

    if (-not $target) {
        for ($round = 1; $round -le [Math]::Max(1, $Retries); $round++) {
            Write-Step "第 $round/$Retries 轮发现（手机可能在打盹，会重试）"
            $target = Find-PhoneEndpoint
            if ($target) { break }
            if ($round -lt $Retries) {
                Write-Warn "本轮未发现，等 ${RetryDelaySec}s 重试（把手机叫醒/停在无线调试页效果最好）"
                Start-Sleep -Seconds $RetryDelaySec
            }
        }
    }

    if (-not $target) {
        Write-Host "`n没有找到可用的无线调试端口。" -ForegroundColor Red
        Write-Host @"
请按顺序排查（脚本无法代做手机侧动作）：
  1. 手机「设置 → 系统 → 开发者选项 → 无线调试」总开关是否开着？关了就打开，端口会换新的。
  2. 点进无线调试页，抄「IP 地址和端口」那行（是 IP:端口，不是配对端口），用 -ConnectPort 指定再跑一次。
  3. 手机别熄屏（临时把休眠设 10 分钟），息屏时 adbd 可能不再应答。
  4. 手机是否还在同一 WLAN（蜂窝上网时电脑扫不到）。
  5. 网络是否开了客户端隔离：手机 ping 电脑若不通，无线调试基本无解 —— 改用 USB 线（最稳），或让手机开热点给电脑。
"@
        exit 1
    }
}

# ---------- 2. 去重（IP 直连 + mDNS 同一设备）----------
Write-Step '清理重复条目（否则 adb 会报 more than one device）'
$devs = Get-AdbDevices
$serials = @($devs | ForEach-Object { Split-Serial $_ })
Write-Host "    当前设备：$($serials -join ' | ')"
if ($serials.Count -gt 1) {
    $keep = if ($target -and ($serials -contains $target)) { $target } else { $serials[0] }
    foreach ($s in $serials) {
        if ($s -ne $keep) {
            $r = (& $adb disconnect $s 2>&1) -join ' '
            Write-Warn "断开 $s：$r"
        }
    }
    $target = $keep
} else {
    $target = $serials[0]
}
Write-Ok "使用设备：$target"

# ---------- 3. 设备体检 ----------
Write-Step '设备信息'
$model = (& $adb -s $target shell getprop ro.product.model 2>&1) -join ''
$rel = (& $adb -s $target shell getprop ro.build.version.release 2>&1) -join ''
Write-Host "    $model / Android $rel"

# ---------- 4. 补 reverse 转发 ----------
if (-not $NoReverse) {
    Write-Step "补 reverse 转发（$($Ports -join ', ')）"
    $existing = (& $adb -s $target reverse --list 2>&1) -join "`n"
    foreach ($p in $Ports) {
        if ($existing -match "tcp:$p\s+tcp:$p") {
            Write-Host "    [tcp:$p] 已在，跳过"
        } else {
            $null = & $adb -s $target reverse "tcp:$p" "tcp:$p" 2>&1
            Write-Ok "[tcp:$p] 已建立"
        }
    }
    Write-Host '    当前转发：'
    (& $adb -s $target reverse --list 2>&1) | ForEach-Object { Write-Host "      $_" }

    # ---------- 5. 隧道端到端自检 ----------
    Write-Step '隧道自检（手机 → 电脑后端）'
    $pyCode = (& $adb -s $target shell "curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:8000/readyz" 2>&1) -join ''
    $javaCode = (& $adb -s $target shell "curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:8080/actuator/health" 2>&1) -join ''
    Write-Host "    python 8000/readyz          -> $pyCode"
    Write-Host "    java   8080/actuator/health -> $javaCode"
    if ($pyCode -notmatch '200') { Write-Warn 'python 隧道不通：确认 scripts/dev-up.ps1 已起（且 python 绑 --host 0.0.0.0）' }
    if ($javaCode -notmatch '200') { Write-Warn 'java 隧道不通：确认 8080 有 java 在监听' }
}

Write-Host "`n完成。设备：$target" -ForegroundColor Green
if (-not $NoReverse) { Write-Host '手机上的打包壳（隧道版）现在可以直接重试登录。' }
