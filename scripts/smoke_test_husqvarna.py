#!/usr/bin/env python3
"""Smoke test Husqvarna Automower credentials and mower GPS data.

Set:
  APPLICATION_KEY=...
  APPLICATION_SECRET=...

Then run:
  python3 scripts/smoke_test_husqvarna.py
"""

from __future__ import annotations

import json
import os
import sys
from urllib import parse, request
from urllib.error import HTTPError, URLError

AUTH_URL = "https://api.authentication.husqvarnagroup.dev/v1/oauth2/token"
MOWERS_URL = "https://api.amc.husqvarna.dev/v1/mowers"


def main() -> int:
    app_key = os.environ.get("APPLICATION_KEY")
    app_secret = os.environ.get("APPLICATION_SECRET")
    if not app_key or not app_secret:
        print("Missing APPLICATION_KEY or APPLICATION_SECRET.", file=sys.stderr)
        return 2

    try:
        token = get_token(app_key, app_secret)
        mowers = get_mowers(app_key, token)
    except RuntimeError as err:
        print(err, file=sys.stderr)
        return 1

    if not mowers:
        print("Authenticated, but no paired mowers were returned.")
        return 0

    for mower in mowers:
        mower_id = mower.get("id", "unknown")
        attrs = mower.get("attributes") or {}
        system = attrs.get("system") or {}
        capabilities = attrs.get("capabilities") or {}
        mower_state = attrs.get("mower") or {}
        positions = attrs.get("positions") or []
        latest = positions[0] if positions else {}

        print(f"Mower: {system.get('name') or mower_id}")
        print(f"  id: {mower_id}")
        print(f"  model: {system.get('model')}")
        print(f"  state: {mower_state.get('state')}")
        print(f"  activity: {mower_state.get('activity')}")
        print(f"  supports_position: {capabilities.get('position')}")
        if latest:
            print(f"  latest_position: {latest.get('latitude')}, {latest.get('longitude')}")
            print(f"  position_history_count: {len(positions)}")
        else:
            print("  latest_position: none returned")
    return 0


def get_token(app_key: str, app_secret: str) -> str:
    body = parse.urlencode(
        {
            "grant_type": "client_credentials",
            "client_id": app_key,
            "client_secret": app_secret,
        }
    ).encode()
    payload = post_form(AUTH_URL, body)
    token = payload.get("access_token")
    if not token:
        raise RuntimeError(f"Authentication response did not include access_token: {payload}")
    return str(token)


def get_mowers(app_key: str, token: str) -> list[dict]:
    req = request.Request(
        MOWERS_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "Authorization-Provider": "husqvarna",
            "X-Api-Key": app_key,
            "Accept": "application/vnd.api+json",
        },
    )
    payload = open_json(req)
    data = payload.get("data")
    if not isinstance(data, list):
        raise RuntimeError(f"Mower response did not include data list: {payload}")
    return data


def post_form(url: str, body: bytes) -> dict:
    req = request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    return open_json(req)


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
