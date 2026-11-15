"""MIT hermes-talk wire subset; see TALK-LICENSE and PROVENANCE.md."""
CLIENT_SECRETS_URL = "https://api.openai.com/v1/realtime/client_secrets"
OPENAI_REALTIME_WS_URL = "wss://api.openai.com/v1/realtime"
class TalkUpstreamError(ValueError):
    pass

def parse_client_secret(payload: dict) -> tuple[str, int | None]:
    """Accept both flat ``{value, expires_at}`` and nested client_secret shapes."""

    value = payload.get("value")
    nested = payload.get("client_secret")
    if not isinstance(value, str) or not value:
        value = nested.get("value") if isinstance(nested, dict) else None
    if not isinstance(value, str) or not value:
        raise TalkUpstreamError("OpenAI Realtime client secret response did not include a value")
    expires_at = payload.get("expires_at")
    if not isinstance(expires_at, (int, float)) and isinstance(nested, dict):
        expires_at = nested.get("expires_at")
    expires_at_ms = int(expires_at * 1000) if isinstance(expires_at, (int, float)) else None
    return value, expires_at_ms
