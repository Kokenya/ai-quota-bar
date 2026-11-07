import json
import os
import shutil
import urllib.request
import urllib.error
from datetime import datetime, timezone
from ai_quota_bar.providers.base import BaseProvider
from ai_quota_bar.models import ProviderUsage, LimitWindow

class CodexProvider(BaseProvider):
    @property
    def provider_id(self) -> str:
        return "codex"

    @property
    def display_name(self) -> str:
        return "OpenAI Codex CLI"

    @property
    def short_tag(self) -> str:
        return "CX"

    @property
    def icon(self) -> str:
        return "🟢"

    def _get_auth_path(self) -> str:
        return os.path.expanduser("~/.codex/auth.json")

    def is_available(self) -> bool:
        if os.path.exists(self._get_auth_path()):
            return True
        return bool(shutil.which("codex"))

    def fetch_usage(self) -> ProviderUsage:
        auth_path = self._get_auth_path()
        if not os.path.exists(auth_path):
            return ProviderUsage(
                provider_id=self.provider_id,
                display_name=self.display_name,
                icon=self.icon,
                is_available=False,
                ok=False,
                error="~/.codex/auth.json not found."
            )

        try:
            with open(auth_path, "r", encoding="utf-8") as f:
                auth = json.load(f)
        except Exception as e:
            return ProviderUsage(
                provider_id=self.provider_id,
                display_name=self.display_name,
                icon=self.icon,
                is_available=True,
                ok=False,
                error=f"Failed to read auth.json: {e}"
            )

        tokens = auth.get("tokens", {})
        access_token = tokens.get("access_token")
        if not access_token:
            api_key = auth.get("OPENAI_API_KEY")
            if api_key:
                return ProviderUsage(
                    provider_id=self.provider_id,
                    display_name=self.display_name,
                    icon=self.icon,
                    is_available=True,
                    ok=True,
                    plan_name="API Key Mode (Pay-as-you-go)",
                    windows=[LimitWindow(name="API Quota", remaining_pct=100, resets_at=None, window_type="custom")]
                )
            return ProviderUsage(
                provider_id=self.provider_id,
                display_name=self.display_name,
                icon=self.icon,
                is_available=True,
                ok=False,
                error="No access token or API key configured."
            )

        # Call ChatGPT / Codex usage endpoint
        urls = [
            "https://chatgpt.com/backend-api/codex/usage",
            "https://chatgpt.com/backend-api/wham/usage"
        ]

        data = None
        last_error = None
        for url in urls:
            try:
                req = urllib.request.Request(
                    url,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "User-Agent": "codex-cli/0.147.0",
                        "Accept": "application/json"
                    }
                )
                with urllib.request.urlopen(req, timeout=6) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8"))
                        break
            except urllib.error.HTTPError as e:
                last_error = f"HTTP {e.code}"
                if e.code == 401:
                    last_error = "Token expired / Re-login needed"
            except Exception as e:
                last_error = str(e)

        if not data:
            return ProviderUsage(
                provider_id=self.provider_id,
                display_name=self.display_name,
                icon=self.icon,
                is_available=True,
                ok=False,
                error=last_error or "Failed to query Codex usage endpoint."
            )

        plan = data.get("plan_type", "unknown").capitalize()
        rl = data.get("rate_limit", {})
        pw = rl.get("primary_window")
        sw = rl.get("secondary_window")

        windows = []

        # Secondary window (often 5-hour or rolling session cap on Pro/Plus)
        if sw:
            used = sw.get("used_percent", 0)
            rem = max(0, 100 - used)
            reset_at = sw.get("reset_at")
            reset_iso = None
            if reset_at:
                reset_iso = datetime.fromtimestamp(reset_at, timezone.utc).isoformat()
            windows.append(LimitWindow(
                name="5-Hour Session Limit",
                remaining_pct=rem,
                resets_at=reset_iso,
                window_type="5h"
            ))

        # Primary window (weekly or monthly plan quota)
        if pw:
            used = pw.get("used_percent", 0)
            rem = max(0, 100 - used)
            reset_at = pw.get("reset_at")
            win_sec = pw.get("limit_window_seconds", 0)
            reset_iso = None
            if reset_at:
                reset_iso = datetime.fromtimestamp(reset_at, timezone.utc).isoformat()

            win_type = "weekly" if win_sec <= 7 * 86400 else "monthly"
            win_name = "Weekly Limit" if win_type == "weekly" else "Plan Quota"

            windows.append(LimitWindow(
                name=win_name,
                remaining_pct=rem,
                resets_at=reset_iso,
                window_type=win_type
            ))
        elif not windows:
            # Fallback if no specific window given
            windows.append(LimitWindow(
                name="Codex Limit",
                remaining_pct=100 if rl.get("allowed", True) else 0,
                resets_at=None,
                window_type="custom"
            ))

        return ProviderUsage(
            provider_id=self.provider_id,
            display_name=self.display_name,
            icon=self.icon,
            is_available=True,
            ok=True,
            plan_name=plan,
            windows=windows
        )
