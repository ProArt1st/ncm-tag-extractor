#!/usr/bin/env python3
from __future__ import annotations

import argparse
import socket
import sys
import webbrowser
import uvicorn


def is_port_available(host: str, port: int) -> bool:
    """Check if a port is available for binding."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
            return True
        except OSError:
            return False


def find_available_port(host: str, start_port: int, max_attempts: int = 100) -> int:
    """Find an available port starting from start_port."""
    for p in range(start_port, start_port + max_attempts):
        if is_port_available(host, p):
            return p
    return start_port


def main() -> None:
    parser = argparse.ArgumentParser(description="NCM Tag Extractor Web Server Launcher")
    parser.add_argument("-p", "--port", type=int, default=None, help="Port to run the server on (default: 8000)")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host to bind (default: 127.0.0.1)")
    parser.add_argument("--no-browser", action="store_true", help="Do not open browser automatically")
    args = parser.parse_args()

    host = args.host
    target_port = args.port or 8000
    port = find_available_port(host, target_port)

    if port != target_port:
        print(f"⚠️ [端口检测] 目标端口 {target_port} 已被占用，已自动无感切换至可用端口 {port}")

    url = f"http://{host}:{port}"
    print("==================================================")
    print(" 🎵 NCM Tag Extractor Web Server Started")
    print(f" 🌐 Access UI in Browser: {url}")
    print("==================================================")

    if not args.no_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    uvicorn.run("server.main:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
