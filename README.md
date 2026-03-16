# WAPDA Monitor for Home Assistant

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/v/release/uppaljs/wapda-monitor-hacs?style=for-the-badge)](https://github.com/uppaljs/wapda-monitor-hacs/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](LICENSE)

A Home Assistant custom integration that monitors WAPDA electricity feeders in real time using the [Roshan Pakistan](https://roshanpakistan.pk) / CCMS PITC portal.

Track your feeder's live ON/OFF status, voltage, load shedding schedule, billing, net metering, and more — all natively inside Home Assistant. No external servers needed.

---

## Install with HACS

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=uppaljs&repository=wapda-monitor-hacs&category=integration)

Or manually: **HACS** → ⋮ → **Custom repositories** → paste `https://github.com/uppaljs/wapda-monitor-hacs` → Category: **Integration** → **Add** → **Download**

Then restart Home Assistant.

---

## What You Get

Each reference number creates a **device** with 30+ entities:

### Real-Time Feeder

| Sensor | Description |
|--------|-------------|
| Feeder Status | ON / OFF |
| Feeder Name | Feeder name from grid |
| Grid Station | Grid station name |
| Grid Voltage | Voltage in kV |
| Grid Current | Current in Amps |
| Active Power | Power in kW |
| Reactive Power | Reactive power in kVar |
| Power Factor | Power factor |
| Feeder Remarks | Operational remarks (e.g. "Tripped", "Under Maintenance") |
| Last Event | Most recent ON/OFF transition with timestamp |
| Status Duration | How long feeder has been in current state |

### Billing & Net Metering

| Sensor | Description |
|--------|-------------|
| Amount Due | Current bill in PKR |
| Net Bill | Net bill after adjustments |
| Bill Due Date | Payment deadline |
| Bill Due In | Days until due date |
| Monthly Consumption | kWh consumed this billing cycle |
| Arrears | Outstanding amount |
| Export Off-Peak / Peak | Net metering export units |
| Import Off-Peak / Peak | Net metering import units |
| Net Metering Balance | Export minus import (positive = you're earning) |
| Energy Charges | Energy charges in PKR |
| Fixed Charges | Fixed charges in PKR |
| FPA | Fuel Price Adjustment |
| GST | General Sales Tax |

### Load Shedding Schedule

| Sensor | Description |
|--------|-------------|
| Scheduled Outage Today | Total scheduled outage hours for today |
| Next Outage In | Hours until the next scheduled outage slot |

### Binary Sensors

| Sensor | Triggers When |
|--------|---------------|
| **Feeder OFF** | Feeder status = OFF (includes voltage & remarks as attributes) |
| **Scheduled Outage Now** | There is a planned outage during the current hour |

### Account Info

| Sensor | Description |
|--------|-------------|
| Account Name | Consumer name from WAPDA records |
| Tariff | Tariff code (A1, A2, A3, etc.) |

---

## Supported DISCOs

Works with any electricity distribution company that uses the PITC/Roshan Pakistan portal:

**IESCO** · **LESCO** · **FESCO** · **MEPCO** · **GEPCO** · **PESCO** · **HESCO** · **SEPCO** · **QESCO** · **TESCO**

---

## Setup

1. **Settings** → **Devices & Services** → **Add Integration**
2. Search for **WAPDA Monitor**
3. Enter your **14-digit reference number** (from your electricity bill)
4. Done — the integration validates against the Roshan Pakistan server and creates all sensors

Add multiple accounts by adding the integration again with a different reference number.

### Polling Intervals (Configurable)

Click **Configure** on the integration card to adjust:

| Data | Default | Range |
|------|---------|-------|
| Feeder status | 5 min | 1 min – 1 hr |
| Billing | 12 hr | 1 hr – 24 hr |
| Schedule | 15 min | 5 min – 2 hr |

---

## Automation Examples

### Power outage alert

```yaml
automation:
  - alias: "Feeder OFF Alert"
    trigger:
      - platform: state
        entity_id: binary_sensor.wapda_XXXXXX_feeder_off
        to: "on"
    action:
      - service: notify.mobile_app_your_phone
        data:
          title: "Power Outage"
          message: >
            {{ states('sensor.wapda_XXXXXX_feeder_name') }} is OFF.
            Voltage: {{ states('sensor.wapda_XXXXXX_feeder_voltage') }} kV
            Remarks: {{ states('sensor.wapda_XXXXXX_feeder_remarks') }}
```

### Pre-charge battery before scheduled outage

```yaml
automation:
  - alias: "Pre-Charge Battery"
    trigger:
      - platform: numeric_state
        entity_id: sensor.wapda_XXXXXX_next_outage_in
        below: 2
    condition:
      - condition: numeric_state
        entity_id: sensor.your_inverter_battery_soc
        below: 80
    action:
      - service: number.set_value
        target:
          entity_id: number.your_inverter_charge_current
        data:
          value: 50
```

### Bill due reminder

```yaml
automation:
  - alias: "Bill Due Reminder"
    trigger:
      - platform: numeric_state
        entity_id: sensor.wapda_XXXXXX_bill_due_in
        below: 4
    action:
      - service: notify.mobile_app_your_phone
        data:
          title: "Electricity Bill Due Soon"
          message: >
            Rs. {{ states('sensor.wapda_XXXXXX_current_bill') }} due in
            {{ states('sensor.wapda_XXXXXX_bill_due_in') }} days
```

---

## Dashboard Card

```yaml
type: entities
title: WAPDA Feeder
entities:
  - entity: binary_sensor.wapda_XXXXXX_feeder_off
  - entity: sensor.wapda_XXXXXX_feeder_name
  - entity: sensor.wapda_XXXXXX_feeder_voltage
  - entity: sensor.wapda_XXXXXX_active_power
  - entity: sensor.wapda_XXXXXX_status_duration
  - entity: sensor.wapda_XXXXXX_feeder_remarks
  - entity: sensor.wapda_XXXXXX_scheduled_outage_today
  - entity: sensor.wapda_XXXXXX_next_outage_in
  - entity: sensor.wapda_XXXXXX_current_bill
  - entity: sensor.wapda_XXXXXX_bill_due_in
  - entity: sensor.wapda_XXXXXX_net_metering_balance
```

---

## How It Works

The integration connects to the PITC CCMS portal (the backend behind Roshan Pakistan) using five internal API endpoints:

| # | Method | Endpoint | Data |
|---|--------|----------|------|
| 1 | GET | `/get-loadinfo/{ref}` | Real-time feeder status, voltage, power, event logs |
| 2 | GET | `/api/details/user?reference=` | Consumer name, address, tariff, feeder code |
| 3 | GET | `/api/details/bill?reference=` | Billing, charges breakdown, net metering, payment history |
| 4 | GET | `/api/schedule_api?feeder_code=&disco_code=` | Hourly outage schedule & actual outage history |
| 5 | POST | `/getflsinfo` | Load shedding schedule (HTML format, not used in HA) |

The integration mimics a real browser session with rotating User-Agent strings, proper Sec-CH-UA headers, and session cookie management to avoid being blocked. All HTTP calls run in a background executor thread so they never block the Home Assistant event loop.

---

## Manual Installation

1. Download the [latest release](https://github.com/uppaljs/wapda-monitor-hacs/releases)
2. Copy `custom_components/wapda_monitor/` to your Home Assistant `config/custom_components/` directory
3. Restart Home Assistant
4. Add via Settings → Devices & Services → Add Integration → WAPDA Monitor

---

## Troubleshooting

**"Cannot connect to the Roshan Pakistan server"**
The portal at ccms.pitc.com.pk must be reachable from your HA instance. Check if the site is accessible in a browser and that your HA server has internet access.

**Some sensors show "unavailable"**
Not all feeders have AMI (smart) meters installed — load info may be empty for some reference numbers. The schedule API occasionally returns server errors for certain feeder codes. Billing data may be unavailable between billing cycles.

**Feeder code not found**
The integration gets the feeder code from load info first, then falls back to user details (FEEDERCD). If both are empty, schedule-related sensors won't populate.

---

## Notes

- This is an unofficial community integration, not affiliated with PITC, WAPDA, or any DISCO
- Data accuracy depends on the Roshan Pakistan / CCMS server
- Some feeders lack AMI metering and will only return billing + customer data
- Be considerate with polling intervals — aggressive polling may trigger rate limiting on the CCMS server

---

## License

[MIT](LICENSE)
