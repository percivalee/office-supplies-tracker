#!/usr/bin/env python3
"""Download frontend vendor assets for offline desktop runtime."""

from __future__ import annotations

import argparse
import sys
import tempfile
import urllib.request
from pathlib import Path


ASSETS: dict[str, list[str]] = {
    "vue.global.prod.js": [
        "https://cdn.jsdelivr.net/npm/vue@3.5.12/dist/vue.global.prod.js",
        "https://unpkg.com/vue@3.5.12/dist/vue.global.prod.js",
    ],
    "axios.min.js": [
        "https://cdn.jsdelivr.net/npm/axios@1.7.9/dist/axios.min.js",
        "https://unpkg.com/axios@1.7.9/dist/axios.min.js",
    ],
    "tailwind.min.css": [
        "https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css",
        "https://unpkg.com/tailwindcss@2.2.19/dist/tailwind.min.css",
    ],
}


def _fetch(url: str, use_env_proxy: bool) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "office-supplies-tracker/1.0",
        },
    )
    if use_env_proxy:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read()

    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=30) as response:
        return response.read()


def _download_asset(filename: str, urls: list[str], vendor_dir: Path, force: bool) -> tuple[bool, str]:
    target = vendor_dir / filename
    if target.exists() and target.stat().st_size > 0 and not force:
        return True, f"skip {filename} (already exists)"

    attempts: list[str] = []
    for use_env_proxy in (True, False):
        mode = "env-proxy" if use_env_proxy else "no-proxy"
        for url in urls:
            try:
                content = _fetch(url, use_env_proxy=use_env_proxy)
                if not content:
                    raise RuntimeError("empty file")
                with tempfile.NamedTemporaryFile("wb", delete=False, dir=vendor_dir) as tmp_file:
                    tmp_file.write(content)
                    tmp_path = Path(tmp_file.name)
                tmp_path.replace(target)
                target.chmod(0o644)
                return True, f"ok {filename} <- {url} ({mode})"
            except Exception as exc:  # noqa: BLE001
                attempts.append(f"{url} [{mode}] -> {exc}")

    detail = "; ".join(attempts)
    return False, f"fail {filename}: {detail}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare frontend vendor assets.")
    parser.add_argument("--force", action="store_true", help="redownload even if target file exists")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    vendor_dir = project_root / "static" / "vendor"
    vendor_dir.mkdir(parents=True, exist_ok=True)

    print(f"Preparing assets in: {vendor_dir}")

    failed = False
    for filename, urls in ASSETS.items():
        ok, message = _download_asset(filename, urls, vendor_dir, force=args.force)
        print(message)
        if not ok:
            failed = True

    if failed:
        print("Vendor asset preparation failed.")
        return 1

    print("Vendor asset preparation done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
