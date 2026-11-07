import json
import os
import shutil
import subprocess
from ai_quota_bar.providers.base import BaseProvider
from ai_quota_bar.models import ProviderUsage, LimitWindow

class CopilotProvider(BaseProvider):
    @property
    def provider_id(self) -> str:
        return "copilot"

    @property
    def display_name(self) -> str:
        return "GitHub Copilot"

    @property
    def short_tag(self) -> str:
        return "GH"

    @property
    def icon(self) -> str:
        return "🐙"

    def is_available(self) -> bool:
        if shutil.which("copilot") or shutil.which("gh"):
            return True
        config_path = os.path.expanduser("~/.config/github-copilot")
        return os.path.exists(config_path)

    def fetch_usage(self) -> ProviderUsage:
        gh_bin = shutil.which("gh")
        if not gh_bin:
            return ProviderUsage(
                provider_id=self.provider_id,
                display_name=self.display_name,
                icon=self.icon,
                is_available=True,
                ok=False,
                error="gh CLI not found."
            )

        try:
            # Query Copilot or GitHub user rate limit status
            proc = subprocess.run(
                [gh_bin, "api", "rate_limit"],
                capture_output=True,
                text=True,
                timeout=6
            )
            if proc.returncode == 0:
                data = json.loads(proc.stdout)
                core = data.get("resources", {}).get("core", {})
                rem = core.get("remaining", 0)
                limit = core.get("limit", 1)
                rem_pct = round((rem / max(limit, 1)) * 100)
                reset_t = core.get("reset")

                windows = [
                    LimitWindow(
                        name="API Hourly Limit",
                        remaining_pct=rem_pct,
                        resets_at=None,
                        window_type="hourly"
                    )
                ]

                return ProviderUsage(
                    provider_id=self.provider_id,
                    display_name=self.display_name,
                    icon=self.icon,
                    is_available=True,
                    ok=True,
                    windows=windows
                )
            else:
                return ProviderUsage(
                    provider_id=self.provider_id,
                    display_name=self.display_name,
                    icon=self.icon,
                    is_available=True,
                    ok=False,
                    error="Not logged in to GitHub Copilot / CLI."
                )
        except Exception as e:
            return ProviderUsage(
                provider_id=self.provider_id,
                display_name=self.display_name,
                icon=self.icon,
                is_available=True,
                ok=False,
                error=str(e)
            )
