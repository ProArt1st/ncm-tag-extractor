#!/usr/bin/env python3
from __future__ import annotations

import sys
import webbrowser
from pathlib import Path
import uvicorn


def main() -> None:
    host = "127.0.0.1"
    port = 8000
    print(f"==================================================")
    print(f" 🎵 NCM Tag Extractor Web Server Started")
    print(f" 🌐 Access UI in Browser: http://{host}:{port}")
    print(f"==================================================")

    # Automatically open browser window
    try:
        webbrowser.open(f"http://{host}:{port}")
    except Exception:
        pass

    uvicorn.run("server.main:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
