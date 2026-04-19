from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.request


BACKEND_URL = os.environ.get("AIDER_BACKEND_URL", "http://backend:8000")
INTERNAL_TOKEN = os.environ.get("INTERNAL_AGENT_TOKEN", "change-internal-agent-token")
DEFAULT_MODEL = os.environ.get("AIDER_MODEL", "openai/gpt-4o-mini")
EDITOR_MODEL = os.environ.get("AIDER_EDITOR_MODEL", "openai/gpt-4o-mini")


def request(method: str, path: str, payload: dict | None = None) -> dict:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{BACKEND_URL}{path}",
        data=data,
        method=method,
        headers={
            "Content-Type": "application/json",
            "X-Internal-Agent-Token": INTERNAL_TOKEN,
        },
    )
    with urllib.request.urlopen(req, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def run_aider_task(task: dict) -> tuple[str, str, dict]:
    model = task.get("preferred_model") or DEFAULT_MODEL
    files = task.get("files_in_scope") or []
    command = [
        "aider",
        "--yes",
        "--no-auto-commits",
        "--model",
        model,
        "--editor-model",
        EDITOR_MODEL,
        "--message",
        task["instruction"],
    ]
    command.extend(files)
    result = subprocess.run(command, cwd="/workspace", capture_output=True, text=True)
    output_payload = {
        "returncode": result.returncode,
        "stdout": result.stdout[-12000:],
        "stderr": result.stderr[-12000:],
        "model": model,
        "files": files,
    }
    if result.returncode == 0:
        summary = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else "Aider task completed."
        return "completed", summary, output_payload
    summary = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "Aider task failed."
    return "failed", summary, output_payload


def main() -> None:
    while True:
        try:
            claim = request("POST", "/api/internal/aider/next")
            details = claim.get("details", {})
            task_id = details.get("task_id")
            if not task_id:
                time.sleep(10)
                continue

            status, summary, output_payload = run_aider_task(details)
            request(
                "POST",
                f"/api/internal/aider/{task_id}",
                {
                    "status": status,
                    "output_summary": summary,
                    "output_payload": output_payload,
                    "error_message": output_payload.get("stderr") if status == "failed" else None,
                },
            )
        except urllib.error.HTTPError as exc:
            print(f"aider worker http error: {exc.code}")
            time.sleep(10)
        except Exception as exc:
            print(f"aider worker error: {exc}")
            time.sleep(10)


if __name__ == "__main__":
    main()
