#!/bin/bash
# 办公用品采购追踪系统启动脚本

cd "$(dirname "$0")"

echo "正在启动办公用品采购追踪系统..."
echo "系统地址: http://localhost:8000"
echo "按 Ctrl+C 停止服务"
echo ""

source venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
