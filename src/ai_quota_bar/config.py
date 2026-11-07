import json
import os
from typing import Dict, Any, List

CONFIG_DIR = os.path.expanduser("~/.config/ai-quota-bar")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
CACHE_DIR = os.path.expanduser("~/.cache/ai-quota-bar")
CACHE_FILE = os.path.join(CACHE_DIR, "status.json")

DEFAULT_CONFIG: Dict[str, Any] = {
    "update_interval_seconds": 120,
    "topbar_format": "standard",  # "standard" (C: 5h 100% W 1% | ...) or "compact" (C 100%·1% | ...)
    "show_resets_in_menu": True,
    "enabled_providers": ["claude", "antigravity", "codex", "copilot"],
    "colors_enabled": True
}

def load_config() -> Dict[str, Any]:
    if not os.path.exists(CONFIG_FILE):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_CONFIG, f, indent=2)
        except Exception:
            pass
        return DEFAULT_CONFIG.copy()

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            user_cfg = json.load(f)
            cfg = DEFAULT_CONFIG.copy()
            cfg.update(user_cfg)
            return cfg
    except Exception:
        return DEFAULT_CONFIG.copy()
