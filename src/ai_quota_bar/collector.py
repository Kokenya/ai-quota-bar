import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
from datetime import datetime, timezone
from typing import Dict, Any

from ai_quota_bar.config import load_config, CACHE_FILE
from ai_quota_bar.models import ProviderUsage, LimitWindow, SubModelQuota
from ai_quota_bar.providers import get_all_providers

def serialize_provider(p: ProviderUsage) -> Dict[str, Any]:
    return {
        "provider_id": p.provider_id,
        "display_name": p.display_name,
        "icon": p.icon,
        "is_available": p.is_available,
        "ok": p.ok,
        "plan_name": p.plan_name,
        "error": p.error,
        "windows": [
            {
                "name": w.name,
                "remaining_pct": w.remaining_pct,
                "resets_at": w.resets_at,
                "window_type": w.window_type
            } for w in p.windows
        ],
        "sub_groups": [
            {
                "group_name": sg.group_name,
                "windows": [
                    {
                        "name": w.name,
                        "remaining_pct": w.remaining_pct,
                        "resets_at": w.resets_at,
                        "window_type": w.window_type
                    } for w in sg.windows
                ]
            } for sg in p.sub_groups
        ]
    }

def deserialize_provider(d: Dict[str, Any]) -> ProviderUsage:
    windows = [
        LimitWindow(
            name=w["name"],
            remaining_pct=w.get("remaining_pct"),
            resets_at=w.get("resets_at"),
            window_type=w.get("window_type", "custom")
        ) for w in d.get("windows", [])
    ]
    sub_groups = [
        SubModelQuota(
            group_name=sg["group_name"],
            windows=[
                LimitWindow(
                    name=w["name"],
                    remaining_pct=w.get("remaining_pct"),
                    resets_at=w.get("resets_at"),
                    window_type=w.get("window_type", "custom")
                ) for w in sg.get("windows", [])
            ]
        ) for sg in d.get("sub_groups", [])
    ]
    return ProviderUsage(
        provider_id=d["provider_id"],
        display_name=d["display_name"],
        icon=d.get("icon", ""),
        is_available=d.get("is_available", True),
        ok=d.get("ok", True),
        plan_name=d.get("plan_name"),
        error=d.get("error"),
        windows=windows,
        sub_groups=sub_groups
    )

def collect_usage(force: bool = False) -> Dict[str, Any]:
    cfg = load_config()
    enabled = set(cfg.get("enabled_providers", []))

    all_provs = get_all_providers()
    target_provs = [p for p in all_provs if p.provider_id in enabled and p.is_available()]

    results: Dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "providers": {}
    }

    with ThreadPoolExecutor(max_workers=min(4, max(1, len(target_provs)))) as executor:
        future_map = {executor.submit(p.fetch_usage): p for p in target_provs}
        try:
            for future in as_completed(future_map, timeout=12):
                p = future_map[future]
                try:
                    usage = future.result(timeout=8)
                    results["providers"][p.provider_id] = serialize_provider(usage)
                except Exception as e:
                    results["providers"][p.provider_id] = serialize_provider(
                        ProviderUsage(
                            provider_id=p.provider_id,
                            display_name=p.display_name,
                            icon=p.icon,
                            is_available=True,
                            ok=False,
                            error=str(e)
                        )
                    )
        except TimeoutError:
            pass

        # Handle any futures that didn't complete
        for future, p in future_map.items():
            if p.provider_id not in results["providers"]:
                results["providers"][p.provider_id] = serialize_provider(
                    ProviderUsage(
                        provider_id=p.provider_id,
                        display_name=p.display_name,
                        icon=p.icon,
                        is_available=True,
                        ok=False,
                        error="Timeout fetching usage"
                    )
                )

    # Save to cache
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    tmp_path = CACHE_FILE + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    os.replace(tmp_path, CACHE_FILE)

    return results

def get_cached_usage() -> Dict[str, Any]:
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return collect_usage()
