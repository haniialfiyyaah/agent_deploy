from __future__ import annotations

import argparse
import time

import httpx


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one live smoke test against a deployed Northstar service")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--timeout", type=int, default=150)
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    with httpx.Client(timeout=30.0) as client:
        ready = client.get(f"{base}/health/ready")
        ready.raise_for_status()
        accepted = client.post(
            f"{base}/v1/runs",
            json={
                "message": "How long does standard delivery normally take? Search policy first.",
                "category": "delivery",
                "expected_document_ids": ["KB-DEL-001"],
            },
        )
        accepted.raise_for_status()
        status_url = f"{base}{accepted.json()['status_url']}"
        deadline = time.monotonic() + args.timeout
        while time.monotonic() < deadline:
            snapshot = client.get(status_url).json()
            if snapshot["status"] in {"completed", "failed", "cancelled"}:
                print(snapshot)
                if snapshot["status"] != "completed":
                    raise SystemExit(1)
                return
            time.sleep(1)
    raise TimeoutError("Agent run did not complete before the smoke-test deadline")


if __name__ == "__main__":
    main()
