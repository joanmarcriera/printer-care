# Home Assistant integration

Two independent pieces: HA's core **Brother** integration reads ink/toner natively;
**printer-care** pushes its own events (keep-alive printed/stuck, counter unreadable...) to a webhook.

## 1. Ink and toner sensors (core `brother` integration)

*Settings > Devices & services > Add integration > Brother Printer*, enter the printer's
hostname (e.g. `colour-printer.example.lan`) and the printer type (`laser` for the HL series,
`ink` for the DCP-T series). You get entities such as `sensor.<name>_black_ink`,
`..._cyan_ink`, `..._magenta_ink`, `..._yellow_ink` (percent) and for lasers `..._black_toner_remaining`,
`..._drum_remaining_life`. Names depend on what you called the device - check
*Developer tools > States* and substitute them below.

## 2. printer-care webhook -> phone notification

Set in `/etc/printer-care.conf`:
`HA_WEBHOOK_URL=http://homeassistant.example.lan:8123/api/webhook/printer_care`

```yaml
alias: Printer care event
description: Forward printer-care events to the phone
triggers:
  - trigger: webhook
    webhook_id: printer_care
    allowed_methods: [POST]
    local_only: true
actions:
  - action: notify.mobile_app_<phone>
    data:
      title: "Printer care: {{ trigger.json.event }} ({{ trigger.json.printer }})"
      message: "{{ trigger.json.message }}"
mode: queued
```

`local_only: true` means only requests from the local network are accepted - keep the
Pi and Home Assistant on the same LAN and never expose the webhook publicly. (On HA older than
2024.10 use `trigger: - platform: webhook` / `service:` instead of `triggers:`/`action:`.)

## 3. Alert when any ink/toner is below 15 %

```yaml
alias: Printer ink or toner low
triggers:
  - trigger: numeric_state
    entity_id:
      - sensor.colour_printer_black_ink
      - sensor.colour_printer_cyan_ink
      - sensor.colour_printer_magenta_ink
      - sensor.colour_printer_yellow_ink
      - sensor.black_printer_black_toner_remaining
    below: 15
actions:
  - action: notify.mobile_app_<phone>
    data:
      title: "Printer supply low"
      message: "{{ trigger.to_state.name }} is at {{ trigger.to_state.state }}%"
mode: queued
```

(Brother ink-tank printers report a low-level threshold of about 7-11 %; 15 % gives time to buy ink.)

## 4. Conditional Lovelace card: "Ink low"

Shown only while at least one supply is below 15.

```yaml
type: conditional
conditions:
  - condition: or
    conditions:
      - condition: numeric_state
        entity: sensor.colour_printer_black_ink
        below: 15
      - condition: numeric_state
        entity: sensor.colour_printer_cyan_ink
        below: 15
      - condition: numeric_state
        entity: sensor.colour_printer_magenta_ink
        below: 15
      - condition: numeric_state
        entity: sensor.colour_printer_yellow_ink
        below: 15
      - condition: numeric_state
        entity: sensor.black_printer_black_toner_remaining
        below: 15
card:
  type: entities
  title: Ink low
  entities:
    - sensor.colour_printer_black_ink
    - sensor.colour_printer_cyan_ink
    - sensor.colour_printer_magenta_ink
    - sensor.colour_printer_yellow_ink
    - sensor.black_printer_black_toner_remaining
```
