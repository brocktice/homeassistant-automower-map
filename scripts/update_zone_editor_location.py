#!/usr/bin/env python3
"""Write latest Automower GPS location for the zone editor.

By default this reads the disposable HA test config entry from:
  /tmp/automower-yard-ha-test/.storage/core.config_entries

It writes:
  tools/mower_location.json
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
from urllib import parse, request
from urllib.error import HTTPError, URLError

AUTH_URL = "https://api.authentication.husqvarnagroup.dev/v1/oauth2/token"
MOWERS_URL = "https://api.amc.husqvarna.dev/v1/mowers"
DEFAULT_CONFIG_ENTRIES = Path("/tmp/automower-yard-ha-test/.storage/core.config_entries")
DEFAULT_OUTPUT = Path("tools/mower_location.json")


def main() -> int:
    config_entries = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_CONFIG_ENTRIES
    output = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_OUTPUT

    try:
        app_key, app_secret = read_credentials(config_entries)
        token = get_token(app_key, app_secret)
        location = get_latest_location(app_key, token)
    except RuntimeError as err:
        print(err, file=sys.stderr)
        return 1

    output.write_text(json.dumps(location, indent=2) + "\n", encoding="utf-8")
    print(
        f"Wrote {output}: {location['name']} "
        f"{location['latitude']}, {location['longitude']}"
    )
    return 0


def read_credentials(path: Path) -> tuple[str, str]:
    if not path.exists():
        raise RuntimeError(f"Config entries file not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    for entry in data.get("data", {}).get("entries", []):
        if entry.get("domain") == "automower_yard":
            entry_data = entry.get("data") or {}
            return str(entry_data["app_key"]), str(entry_data["app_secret"])
    raise RuntimeError("No automower_yard config entry found.")


def get_token(app_key: str, app_secret: str) -> str:
    body = parse.urlencode(
        {
            "grant_type": "client_credentials",
            "client_id": app_key,
            "client_secret": app_secret,
        }
    ).encode()
    payload = open_json(
        request.Request(
            AUTH_URL,
            data=body,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    )
    token = payload.get("access_token")
    if not token:
        raise RuntimeError("Authentication response did not include access_token.")
    return str(token)


def get_latest_location(app_key: str, token: str) -> dict:
    payload = open_json(
        request.Request(
            MOWERS_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "Authorization-Provider": "husqvarna",
                "X-Api-Key": app_key,
                "Accept": "application/vnd.api+json",
            },
        )
    )
    for mower in payload.get("data", []):
        attrs = mower.get("attributes") or {}
        positions = attrs.get("positions") or []
        if not positions:
            continue
        latest = positions[0]
        if latest.get("latitude") is None or latest.get("longitude") is None:
            continue
        system = attrs.get("system") or {}
        return {
            "name": system.get("name") or mower.get("id") or "Automower",
            "mower_id": mower.get("id"),
            "latitude": float(latest["latitude"]),
            "longitude": float(latest["longitude"]),
        }
    raise RuntimeError("No mower with a latest GPS position was returned.")


def open_json(req: request.Request) -> dict:
    try:
        with request.urlopen(req, timeout=30) as response:
            text = response.read().decode()
    except HTTPError as err:
        detail = err.read().decode(errors="replace")
        raise RuntimeError(f"HTTP {err.code} from {req.full_url}: {detail}") from err
    except URLError as err:
        raise RuntimeError(f"Network error calling {req.full_url}: {err}") from err

    try:
        return json.loads(text)
    except json.JSONDecodeError as err:
        raise RuntimeError(f"Expected JSON from {req.full_url}, got: {text[:200]}") from err


if __name__ == "__main__":
    raise SystemExit(main())
