# ============================================================
# 手机联调防火墙放行（8000/8080 端口级规则）
#
# ⚠️ 需管理员运行：右键 PowerShell → 以管理员身份运行 →
#    pwsh -File scripts/firewall-phone.ps1
#
# 背景（2026-09-10 踩坑）：打包壳手机直连本机后端。java 进程实际运行路径
# （Eclipse Adoptium jdk-21）不在既有程序级放行名单里 → 手机连 8080 的包被
# 防火墙静默丢弃 → 前端报 "Failed to fetch"，而 python(8000) 恰好有匹配规则
# 所以能通。**端口规则不依赖程序路径**：换 JDK / 换后端起法都不会失效。
# ============================================================
$ErrorActionPreference = "Stop"

foreach ($p in 8000, 8080) {
    $name = "VocalVerse port $p"
    $existing = Get-NetFirewallRule -DisplayName $name -ErrorAction SilentlyContinue
    if ($existing) {
        Write-Host "  [$name] 已存在，跳过。"
    } else {
        New-NetFirewallRule -DisplayName $name -Direction Inbound -Protocol TCP -LocalPort $p -Action Allow -Profile Public,Private | Out-Null
        Write-Host "  [$name] 已添加。"
    }
}

Write-Host "完成。核对：Get-NetFirewallRule | Where-Object { \$_.DisplayName -match 'VocalVerse' }"
