import json
import os
import shutil
import subprocess
from ai_quota_bar.providers.base import BaseProvider
from ai_quota_bar.models import ProviderUsage, LimitWindow, SubModelQuota

class AntigravityProvider(BaseProvider):
    @property
    def provider_id(self) -> str:
        return "antigravity"

    @property
    def display_name(self) -> str:
        return "Google Antigravity"

    @property
    def short_tag(self) -> str:
        return "AG"

    @property
    def icon(self) -> str:
        return "🔵"

    def _get_bin(self) -> str:
        local_bin = os.path.expanduser("~/.local/bin/agy")
        if os.path.exists(local_bin):
            return local_bin
        found = shutil.which("agy")
        return found or "agy"

    def is_available(self) -> bool:
        bin_path = self._get_bin()
        return os.path.exists(bin_path) or bool(shutil.which(bin_path))

    def fetch_usage(self) -> ProviderUsage:
        bin_path = self._get_bin()
        try:
            proc = subprocess.run(
                [bin_path, "--output-format", "json", "--print", "/usage"],
                capture_output=True,
                text=True,
                timeout=8
            )
            if proc.returncode != 0:
                return ProviderUsage(
                    provider_id=self.provider_id,
                    display_name=self.display_name,
                    icon=self.icon,
                    is_available=True,
                    ok=False,
                    error=proc.stderr.strip() or f"exit code {proc.returncode}"
                )

            res = json.loads(proc.stdout)
            cmd_data = res.get("command", {}).get("data", {})
            groups = cmd_data.get("groups", [])

            windows = []
            sub_groups = []

            for g in groups:
                g_name = g.get("name", "")
                buckets = g.get("buckets", [])
                group_windows = []

                for b in buckets:
                    w_type = b.get("window", "custom")
                    rem = b.get("remaining_fraction", 1.0)
                    rem_pct = max(0, min(100, round(rem * 100)))
                    reset_t = b.get("reset_time")
                    b_name = b.get("name", w_type)

                    lw = LimitWindow(
                        name=b_name,
                        remaining_pct=rem_pct,
                        resets_at=reset_t,
                        window_type=w_type
                    )
                    group_windows.append(lw)

                    if g_name == "Gemini Models":
                        windows.append(lw)

                if group_windows:
                    sub_groups.append(SubModelQuota(
                        group_name=g_name,
                        windows=group_windows
                    ))

            return ProviderUsage(
                provider_id=self.provider_id,
                display_name=self.display_name,
                icon=self.icon,
                is_available=True,
                ok=True,
                windows=windows,
                sub_groups=sub_groups
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
