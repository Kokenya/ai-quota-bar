import json
import os
import urllib.request
import urllib.error
from ai_quota_bar.providers.base import BaseProvider
from ai_quota_bar.models import ProviderUsage, LimitWindow

class ClaudeProvider(BaseProvider):
    @property
    def provider_id(self) -> str:
        return "claude"

    @property
    def display_name(self) -> str:
        return "Claude Code (Anthropic)"

    @property
    def short_tag(self) -> str:
        return "C"

    @property
    def icon(self) -> str:
        return "🟣"

    def _get_paths(self):
        return {
            "creds": os.path.expanduser("~/.claude/.credentials.json"),
            "config": os.path.expanduser("~/.claude.json")
        }

    def is_available(self) -> bool:
        paths = self._get_paths()
        return os.path.exists(paths["creds"]) or os.path.exists(paths["config"])

    def fetch_usage(self) -> ProviderUsage:
        paths = self._get_paths()
        token = None
        if os.path.exists(paths["creds"]):
            try:
                with open(paths["creds"], "r", encoding="utf-8") as f:
                    creds = json.load(f)
                    token = creds.get("claudeAiOauth", {}).get("accessToken")
            except Exception:
                pass

        usage_json = None
        if token:
            try:
                req = urllib.request.Request(
                    "https://api.anthropic.com/api/oauth/usage",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "User-Agent": "Claude-Code/2.1.319",
                        "Accept": "application/json"
                    }
                )
                with urllib.request.urlopen(req, timeout=6) as resp:
                    if resp.status == 200:
                        usage_json = json.loads(resp.read().decode("utf-8"))
            except Exception:
                pass

        if not usage_json and os.path.exists(paths["config"]):
            try:
                with open(paths["config"], "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    cached = cfg.get("cachedUsageUtilization", {})
                    usage_json = cached.get("utilization")
            except Exception as e:
                return ProviderUsage(
                    provider_id=self.provider_id,
                    display_name=self.display_name,
                    icon=self.icon,
                    is_available=True,
                    ok=False,
                    error=str(e)
                )

        if not usage_json:
            return ProviderUsage(
                provider_id=self.provider_id,
                display_name=self.display_name,
                icon=self.icon,
                is_available=True,
                ok=False,
                error="Could not retrieve Claude usage."
            )

        windows = []

        # 5-Hour Limit
        fh = usage_json.get("five_hour")
        if fh:
            util = fh.get("utilization", 0)
            windows.append(LimitWindow(
                name="5-Hour Limit",
                remaining_pct=max(0, round(100 - util)),
                resets_at=fh.get("resets_at"),
                window_type="5h"
            ))
        else:
            windows.append(LimitWindow(
                name="5-Hour Limit",
                remaining_pct=100,
                resets_at=None,
                window_type="5h"
            ))

        # Weekly Limit
        sd = usage_json.get("seven_day")
        if sd:
            util = sd.get("utilization", 0)
            windows.append(LimitWindow(
                name="Weekly Limit",
                remaining_pct=max(0, round(100 - util)),
                resets_at=sd.get("resets_at"),
                window_type="weekly"
            ))
        else:
            limits = usage_json.get("limits", [])
            found_weekly = False
            for lim in limits:
                if lim.get("kind") == "weekly_all":
                    pct = lim.get("percent", 0)
                    windows.append(LimitWindow(
                        name="Weekly Limit",
                        remaining_pct=max(0, round(100 - pct)),
                        resets_at=lim.get("resets_at"),
                        window_type="weekly"
                    ))
                    found_weekly = True
                    break
            if not found_weekly:
                windows.append(LimitWindow(
                    name="Weekly Limit",
                    remaining_pct=100,
                    resets_at=None,
                    window_type="weekly"
                ))

        return ProviderUsage(
            provider_id=self.provider_id,
            display_name=self.display_name,
            icon=self.icon,
            is_available=True,
            ok=True,
            windows=windows
        )
