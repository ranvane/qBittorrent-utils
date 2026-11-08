#!/bin/bash
# ============================================================
# qBittorrent 下载完成后清理 .!qB 残留文件脚本
# ============================================================
# 用途：
#   qBittorrent 下载过程中会给未完成的文件追加 ".!qB" 后缀，
#   正常完成后会自动去掉。但在某些异常场景（部分文件未勾选、
#   历史 bug、手动移动文件等）下可能残留 "文件名.!qB" 文件。
#   本脚本在种子下载完成后递归检查内容目录并删除这些残留文件。
#
# qBittorrent 配置：
#   设置 → 下载 → 勾选“Torrent 完成时运行外部程序”
#   命令填写：
#       /downloads/clean_qb.sh "%F"
#   参数说明：
#       %F = 种子内容路径（单文件种子为该文件路径，
#            多文件种子为根目录路径）
#   注意：
#       - 路径需用双引号括起，防止空格导致参数被拆分
#       - 若 qBittorrent 运行在 Docker 中，脚本必须放在
#         容器内可访问的路径，且 "%F" 是容器内视角的路径
#       - 脚本需有执行权限：chmod +x clean_qb.sh
# ============================================================

# 接收 qBittorrent 传入的内容路径（%F）
TARGET="$1"

# 参数为空时直接退出，避免误操作
if [ -z "$TARGET" ]; then
    echo "错误：未收到内容路径参数（%F）" >&2
    exit 1
fi

# 目标路径不存在时退出（可能已被移动或删除）
if [ ! -e "$TARGET" ]; then
    echo "提示：路径不存在，跳过：$TARGET" >&2
    exit 0
fi

# 情况一：多文件种子，%F 是目录 → 递归查找并删除 .!qB 文件
if [ -d "$TARGET" ]; then
    find "$TARGET" -type f -name "*.!qB" -print -delete 2>/dev/null
fi

# 情况二：单文件种子，%F 是文件本身 →
#   检查同目录下是否存在 "该文件名.!qB" 的残留
if [ -f "$TARGET" ]; then
    RESIDUAL="${TARGET}.!qB"
    if [ -f "$RESIDUAL" ]; then
        rm -f "$RESIDUAL"
        echo "已删除残留文件：$RESIDUAL"
    fi
fi

exit 0
