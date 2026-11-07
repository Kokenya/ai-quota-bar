from ai_quota_bar.providers.base import BaseProvider
from ai_quota_bar.providers.claude import ClaudeProvider
from ai_quota_bar.providers.antigravity import AntigravityProvider
from ai_quota_bar.providers.codex import CodexProvider
from ai_quota_bar.providers.copilot import CopilotProvider

ALL_PROVIDERS = [
    ClaudeProvider(),
    AntigravityProvider(),
    CodexProvider(),
    CopilotProvider(),
]

def get_provider(provider_id: str):
    for p in ALL_PROVIDERS:
        if p.provider_id == provider_id:
            return p
    return None

def get_all_providers():
    return ALL_PROVIDERS
