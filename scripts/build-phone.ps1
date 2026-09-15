# ============================================================
# 手机包一键重建（方案 B 打包壳：web build → cap copy → assembleDebug）
#
# 用法（每次改完 web 后执行一次）：
#   pwsh -File scripts/build-phone.ps1            # 默认 IP 192.168.0.104
#   pwsh -File scripts/build-phone.ps1 -Ip 10.0.0.5
# 产物：apps/mobile/android/app/build/outputs/apk/debug/app-debug.apk
#
# 背景（2026-09-10 方案 B 落地）：打包壳的 API 基址是**构建期写死**的
# （VITE_PYTHON_BASE/VITE_JAVA_BASE），换网络/IP 变了必须先跑本脚本重建，
# 否则 App 还在打旧地址（表现为登录/接口全失败且后端日志看不到请求）。
# ============================================================
param([string]$Ip = "192.168.0.104")
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot

Write-Host "== 1/3 web build（API 基址 -> http://${Ip}:8000 / :8080）=="
Push-Location "$Root\apps\web"
$env:VITE_PYTHON_BASE = "http://${Ip}:8000"
$env:VITE_JAVA_BASE = "http://${Ip}:8080"
pnpm build
Pop-Location

Write-Host "== 2/3 cap copy（web 产物进壳）=="
Push-Location "$Root\apps\mobile"
npx cap copy android
Pop-Location

Write-Host "== 3/3 assembleDebug =="
Push-Location "$Root\apps\mobile\android"
.\gradlew.bat assembleDebug
Pop-Location

Write-Host "== 完成。APK：$Root\apps\mobile\android\app\build\outputs\apk\debug\app-debug.apk"
