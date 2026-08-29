#!/usr/bin/env python3
"""Register DeepSeek-V4-Flash in the Admin LLM registry.

The API key must be supplied through VOLCENGINE_API_KEY. It is passed to the
existing encrypted PostgreSQL credential path and is never printed or stored
in the source tree.
"""

import copy
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.runtime import app
from src.domain.core_services import get_site_config, normalize_llm_registry_config, save_site_config


MODEL = {
    "key": "volcengine-deepseek-v4-flash",
    "label": "DeepSeek-V4-Flash正式版",
    "provider": "volcengine",
    "model_name": "deepseek-v4-flash-ga-260731",
    "base_url": "https://ark.cn-beijing.volces.com/api/v3",
    "purpose": "general",
    "enabled": True,
}


def main():
    api_key = str(os.environ.get("VOLCENGINE_API_KEY") or "").strip()
    if not api_key:
        print("VOLCENGINE_API_KEY_missing", file=sys.stderr)
        return 2

    with app.app_context():
        current = get_site_config()
        registry = normalize_llm_registry_config(current.get("llm_registry"))
        models = copy.deepcopy(registry.get("models") or [])
        matching = next((item for item in models if item.get("key") == MODEL["key"]), None)
        if matching is None:
            models.insert(0, copy.deepcopy(MODEL))
        else:
            matching.update(MODEL)
        registry["models"] = models
        registry["default_model_key"] = MODEL["key"]
        for item in registry["models"]:
            if item.get("key") == MODEL["key"]:
                item["api_key"] = api_key
                break
        next_config = copy.deepcopy(current)
        next_config["llm_registry"] = registry
        saved = save_site_config(next_config)
        saved_registry = saved.get("llm_registry") or {}
        print(
            "configured model_key=%s default_model_key=%s models=%d"
            % (
                MODEL["key"],
                saved_registry.get("default_model_key") or "",
                len(saved_registry.get("models") or []),
            )
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
