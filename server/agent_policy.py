"""Operator-controlled access to the paid Yandex key on public instances."""
import os
from uuid import UUID


def provider_allowed(tenant_id, *, production=None):
    if production is None:
        production = os.getenv("APP_ENV", "development").lower() == "production"
    binding = os.getenv("YANDEX_AGENT_TENANT_IDS", "").strip()
    if not binding:
        return not production
    try:
        entries = [value.strip() for value in binding.split(",")]
        if any(not value for value in entries):
            return False
        allowed = {str(UUID(value)) for value in entries}
        return str(UUID(tenant_id)) in allowed
    except (ValueError, TypeError, AttributeError):
        return False


def provider_configured():
    model = os.getenv("YANDEX_AGENT_MODEL") or os.getenv("YANDEX_MODEL", "")
    return bool(os.getenv("YANDEX_API_KEY") and model.startswith("gpt://"))
