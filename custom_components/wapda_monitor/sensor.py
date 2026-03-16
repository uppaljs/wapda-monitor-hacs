"""Sensor platform for WAPDA Monitor."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_REFERENCE, DATA_BILL, DATA_LOAD, DATA_SCHEDULE, DATA_USER, DOMAIN, MANUFACTURER
from .coordinator import WapdaDataCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up WAPDA Monitor sensors from a config entry."""
    coordinator: WapdaDataCoordinator = hass.data[DOMAIN][entry.entry_id]
    reference = entry.data[CONF_REFERENCE]

    entities: list[SensorEntity] = [
        # --- Load / Feeder sensors ---
        WapdaSensor(coordinator, reference, "feeder_status", "Feeder Status",
                    icon="mdi:transmission-tower", category="load",
                    value_fn=lambda d: d.get("current_status")),
        WapdaSensor(coordinator, reference, "feeder_name", "Feeder Name",
                    icon="mdi:transmission-tower", category="load",
                    value_fn=lambda d: d.get("feeder")),
        WapdaSensor(coordinator, reference, "grid_name", "Grid Station",
                    icon="mdi:office-building", category="load",
                    value_fn=lambda d: d.get("grid")),
        WapdaSensor(coordinator, reference, "feeder_voltage", "Grid Voltage",
                    icon="mdi:flash", category="load",
                    device_class=SensorDeviceClass.VOLTAGE,
                    unit=UnitOfElectricPotential.KILOVOLT,
                    state_class=SensorStateClass.MEASUREMENT,
                    value_fn=lambda d: _num(d.get("voltage"))),
        WapdaSensor(coordinator, reference, "feeder_current", "Grid Current",
                    icon="mdi:current-ac", category="load",
                    device_class=SensorDeviceClass.CURRENT,
                    unit=UnitOfElectricCurrent.AMPERE,
                    state_class=SensorStateClass.MEASUREMENT,
                    value_fn=lambda d: _num(d.get("current"))),
        WapdaSensor(coordinator, reference, "active_power", "Active Power",
                    icon="mdi:flash-triangle", category="load",
                    device_class=SensorDeviceClass.POWER,
                    unit=UnitOfPower.KILO_WATT,
                    state_class=SensorStateClass.MEASUREMENT,
                    value_fn=lambda d: _num(d.get("active_power_kW"))),
        WapdaSensor(coordinator, reference, "reactive_power", "Reactive Power",
                    icon="mdi:flash-triangle-outline", category="load",
                    unit="kVar",
                    state_class=SensorStateClass.MEASUREMENT,
                    value_fn=lambda d: _num(d.get("reactive_power_kVar"))),
        WapdaSensor(coordinator, reference, "power_factor", "Power Factor",
                    icon="mdi:angle-acute", category="load",
                    device_class=SensorDeviceClass.POWER_FACTOR,
                    state_class=SensorStateClass.MEASUREMENT,
                    value_fn=lambda d: _num(d.get("power_factor"))),
        WapdaSensor(coordinator, reference, "feeder_remarks", "Feeder Remarks",
                    icon="mdi:message-text", category="load",
                    value_fn=lambda d: d.get("remarks") or "N/A"),
        WapdaSensor(coordinator, reference, "last_event", "Last Event",
                    icon="mdi:history", category="load",
                    value_fn=_last_event_value,
                    attrs_fn=_last_event_attrs),
        WapdaSensor(coordinator, reference, "status_duration", "Status Duration",
                    icon="mdi:timer-sand", category="load",
                    value_fn=_status_duration_value),

        # --- User / Account sensors ---
        WapdaSensor(coordinator, reference, "account_name", "Account Name",
                    icon="mdi:account", category="user",
                    value_fn=lambda d: (d.get("NAME") or "").strip()),
        WapdaSensor(coordinator, reference, "tariff", "Tariff",
                    icon="mdi:tag", category="user",
                    value_fn=lambda d: (d.get("TARIFF") or "").strip()),

        # --- Billing sensors ---
        WapdaSensor(coordinator, reference, "current_bill", "Amount Due",
                    icon="mdi:currency-rupee", category="bill",
                    unit="PKR", state_class=SensorStateClass.TOTAL,
                    value_fn=lambda d: _bill_val(d, "currAmntDue")),
        WapdaSensor(coordinator, reference, "net_bill", "Net Bill",
                    icon="mdi:receipt-text", category="bill",
                    unit="PKR", state_class=SensorStateClass.TOTAL,
                    value_fn=lambda d: _bill_val(d, "netBill")),
        WapdaSensor(coordinator, reference, "bill_due_date", "Bill Due Date",
                    icon="mdi:calendar-clock", category="bill",
                    value_fn=lambda d: _bill_str(d, "billDueDate")),
        WapdaSensor(coordinator, reference, "bill_due_in", "Bill Due In",
                    icon="mdi:calendar-alert", category="bill",
                    unit="days",
                    value_fn=_bill_due_in_value),
        WapdaSensor(coordinator, reference, "monthly_consumption", "Monthly Consumption",
                    icon="mdi:meter-electric", category="bill",
                    device_class=SensorDeviceClass.ENERGY,
                    unit=UnitOfEnergy.KILO_WATT_HOUR,
                    state_class=SensorStateClass.TOTAL,
                    value_fn=lambda d: _bill_val(d, "totCurCons")),
        WapdaSensor(coordinator, reference, "arrears", "Arrears",
                    icon="mdi:cash-clock", category="bill",
                    unit="PKR",
                    value_fn=lambda d: _bill_val(d, "arrear")),

        # Net metering
        WapdaSensor(coordinator, reference, "export_off_peak", "Export Off-Peak",
                    icon="mdi:solar-power", category="bill",
                    unit="units", state_class=SensorStateClass.TOTAL,
                    value_fn=lambda d: _bill_val(d, "exp_op_units")),
        WapdaSensor(coordinator, reference, "export_peak", "Export Peak",
                    icon="mdi:solar-power-variant", category="bill",
                    unit="units", state_class=SensorStateClass.TOTAL,
                    value_fn=lambda d: _bill_val(d, "exp_p_units")),
        WapdaSensor(coordinator, reference, "import_off_peak", "Import Off-Peak",
                    icon="mdi:transmission-tower-import", category="bill",
                    unit="units", state_class=SensorStateClass.TOTAL,
                    value_fn=lambda d: _bill_val(d, "imp_op_units")),
        WapdaSensor(coordinator, reference, "import_peak", "Import Peak",
                    icon="mdi:transmission-tower-export", category="bill",
                    unit="units", state_class=SensorStateClass.TOTAL,
                    value_fn=lambda d: _bill_val(d, "imp_p_units")),
        WapdaSensor(coordinator, reference, "net_metering_balance", "Net Metering Balance",
                    icon="mdi:scale-balance", category="bill",
                    unit="units",
                    value_fn=_net_metering_balance_value),

        # Charges breakdown
        WapdaSensor(coordinator, reference, "energy_charges", "Energy Charges",
                    icon="mdi:lightning-bolt", category="bill",
                    unit="PKR",
                    value_fn=lambda d: _charge_val(d, "companyCharges", "energyCharges")),
        WapdaSensor(coordinator, reference, "fixed_charges", "Fixed Charges",
                    icon="mdi:currency-rupee", category="bill",
                    unit="PKR",
                    value_fn=lambda d: _charge_val(d, "companyCharges", "fixedCharges")),
        WapdaSensor(coordinator, reference, "fpa", "FPA (Fuel Price Adjustment)",
                    icon="mdi:gas-station", category="bill",
                    unit="PKR",
                    value_fn=lambda d: _bill_val(d, "totalFpa")),
        WapdaSensor(coordinator, reference, "gst", "GST",
                    icon="mdi:percent", category="bill",
                    unit="PKR",
                    value_fn=lambda d: _charge_val(d, "govtCharges", "gst")),

        # --- Schedule sensors ---
        WapdaSensor(coordinator, reference, "scheduled_outage_today", "Scheduled Outage Today",
                    icon="mdi:calendar-clock", category="schedule",
                    unit="hours",
                    value_fn=_scheduled_outage_today_value),
        WapdaSensor(coordinator, reference, "next_outage_in", "Next Outage In",
                    icon="mdi:clock-alert", category="schedule",
                    unit="hours",
                    value_fn=_next_outage_in_value),
    ]

    async_add_entities(entities)


# ====================================================================== #
#  Value extraction helpers
# ====================================================================== #

def _num(val: Any) -> float | None:
    """Safely convert to float."""
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _bill_val(bill_data: dict | None, key: str) -> float | None:
    """Extract a numeric value from bill.basicInfo."""
    if not bill_data:
        return None
    basic = bill_data.get("basicInfo")
    if not basic:
        return None
    return _num(basic.get(key))


def _bill_str(bill_data: dict | None, key: str) -> str | None:
    """Extract a string value from bill.basicInfo."""
    if not bill_data:
        return None
    basic = bill_data.get("basicInfo")
    if not basic:
        return None
    val = basic.get(key)
    return str(val).strip() if val else None


def _charge_val(bill_data: dict | None, group: str, key: str) -> float | None:
    """Extract a charge from bill.basicInfo.companyCharges or govtCharges."""
    if not bill_data:
        return None
    basic = bill_data.get("basicInfo")
    if not basic:
        return None
    charges = basic.get(group)
    if not charges:
        return None
    return _num(charges.get(key))


def _last_event_value(load: dict | None) -> str | None:
    """Format the most recent event log entry."""
    if not load:
        return None
    events = load.get("event_logs", [])
    if not events:
        return None
    ev = events[0]
    return f"{ev.get('event', '')} at {ev.get('event_time', '')}"


def _last_event_attrs(load: dict | None) -> dict:
    """Return full event list as attributes."""
    if not load:
        return {}
    events = load.get("event_logs", [])
    return {
        "events": events,
        "event_count": len(events),
    }


def _status_duration_value(load: dict | None) -> str | None:
    """Calculate how long the feeder has been in its current status."""
    if not load:
        return None
    status_time = load.get("current_status_time")
    if not status_time:
        return None
    try:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%d-%m-%Y %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
            try:
                dt = datetime.strptime(status_time, fmt)
                delta = datetime.now() - dt
                hours = int(delta.total_seconds() // 3600)
                minutes = int((delta.total_seconds() % 3600) // 60)
                if hours > 0:
                    return f"{hours}h {minutes}m"
                return f"{minutes}m"
            except ValueError:
                continue
        return status_time
    except Exception:  # noqa: BLE001
        return status_time


def _bill_due_in_value(bill_data: dict | None) -> int | None:
    """Calculate days until bill due date."""
    if not bill_data:
        return None
    basic = bill_data.get("basicInfo")
    if not basic:
        return None
    due_str = basic.get("billDueDate")
    if not due_str:
        return None
    try:
        for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
            try:
                due_date = datetime.strptime(due_str.strip(), fmt).date()
                return (due_date - datetime.now().date()).days
            except ValueError:
                continue
        return None
    except Exception:  # noqa: BLE001
        return None


def _net_metering_balance_value(bill_data: dict | None) -> float | None:
    """Calculate export minus import units."""
    if not bill_data:
        return None
    basic = bill_data.get("basicInfo")
    if not basic:
        return None
    try:
        exp_op = float(basic.get("exp_op_units") or 0)
        exp_p = float(basic.get("exp_p_units") or 0)
        imp_op = float(basic.get("imp_op_units") or 0)
        imp_p = float(basic.get("imp_p_units") or 0)
        return (exp_op + exp_p) - (imp_op + imp_p)
    except (ValueError, TypeError):
        return None


def _scheduled_outage_today_value(schedule: dict | None) -> float | None:
    """Total scheduled outage hours for today."""
    if not schedule:
        return None
    maint = schedule.get("maintenance_sch", [])
    if not maint or not isinstance(maint, list):
        return None
    total_mins = sum(m for m in maint if isinstance(m, (int, float)))
    return round(total_mins / 60, 1)


def _next_outage_in_value(schedule: dict | None) -> float | None:
    """Hours until next scheduled outage slot (from maintenance_sch)."""
    if not schedule:
        return None
    maint = schedule.get("maintenance_sch", [])
    if not maint or not isinstance(maint, list):
        return None
    now_hour = datetime.now().hour
    for offset in range(1, 25):
        idx = (now_hour + offset) % 24
        if idx < len(maint) and maint[idx] > 0:
            return offset
    return None


# ====================================================================== #
#  Entity class
# ====================================================================== #

class WapdaSensor(CoordinatorEntity[WapdaDataCoordinator], SensorEntity):
    """Representation of a single WAPDA Monitor sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: WapdaDataCoordinator,
        reference: str,
        key: str,
        name: str,
        *,
        icon: str | None = None,
        category: str,
        value_fn,
        attrs_fn=None,
        device_class: SensorDeviceClass | None = None,
        unit: str | None = None,
        state_class: SensorStateClass | None = None,
    ) -> None:
        super().__init__(coordinator)
        self._reference = reference
        self._key = key
        self._category = category
        self._value_fn = value_fn
        self._attrs_fn = attrs_fn

        self._attr_name = name
        self._attr_unique_id = f"wapda_{reference}_{key}"
        self._attr_icon = icon
        self._attr_device_class = device_class
        self._attr_native_unit_of_measurement = unit
        self._attr_state_class = state_class

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._reference)},
            name=f"WAPDA Feeder Monitor {self._reference}",
            manufacturer=MANUFACTURER,
            model="WAPDA Feeder Monitor",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def native_value(self) -> Any:
        data = self.coordinator.data
        if not data:
            return None
        category_data = data.get(self._category)
        try:
            return self._value_fn(category_data)
        except Exception:  # noqa: BLE001
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self._attrs_fn is None:
            return None
        data = self.coordinator.data
        if not data:
            return None
        category_data = data.get(self._category)
        try:
            return self._attrs_fn(category_data)
        except Exception:  # noqa: BLE001
            return None
