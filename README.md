# Vext for Home Assistant

[![tests](https://github.com/necmes/ha-vext/actions/workflows/tests.yml/badge.svg)](https://github.com/necmes/ha-vext/actions/workflows/tests.yml)

> ⚠️ **Unofficial community integration.** Not made by, affiliated with, endorsed
> by, or supported by Vext. Vext does not publish a public API: the interface this
> integration uses can change or disappear at any time, without notice, and the
> integration will simply stop working when it does. Use at your own risk, with
> your own account and your own cabinets. No warranty.
>
> **Please do not contact Vext support about this integration.** If something is
> broken here, open an issue on this repository. Suspected security issues go to
> Vext privately — see [SECURITY.md](SECURITY.md).

Brings your **Vext** indoor smart gardens into Home Assistant. Sign in with your
Vext app account and each cabinet shows up as a Home Assistant **device** with
sensors and a few controls, plus a bundled dashboard card.

## Install (HACS)

1. HACS → **⋮** → **Custom repositories** → add `https://github.com/necmes/ha-vext`,
   category **Integration**.
2. Search **Vext** in HACS → **Download** → **Restart Home Assistant**.
3. **Settings → Devices & Services → Add Integration → Vext** → sign in with your
   Vext **email + password**.

## What you get

Per cabinet (one HA device):

- **Sensors** — temperature, humidity, water, nutrient grow/bloom, plant-health
  score, pods ready / past-prime (with the plant list), water-refill estimate,
  wifi signal, firmware.
- **Controls** — brightness, fog moisture, fog rhythm, lights on/off times.

Temperature and humidity keep long-term statistics, so history graphs work.

## Dashboard card

A card ships with the integration — no extra frontend downloads needed. Add a
card and pick **Vext Cabinet Card**, or in YAML:

```yaml
type: custom:vext-cabinet-card
# optional, otherwise all cabinets are shown:
# cabinet: "Vext cabinet left"
# optional, only if your tank differs from the 24 L default:
# water_max_l: 24
# nutrient_max_ml: 350
```

It shows plant health, the sensor tiles, the plant wall, and the controls.

## How it behaves towards the Vext service

This integration is deliberately a light, well-behaved client:

| | |
|---|---|
| **Identification** | Every request sends `User-Agent: HomeAssistant-Vext/<version> (+https://github.com/necmes/ha-vext)`. |
| **Authentication** | Normal sign-in with *your* account, same as the app. The session is renewed with the refresh token; the password is only replayed when the refresh token is rejected. |
| **Polling** | Every 120 s by default. Configurable in the integration's **Configure** dialog, but never below **60 s** — the floor is enforced in code, not just in the UI. |
| **Volume** | One poll = 5 sequential reads (cabinets, settings, telemetry, cabinet data, plants). About 2.5 requests per minute in the default configuration, regardless of how many cabinets the account has. |
| **Errors** | Exponential backoff (×2, capped at 30 min), `Retry-After` honoured on 429/503. Bad credentials stop polling entirely and raise a Home Assistant re-auth prompt instead of retrying. |
| **Payload** | Only the columns actually displayed are requested. |
| **Writes** | Only settings you change yourself (brightness, fog, light schedule), on your own cabinets, debounced so dragging a slider sends one request. |
| **Scope** | Reads and writes your own account's data only. No probing, no scanning, no attempt to work around access controls. |

Contributions that make the integration noisier against the service will not be
merged. See [SECURITY.md](SECURITY.md).

## Credentials

Your email and password are stored only in Home Assistant's config entry storage.
Nothing is written to disk in plain text by this integration.

## Development

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-test.txt
pytest --cov=custom_components/vext --cov-branch --cov-report=term-missing
```

The suite covers 100% of statements and branches, and CI fails below that. It
pins the behaviour that matters against the service: the User-Agent on every
request, the 60 second poll floor, the exponential backoff and `Retry-After`
handling, the refresh-token flow, and the fact that a session only ever sees
its own account's cabinets.

## License

MIT.
