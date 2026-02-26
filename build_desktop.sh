#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -f "venv/bin/activate" ]; then
  echo "未找到虚拟环境，请先执行："
  echo "python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
  exit 1
fi

source venv/bin/activate

python3 scripts/prepare_vendor_assets.py

pyinstaller --noconfirm --clean build.spec

echo "打包完成：dist/office-supplies-desktop/"
