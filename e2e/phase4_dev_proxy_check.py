"""Check that the running Vite dev server proxies Phase 4 message APIs.

This catches the common manual-acceptance failure where Vite on 5173 still
points at an old backend process on 8000 that does not include /api/messages.
"""

from __future__ import annotations

import sys

import httpx


FRONTEND_URL = "http://127.0.0.1:5173"
BACKEND_URL = "http://127.0.0.1:8000"


def main() -> int:
    with httpx.Client(timeout=5.0) as client:
        backend_openapi = client.get(f"{BACKEND_URL}/openapi.json")
        backend_openapi.raise_for_status()
        if "/api/messages/search" not in backend_openapi.text:
            print("FAIL: backend 8000 is running old code without /api/messages/search")
            return 1

        proxy = client.get(
            f"{FRONTEND_URL}/api/messages/search",
            params={"session_id": "phase4-proxy-check", "q": "probe"},
        )
        if proxy.status_code == 404:
            print("FAIL: Vite proxy on 5173 returns 404 for /api/messages/search")
            return 1
        proxy.raise_for_status()

    print("Phase 4 dev proxy check passed")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except httpx.HTTPError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
