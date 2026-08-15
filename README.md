# Versatile Thermostat — Auto Fan plugin

`vtherm_auto_fan_extended` is an external plugin for
[Versatile Thermostat](https://github.com/jmcollin78/versatile_thermostat) (VTherm).

It brings back the historical **auto-fan** feature — automatically driving the
fan speed of an underlying climate depending on the temperature gap — as a
standalone [Feature Manager](documentation/tech-docs/auto-fan-plugin.md) plugin
instead of being hard-coded in the VTherm core.

## What it does

For every `over_climate` VTherm, at each control cycle the plugin:

1. Maps a logical fan level (`none` / `low` / `medium` / `high` / `turbo`) onto a
   real `fan_mode` of the underlying climate, adapting to the number of
   available speeds.
2. Computes the temperature gap `dtemp = target − current`.
3. If `|dtemp| ≥ 2 °C` **and** it is coherent with the current HVAC mode, it
   sends the *activated* fan mode to the underlying; otherwise it sends the
   *deactivated* (silent) fan mode.

## Requirements

- Home Assistant `2025.1.0+`
- `versatile_thermostat` core with external Feature Manager support
- `vtherm_api >= 0.4.0`

## Installation

Copy `custom_components/vtherm_auto_fan_extended` into your Home Assistant
`config/custom_components/` folder (or install through HACS as a custom
repository), then restart Home Assistant.

## Configuration

Add the **Versatile Thermostat Auto Fan** integration from
*Settings → Devices & Services*:

- The first entry creates **global defaults** (the fan level applied to every
  `over_climate` VTherm that has no dedicated entry).
- Additional entries let you **override the level per thermostat**.

### Migration from the core auto-fan

If a VTherm config entry still contains the legacy `auto_fan_mode` key, the
plugin uses it as a fallback when no dedicated plugin entry exists.

## Service

For backward compatibility the auto fan level is changed through the historical
Versatile Thermostat service `versatile_thermostat.set_auto_fan_mode`:

```yaml
service: versatile_thermostat.set_auto_fan_mode
data:
  entity_id: climate.my_over_climate_vtherm
  auto_fan_mode: High   # None | Low | Medium | High | Turbo
```

## Exposed attributes

The manager exposes its state under the top-level `auto_fan` attribute section:

- `auto_fan_mode` — configured level
- `current_auto_fan_mode` — currently active level
- `auto_activated_fan_mode` — underlying fan mode used when activated
- `auto_deactivated_fan_mode` — underlying fan mode used when deactivated

## Development

See [documentation/tech-docs/auto-fan-plugin.md](documentation/tech-docs/auto-fan-plugin.md)
for the full migration plan and architecture.

```bash
pip install -r requirements_test.txt
pytest
```
