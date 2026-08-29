#!/usr/bin/env python3
"""Run real connectivity and one-shot chat checks for the Volcengine model.

The API key is intentionally read only from VOLCENGINE_API_KEY. The script
never prints request headers, credentials, or the full response payload.
"""

import argparse
import json
import os
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
DEFAULT_MODEL_ID = "deepseek-v4-flash-ga-260731"


def _request(url, api_key, payload=None, timeout=30):
    body = None
    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(url, data=body, headers=headers, method="POST" if body else "GET")
    started = time.perf_counter()
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read()
            return {
                "ok": 200 <= response.status < 300,
                "status": response.status,
                "duration_ms": round((time.perf_counter() - started) * 1000),
                "payload": json.loads(raw.decode("utf-8")) if raw else {},
            }
    except HTTPError as error:
        # Read only a bounded diagnostic body; never include request headers.
        raw = error.read(512).decode("utf-8", errors="replace")
        return {
            "ok": False,
            "status": error.code,
            "duration_ms": round((time.perf_counter() - started) * 1000),
            "error": raw[:240],
        }
    except (URLError, TimeoutError, OSError) as error:
        return {
            "ok": False,
            "status": 0,
            "duration_ms": round((time.perf_counter() - started) * 1000),
            "error": str(getattr(error, "reason", error))[:240],
        }


def _answer_text(payload):
    choices = payload.get("choices") if isinstance(payload, dict) else None
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return ""
    message = choices[0].get("message")
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    return content.strip() if isinstance(content, str) else ""


def main():
    parser = argparse.ArgumentParser(description="Real DeepSeek-V4-Flash Ark connectivity test")
    parser.add_argument("--base-url", default=os.environ.get("VOLCENGINE_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--model", default=os.environ.get("VOLCENGINE_MODEL_ID", DEFAULT_MODEL_ID))
    parser.add_argument("--timeout", type=int, default=int(os.environ.get("VOLCENGINE_TEST_TIMEOUT", "30")))
    args = parser.parse_args()
    api_key = str(os.environ.get("VOLCENGINE_API_KEY") or "").strip()
    if not api_key:
        print(json.dumps({"ok": False, "stage": "configuration", "error": "VOLCENGINE_API_KEY_missing"}, ensure_ascii=False))
        return 2

    base_url = args.base_url.rstrip("/")
    connectivity = _request(f"{base_url}/models", api_key, timeout=max(5, args.timeout))
    result = {
        "base_url": base_url,
        "model": args.model,
        "connectivity": {
            "ok": connectivity.get("ok"),
            "status": connectivity.get("status"),
            "duration_ms": connectivity.get("duration_ms"),
            "error": connectivity.get("error", ""),
        },
    }

    # This is the only billable/model-generation request in the test.
    chat = _request(
        f"{base_url}/chat/completions",
        api_key,
        payload={
            "model": args.model,
            "messages": [{"role": "user", "content": "hi there"}],
            "stream": False,
            "max_tokens": 64,
        },
        timeout=max(5, args.timeout),
    )
    answer = _answer_text(chat.get("payload"))
    result["hi_there"] = {
        "ok": bool(chat.get("ok") and answer),
        "status": chat.get("status"),
        "duration_ms": chat.get("duration_ms"),
        "answer_preview": answer[:240],
        "error": chat.get("error", "") if not answer else "",
    }
    result["ok"] = bool(result["connectivity"]["ok"] and result["hi_there"]["ok"])
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
