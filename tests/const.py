"""Constants for WAPDA Monitor tests."""

MOCK_REFERENCE = "01234567890123"

MOCK_USER_INPUT = {
    "reference": MOCK_REFERENCE,
}

MOCK_LOAD_DATA = {
    "feeder_code": "FDR001",
    "feeder_name": "Test Feeder",
    "grid_station": "Test Grid",
    "current_status": "ON",
    "voltage": "11.2",
    "current": "150",
    "active_power": "1200",
    "reactive_power": "300",
    "power_factor": "0.97",
    "remarks": "",
    "last_event": "2025-01-15 10:30:00",
    "status_duration": "2h 30m",
}

MOCK_USER_DATA = {
    "NAME": "Test Consumer",
    "CONSNAME": "Test Consumer",
    "CONSADDRESS": "123 Test Street",
    "TARIFF": "A1",
    "FEEDERCD": "FDR001",
    "CNIC": "12345-6789012-3",
    "MOBILE": "03001234567",
}

MOCK_BILL_DATA = {
    "NETAMT": "5000",
    "DUEDATE": "2025-02-15",
    "CONSUMPTION": "350",
    "ARREARS": "0",
    "ENERGYCHG": "3500",
    "FIXEDCHG": "500",
    "FPA": "200",
    "GST": "800",
    "EXPORTOFFPEAK": "10",
    "EXPORTPEAK": "5",
    "IMPORTOFFPEAK": "200",
    "IMPORTPEAK": "150",
}

MOCK_SCHEDULE_DATA = {
    "maintenance_sch": {str(i): 0 for i in range(24)},
    "feeder_code": "FDR001",
}

MOCK_COORDINATOR_DATA = {
    "load": MOCK_LOAD_DATA,
    "user": MOCK_USER_DATA,
    "bill": MOCK_BILL_DATA,
    "schedule": MOCK_SCHEDULE_DATA,
}
