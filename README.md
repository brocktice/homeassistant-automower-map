# Robot Mower Yard

Home Assistant custom integration for managing multiple robot mowers in one
yard. It can aggregate Husqvarna Automower, Segway Navimow, mock, and existing
Home Assistant entity providers into shared yard status, zones, maps, and
heatmaps.

This replaces the earlier Automower-only integration.

## What It Exposes

- Yard/location config entries that group one or more mower providers.
- Provider config entries for Husqvarna Automower, Navimow, existing HA
  entities, and mock data.
- `device_tracker`: mower position for the Home Assistant map.
- `lawn_mower`: mower controls where the provider supports them.
- `binary_sensor`: mower problem state and one `In <zone>` entity per configured
  yard zone.
- `sensor`: mower status, yard zone, battery, cutting height, and provider
  statistics where available.
- `camera`: yard overview, yard heatmap, and per-mower snapshot cameras.
- `switch`: provider-supported mower switches where available.
- Sidebar panel: mower status, live zone map, live signed-evidence heatmap, zone
  editor link, and Navimow base-station/calibration settings.

## Provider Notes

### Husqvarna Automower

Create an application in the Husqvarna Developer Portal and connect it to:

- Authentication API
- Automower Connect API

Use that application's key and secret when adding the Husqvarna provider.

### Segway Navimow

Add a Navimow provider and sign in through the integration flow. Navimow
positions can be calibrated in provider settings:

- Base station latitude/longitude
- North/east position offsets in meters

The offsets are applied to mower positions, the base station marker, and
displayed heatmap samples.

## Install

### HACS Custom Repository

1. In HACS, open **Integrations**.
2. Use the three-dot menu and choose **Custom repositories**.
3. Add this repository URL as category **Integration**.
4. Install **Robot Mower Yard**.
5. Restart Home Assistant.
6. Add a **Robot Mower Yard** yard/location first.
7. Add one or more provider entries and attach them to that yard.

### Manual Install

Copy `custom_components/robot_mower_yard` to your Home Assistant
`custom_components` directory, restart Home Assistant, then add
**Robot Mower Yard** from Devices & services.

## Yard Zones

Zones are edited from the yard entry's Configure screen or from the sidebar's
zone editor link. They are stored as JSON in the yard entry options.

Example:

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

Coordinates are `[latitude, longitude]`. When a mower is inside multiple zones,
the `yard_zones` attribute lists matches from smallest zone to largest zone.

## Heatmaps

The integration stores throttled mower position samples in Home Assistant
storage. The sidebar heatmap renders a signed evidence field:

- Green: normal/good samples
- Red: problem samples
- Yellow: mixed or weak evidence

The heatmap is live, zoomable, and shared across mowers in the selected yard.

## Problem Notification Blueprint

This repo includes a Home Assistant blueprint at:

```text
blueprints/automation/robot_mower_yard/mower_problem_notification.yaml
```

It selects a Robot Mower Yard mower device, infers that mower's problem/status/
yard-zone/battery/snapshot-camera entities, waits for the problem state to
persist for 60 seconds, snapshots the mower camera, and sends a notification.

Inputs:

- Mower device
- Mobile App notification devices or notify services
- Optional notification title/message/open URL

If HACS does not install the blueprint automatically, copy the blueprint file to:

```text
/config/blueprints/automation/robot_mower_yard/mower_problem_notification.yaml
```

## Local Home Assistant Test

Run a disposable Home Assistant Core container with this integration mounted:

```bash
docker rm -f robot-mower-yard-ha-test >/dev/null 2>&1 || true
rm -rf /tmp/robot-mower-yard-ha-test
mkdir -p /tmp/robot-mower-yard-ha-test
docker run -d --name robot-mower-yard-ha-test \
  -p 8123:8123 \
  -v /tmp/robot-mower-yard-ha-test:/config \
  -v "$PWD/custom_components:/config/custom_components:ro" \
  ghcr.io/home-assistant/home-assistant:stable
```

Then open <http://localhost:8123>. Stop it with:

```bash
docker rm -f robot-mower-yard-ha-test
```
