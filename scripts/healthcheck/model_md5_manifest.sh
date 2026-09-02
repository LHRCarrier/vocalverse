#!/usr/bin/env bash
# ============================================================
# 模型文件清单及 MD5 列表生成脚本
# 对应审计项: ASR-M01 / TTS-M01 / ISE-M01（模型文件完整性）
#
# 用法:
#   ./model_md5_manifest.sh [模型目录] [输出文件]
#   默认: 模型目录 = /data/models，输出 = model_manifest_<时间戳>.txt
#
# 说明:
#   - 递归扫描 .pt / .onnx / .pth 三类模型文件
#   - 输出格式: <MD5 哈希>  <文件路径>（md5sum 原生格式，可直接与发布 manifest 比对）
#   - Windows 审计机无 md5sum 时，PowerShell 等价写法:
#       Get-ChildItem -Recurse -Include *.pt,*.onnx,*.pth | Get-FileHash -Algorithm MD5
# ============================================================

set -euo pipefail

MODEL_DIR="${1:-/data/models}"
OUT="${2:-model_manifest_$(date +%Y%m%d_%H%M%S).txt}"

if [ ! -d "$MODEL_DIR" ]; then
    echo "错误: 模型目录不存在: $MODEL_DIR" >&2
    exit 1
fi

echo "扫描目录: $MODEL_DIR"

# find + md5sum 组合: 递归查找模型文件并计算 MD5，按路径排序后写入清单
find "$MODEL_DIR" -type f \( -name "*.pt" -o -name "*.onnx" -o -name "*.pth" \) \
    -exec md5sum {} \; | sort -k2 > "$OUT"

count=$(wc -l < "$OUT")
echo "模型文件数: $count"
echo "清单已写入: $OUT"

# 一句话命令组合（可直接粘贴执行）:
# find /data/models -type f \( -name "*.pt" -o -name "*.onnx" -o -name "*.pth" \) -exec md5sum {} \; | sort -k2 > model_manifest.txt
