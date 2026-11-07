from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

@dataclass
class LimitWindow:
    name: str                   # e.g. "5-Hour Limit", "Weekly Limit"
    remaining_pct: Optional[int] # e.g. 98, or None if unknown
    resets_at: Optional[str]     # ISO timestamp or description
    window_type: str = "custom"  # "5h", "weekly", "monthly", "custom"

@dataclass
class SubModelQuota:
    group_name: str
    windows: List[LimitWindow] = field(default_factory=list)

@dataclass
class ProviderUsage:
    provider_id: str             # "claude", "antigravity", "codex", "copilot"
    display_name: str            # "Claude Code", "Google Antigravity", etc.
    icon: str                    # "🟣", "🔵", "🟢", "🐙"
    is_available: bool           # Whether the tool is installed / authenticated
    ok: bool                     # Whether fetch succeeded
    windows: List[LimitWindow] = field(default_factory=list)
    sub_groups: List[SubModelQuota] = field(default_factory=list)
    plan_name: Optional[str] = None
    error: Optional[str] = None

    def get_5h_window(self) -> Optional[LimitWindow]:
        for w in self.windows:
            if w.window_type == "5h" or "5h" in w.name.lower() or "5-hour" in w.name.lower():
                return w
        return None

    def get_weekly_window(self) -> Optional[LimitWindow]:
        for w in self.windows:
            if w.window_type == "weekly" or "week" in w.name.lower():
                return w
        return None

@dataclass
class QuotaReport:
    timestamp: str
    providers: Dict[str, ProviderUsage] = field(default_factory=dict)
