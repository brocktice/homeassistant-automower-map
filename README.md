# Automower Yard

Home Assistant custom integration for Husqvarna Automower Connect with live
position updates, yard-zone awareness, and a visual zone editor.

## What it exposes

- `device_tracker`: mower GPS position for the Home Assistant map.
- `binary_sensor`: stuck/problem state based on mower state, activity, or error code.
- `binary_sensor`: one `In <zone>` entity per configured yard zone for automations.
- `sensor`: mower status.
- `sensor`: named yard zone, derived from configured circle or polygon zones.
- `sensor`: battery percentage, charging time, cutting height, and mower statistics.
- `camera`: read-only satellite yard map with zone overlays and mower marker.
- `camera`: square mower-centered yard map detail view for notifications.
- `camera`: aging satellite heatmap that fades old stuck/ok mower samples.
- Home Assistant sidebar panel: visual zone editor with satellite imagery.

The integration fetches the initial mower state from the Automower Connect REST
API, then keeps a Husqvarna WebSocket open for timely status and position
events.

When a mower is inside multiple zones, the `yard_zones` attribute lists matches
from smallest zone to largest zone. The displayed yard-zone state joins them in
that order.

The heatmap stores throttled mower position samples in Home Assistant storage.
Recent stuck/problem samples render red, normal samples render green, and both
fade out over time so fixed trouble spots cool down automatically.

## Husqvarna setup

Create an application in the Husqvarna Developer Portal and connect it to:

- Authentication API
- Automower Connect API

Use that application's key and secret when adding the integration in Home
Assistant.

## Install

### HACS custom repository

1. In HACS, open **Integrations**.
2. Use the three-dot menu and choose **Custom repositories**.
3. Add this repository URL as category **Integration**.
4. Install **Automower Yard**.
5. Restart Home Assistant.
6. Add the integration from **Settings > Devices & services**.

### Manual install

Copy `custom_components/automower_yard` to your Home Assistant
`custom_components` directory, restart Home Assistant, then add
**Automower Yard** from Devices & services.

## Yard Zones

After setup, open the **Automower Yard** sidebar panel to draw zones on a
satellite map and save them directly to Home Assistant.

Zones are saved as JSON in the integration options. Example:

```json
[
  {
    "name": "Front slope",
    "center": [44.000001, -93.000001],
    "radius_m": 8
  },
  {
    "name": "Back yard",
    "polygon": [
      [44.000010, -93.000010],
      [44.000010, -93.000090],
      [44.000080, -93.000090],
      [44.000080, -93.000010]
    ]
  }
]
```

Coordinates are `[latitude, longitude]`.

## Problem Notification Blueprint

This repo includes a Home Assistant blueprint at:

```text
blueprints/automation/automower_yard/mower_problem_notification.yaml
```

It triggers when the mower stuck/problem binary sensor turns on, snapshots a map
camera, and sends a notification with mower state, activity, yard-zone text, and
the map image. Use `Yard Map Detail` for a square mower-centered notification
image, or `Yard Map` for the full yard.

Inputs:

- Problem sensor, e.g. `binary_sensor.mr_snippers_stuck`
- Status sensor, e.g. `sensor.mr_snippers_status`
- Yard zone sensor, e.g. `sensor.mr_snippers_yard_zone`
- Notification map camera, e.g. `camera.mr_snippers_yard_map_detail`
- Mobile App notification devices or notify services, e.g. `notify.mobile_app_your_phone`

If HACS does not install the blueprint automatically, copy the blueprint file to:

```text
/config/blueprints/automation/automower_yard/mower_problem_notification.yaml
```

## Development

### Standalone zone editor

The integration includes the editor as a Home Assistant sidebar panel. For local
development, the same editor can be served outside Home Assistant:

```bash
python3 -m http.server 8090 --bind 0.0.0.0 --directory tools
```

Then open `http://<vm-ip>:8090/zone_editor.html`. You can optionally seed the
map center from a mower coordinate:

```text
http://<vm-ip>:8090/zone_editor.html?lat=44.000001&lon=-93.000001
```

If you are using the disposable HA container from this README, generate a local
latest-location file so the editor opens centered on the mower:

```bash
python3 scripts/update_zone_editor_location.py
```

### Smoke test credentials

Before loading the integration in Home Assistant, you can verify that your
Husqvarna app credentials return mower location data:

```bash
APPLICATION_KEY="..." APPLICATION_SECRET="..." \
  python3 scripts/smoke_test_husqvarna.py
```

This uses only Python's standard library and prints each mower's status,
position capability, and latest GPS coordinate if Husqvarna returns one.

### Local Home Assistant test

Run a disposable Home Assistant Core container with this integration mounted:

```bash
docker rm -f automower-yard-ha-test >/dev/null 2>&1 || true
rm -rf /tmp/automower-yard-ha-test
mkdir -p /tmp/automower-yard-ha-test
docker run -d --name automower-yard-ha-test \
  -p 8123:8123 \
  -v /tmp/automower-yard-ha-test:/config \
  -v "$PWD/custom_components:/config/custom_components:ro" \
  ghcr.io/home-assistant/home-assistant:stable
```

Then open <http://localhost:8123>. Stop it with:

```bash
docker rm -f automower-yard-ha-test
```
