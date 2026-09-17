"""Recreate the labeled synthetic fixture; contains no physical measurements."""
from pathlib import Path
import json

SID = "19ad1000-0000-4000-8000-000000000001"
EPOCH_UNIX_MS = 1790000000000
records = []


def emit(kind, seconds, payload, source=None):
    records.append({"schema": "atomos.radio.v1", "session_id": SID, "seq": len(records),
        "kind": kind, "received_elapsed_ns": str((1000 + seconds) * 10**9),
        "received_unix_ms": EPOCH_UNIX_MS + seconds * 1000,
        "source_elapsed_ns": None if source is None else str((1000 + source) * 10**9),
        "payload": payload})


def wifi(rssi=-55, *, batch="synthetic-1", origin="wifi_scan_broadcast", updated=True):
    return {"ssid": "SYNTHETIC_TEST_AP", "bssid": "02:19:00:00:00:01",
            "frequency_mhz": 5180, "channel_width": 2, "rssi_dbm": rssi,
            "capabilities": "[SYNTHETIC][WPA2-PSK-CCMP][ESS]",
            "source_timestamp_unit": "us", "batch_id": batch,
            "origin": origin, "results_updated": updated,
            "fixture_unknown_field": {"large_integer": 2**80 + 123}}


def lte(rsrp=-103, *, api29=False, origin="cell_info_callback"):
    signal = {"dbm": rsrp, "rsrp_dbm": rsrp, "rsrq_db": -12,
              "rssi_dbm": -77, "timing_advance_raw": 2,
              "vendor_quality_unknown": {"code": 7}}
    signal["rssnr_tenth_db" if api29 else "rssnr_db"] = 115 if api29 else 11
    return {"subscription_id": 1, "rat": "LTE", "registered": True,
            "connection_status": 1, "identity": {"mcc": "204", "mnc": "99",
            "ci": 19000001, "tac": 19, "pci": 101, "earfcn": 1650},
            "signal": signal, "source_timestamp_unit": "ns" if api29 else "ms",
            "origin": origin, "rssnr_api_sdk": 29 if api29 else 36}


def nr(rsrp=-97):
    return {"subscription_id": 1, "rat": "NR", "registered": False,
            "connection_status": 2, "identity": {"mcc": "204", "mnc": "99",
            "nci": 68719476735, "tac": 19, "pci": 201, "nrarfcn": 640000},
            "signal": {"dbm": rsrp, "ss_rsrp_dbm": rsrp, "ss_rsrq_db": -11,
            "ss_sinr_db": 14, "csi_rsrp_dbm": None, "csi_rsrq_db": None,
            "csi_sinr_db": None}, "source_timestamp_unit": "ms",
            "origin": "cell_info_callback"}


emit("session", 0, {"synthetic": True, "label": "SYNTHETIC: no device or over-air measurements",
    "signal_type": "reported_power_quality", "permissions": {"fine_location": True,
    "read_phone_state": True, "nearby_wifi_devices": True},
    "collection_intervals_ms": {"wifi_request": 35000, "cell_request": 10000},
    "device": {"model": "SYNTHETIC_FIXTURE", "sdk_int": 36},
    "app": {"version": "R19 study fixture"}, "time": {"elapsed_clock": "since_boot_including_sleep"},
    "historical_unit_case": "One labeled API29 LTE observation tests tenths-dB input handling; not one real device run."})
emit("status", 0, {"code": "synthetic_fixture", "message": "All observations are invented test data.", "details": {}})
emit("marker", 1, {"text": "SYNTHETIC stationary interval label"})
emit("wifi", 1, wifi(), 0)
emit("cell", 1, lte(), 0)
emit("cell", 1, nr(), 0)
emit("wifi", 3, wifi(batch="synthetic-2", updated=False), 0)
emit("cell", 3, lte(origin="periodic_cached_read"), 0)
emit("status", 4, {"code": "wifi_scan_request_rejected", "message": "SYNTHETIC throttled scan request", "details": {"request_accepted": False}})
emit("wifi", 10, wifi(-56, batch="synthetic-3"), 9)
emit("cell", 10, lte(-105), 9)
emit("cell", 10, nr(-99), 9)
emit("marker", 15, {"text": "SYNTHETIC phone orientation changed; marker only"})
emit("wifi", 20, wifi(-60, batch="synthetic-4"), 19)
emit("cell", 20, lte(-107, api29=True), 19)
emit("cell", 20, nr(-101), None)
emit("status", 30, {"code": "permission_unavailable", "message": "SYNTHETIC permission interruption", "details": {"fine_location": False}})
emit("wifi", 45, wifi(batch="synthetic-5", origin="cached_read", updated=False), 0)
emit("marker", 46, {"text": "No range, phase, position or handover is implied by this fixture."})
emit("session_end", 50, {"reason": "synthetic_complete", "counts": {"events_before_end": len(records)}})
target = Path(__file__).with_name("synthetic_radio.jsonl")
target.write_bytes(b"".join((json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8") for r in records))
print(target)
