"""OAuth helpers for Robot Mower Yard providers."""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from homeassistant.helpers.config_entry_oauth2_flow import LocalOAuth2Implementation


class NavimowOAuth2Implementation(LocalOAuth2Implementation):
    """Navimow OAuth2 implementation."""

    @property
    def name(self) -> str:
        """Return implementation name."""
        return "Navimow"

    async def async_generate_authorize_url(self, *args: Any, **kwargs: Any) -> str:
        """Append channel=homeassistant without changing OAuth2 behavior."""
        url = await super().async_generate_authorize_url(*args, **kwargs)
        parsed = urlparse(url)
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        query.setdefault("channel", "homeassistant")
        return urlunparse(parsed._replace(query=urlencode(query)))
