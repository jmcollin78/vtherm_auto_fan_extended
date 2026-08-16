# Versatile Thermostat — Auto Fan plugin

`vtherm_auto_fan_extended` is an external plugin for
[Versatile Thermostat](https://github.com/jmcollin78/versatile_thermostat) (VTherm).

It brings back the historical **auto-fan** feature — automatically driving the
fan speed of an underlying climate depending on the temperature gap — as a
standalone [Feature Manager](documentation/tech-docs/auto-fan-plugin.md) plugin
instead of being hard-coded in the VTherm core.

## What it does

For every `over_climate` VTherm exposing `fan_modes`, the plugin creates a set
of configuration entities and, at each control cycle:

1. Computes the temperature gap `dtemp = target − current`.
2. Selects the underlying `fan_mode` whose **activation threshold** is the
   greatest one that is `> 0` and `≤ |dtemp|`, provided it is coherent with the
   current HVAC mode (heating/cooling/off).
3. Otherwise it applies the configured **rest** `fan_mode`.
4. The chosen `fan_mode` is only sent to the underlying when it actually
   changes.

Each `fan_mode` gets its own user-configurable threshold (a threshold of `0`
means the `fan_mode` never participates), so non-normalized `fan_modes`
(e.g. `on_low` / `on_high` / `auto_low` / `off`) are supported out of the box.

## Requirements

- Home Assistant `2025.1.0+`
- `versatile_thermostat` core with external Feature Manager support
- `vtherm_api >= 0.4.0`

## Installation

This plugin is **not yet published in the default HACS store**, so it must be
added as a **custom repository**.

### HACS (custom repository)

1. Open *HACS* in Home Assistant.
2. Click the top-right menu (⋮) and choose **Custom repositories**.
3. Add the repository URL
   `https://github.com/jmcollin78/vtherm_auto_fan_extended` and select the
   **Integration** category, then click **Add**.
4. Search for **Versatile Thermostat Auto Fan** in HACS, install it.
5. Restart Home Assistant.

### Manual

Copy `custom_components/vtherm_auto_fan_extended` into your Home Assistant
`config/custom_components/` folder, then restart Home Assistant.


## Configuration

Add the **Versatile Thermostat Auto Fan** integration from
*Settings → Devices & Services* and pick the target `over_climate` VTherm.
One entry is created per thermostat and exposes, attached to the VTherm device:

- one **`number`** *fan mode threshold* per underlying `fan_mode` (°C or °F,
  step `0.1`; `0` disables that `fan_mode`);
- one **`select`** *rest mode* (the `fan_mode` used when no threshold is
  reached);
- one **`switch`** *auto fan* to enable or disable the automation.

Sensible defaults are computed on first creation and can be adjusted from the
UI; the values are restored across restarts.

## Exposed attributes

The manager exposes its state under the top-level `auto_fan` attribute section:

- `enabled` — whether the auto fan switch is on
- `current_gap` — last temperature gap `dtemp`
- `selected_fan_mode` — `fan_mode` chosen by the algorithm
- `sent_fan_mode` — `fan_mode` last sent to the underlying
- `rest_mode` — configured rest `fan_mode`
- `thresholds` — per `fan_mode` activation thresholds

## Development

See [documentation/tech-docs/auto-fan-plugin.md](documentation/tech-docs/auto-fan-plugin.md)
for the full migration plan and architecture.

```bash
pip install -r requirements_test.txt
pytest
```
