from abc import ABC, abstractmethod
from ai_quota_bar.models import ProviderUsage

class BaseProvider(ABC):
    @property
    @abstractmethod
    def provider_id(self) -> str:
        """Unique ID, e.g. 'claude'"""
        pass

    @property
    @abstractmethod
    def display_name(self) -> str:
        """User-friendly name, e.g. 'Claude Code'"""
        pass

    @property
    @abstractmethod
    def short_tag(self) -> str:
        """Top bar short tag, e.g. 'C' or 'AG'"""
        pass

    @property
    @abstractmethod
    def icon(self) -> str:
        """Emoji icon, e.g. '🟣'"""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if provider CLI / credentials exist."""
        pass

    @abstractmethod
    def fetch_usage(self) -> ProviderUsage:
        """Fetch real-time usage and limits."""
        pass
