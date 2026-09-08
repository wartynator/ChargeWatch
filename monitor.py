#!/usr/bin/env python3
"""Poll ZSE Drive stations and append connector availability to Excel."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from openpyxl import Workbook, load_workbook

from database import save_snapshot


API_URL = "https://zsedrive.sk/api/v4.7/stations/{station_id}"
DEFAULT_STATIONS = (73151, 72182)
HEADERS = (
    "station_id",
    "connector_id",
    "evse_id",
    "state",
    "checked_at",
    "name",
    "address",
)
AVAILABLE_STATES = {"available", "free", "ready", "true", "1"}
UNAVAILABLE_STATES = {
    "unavailable",
    "occupied",
    "charging",
    "reserved",
    "faulted",
    "offline",
    "false",
    "0",
}


def fetch_station(station_id: int, timeout: float, attempts: int = 2) -> Any:
    for attempt in range(1, attempts + 1):
        print(
            f"Fetching station {station_id} (attempt {attempt}/{attempts})...",
            flush=True,
        )
        request = Request(
            API_URL.format(station_id=station_id),
            headers={
                "Accept": "application/json",
                "User-Agent": "Mozilla/5.0 (compatible; ConnectorMonitor/1.0)",
                "Referer": "https://zsedrive.sk/",
            },
        )
        try:
            with urlopen(request, timeout=timeout) as response:
                return json.load(response)
        except (URLError, TimeoutError) as error:
            if attempt == attempts:
                raise
            print(f"Station {station_id} request failed: {error}; retrying...", flush=True)
            time.sleep(attempt * 2)

    raise RuntimeError("Unreachable")


def _first(record: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in record and record[key] is not None:
            return record[key]
    return None


def _availability(record: dict[str, Any]) -> str:
    raw_state = _first(
        record,
        "available",
        "isAvailable",
        "freeConnector",
        "state",
        "status",
        "availability",
    )
    if isinstance(raw_state, bool):
        return "available" if raw_state else "unavailable"

    normalized = str(raw_state).strip().lower()
    if normalized in AVAILABLE_STATES:
        return "available"
    if normalized in UNAVAILABLE_STATES:
        return "unavailable"
    return normalized or "unknown"


def _format_address(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if not isinstance(value, dict):
        return ""

    preferred_keys = (
        "street",
        "streetName",
        "houseNumber",
        "postalCode",
        "zipCode",
        "city",
        "country",
    )
    parts = [str(value[key]).strip() for key in preferred_keys if value.get(key)]
    return ", ".join(dict.fromkeys(parts))


def extract_station_details(payload: Any) -> tuple[str, str]:
    """Extract display metadata without treating connector labels as station names."""
    pending = [payload]
    name = ""
    address = ""
    while pending and (not name or not address):
        value = pending.pop(0)
        if isinstance(value, list):
            pending.extend(value)
            continue
        if not isinstance(value, dict):
            continue

        if not name:
            name_value = _first(value, "stationName", "name", "title")
            if isinstance(name_value, str):
                name = name_value.strip()
        if not address:
            address_value = _first(
                value, "formattedAddress", "fullAddress", "address"
            )
            address = _format_address(address_value)

        pending.extend(
            child for key, child in value.items() if key not in {"connectors", "address"}
        )
    return name, address


def _connector_rows(
    connector_array: list[Any], station_id: int, parent_evse_id: Any
) -> list[dict[str, Any]]:
    rows = []
    for connector in connector_array:
        if not isinstance(connector, dict):
            continue
        connector_id = _first(connector, "connectorId", "connector_id", "id", "uid")
        connector_evse_id = _first(connector, "evseId", "evse_id", "evseUid")
        effective_evse_id = connector_evse_id or parent_evse_id or ""
        rows.append(
            {
                "station_id": station_id,
                "connector_id": connector_id if connector_id is not None else "",
                "evse_id": effective_evse_id,
                "state": _availability(connector),
            }
        )
    return rows


def extract_connectors(payload: Any, station_id: int) -> list[dict[str, Any]]:
    """Find connector objects while retaining an EVSE id from parent objects."""
    connectors: list[dict[str, Any]] = []
    station_name, station_address = extract_station_details(payload)
    pending: list[tuple[Any, Any]] = [(payload, None)]
    while pending:
        value, inherited_evse_id = pending.pop()
        if isinstance(value, dict):
            evse_id = _first(value, "evseId", "evse_id", "evseUid")
            if evse_id is None:
                evse_id = inherited_evse_id

            connector_array = value.get("connectors")
            if isinstance(connector_array, list):
                connector_rows = _connector_rows(connector_array, station_id, evse_id)
                for row in connector_rows:
                    row["name"] = station_name
                    row["address"] = station_address
                connectors.extend(connector_rows)

            pending.extend(
                (child, evse_id) for key, child in value.items() if key != "connectors"
            )
        elif isinstance(value, list):
            pending.extend((child, inherited_evse_id) for child in value)

    return connectors


def append_rows(path: Path, rows: list[dict[str, Any]], checked_at: datetime) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        workbook = load_workbook(path)
        worksheet = workbook["Availability"]
        for column_number, header in enumerate(HEADERS, start=1):
            worksheet.cell(row=1, column=column_number, value=header)
    else:
        workbook = Workbook()
        worksheet = workbook.active
        worksheet.title = "Availability"
        worksheet.append(HEADERS)
        worksheet.freeze_panes = "A2"
        worksheet.auto_filter.ref = "A1:E1"

    timestamp = checked_at.isoformat(timespec="seconds")
    for row in rows:
        worksheet.append(
            (
                row["station_id"],
                row["connector_id"],
                row["evse_id"],
                row["state"],
                timestamp,
                row["name"],
                row["address"],
            )
        )

    for column, width in zip("ABCDEFG", (14, 16, 24, 16, 28, 32, 48)):
        worksheet.column_dimensions[column].width = width
    workbook.save(path)


def persist_rows(
    database_url: str,
    excel_path: Path | None,
    rows: list[dict[str, Any]],
    checked_at: datetime,
) -> None:
    save_snapshot(database_url, rows, checked_at)
    if excel_path is not None:
        append_rows(excel_path, rows, checked_at)


def check_stations(
    station_ids: list[int],
    database_url: str,
    excel_path: Path | None,
    timeout: float,
) -> int:
    checked_at = datetime.now().astimezone()
    rows = collect_station_rows(station_ids, timeout)
    persist_rows(database_url, excel_path, rows, checked_at)
    print(
        f"{checked_at.isoformat(timespec='seconds')}: recorded {len(rows)} connectors",
        flush=True,
    )
    return len(rows)


def collect_station_rows(station_ids: list[int], timeout: float) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    failures: list[str] = []
    for station_id in station_ids:
        try:
            payload = fetch_station(station_id, timeout)
            station_rows = extract_connectors(payload, station_id)
            if not station_rows:
                raise ValueError("response contains no connectors array")
            rows.extend(station_rows)
            print(f"Station {station_id}: found {len(station_rows)} connectors", flush=True)
        except (OSError, ValueError) as error:
            failures.append(f"{station_id}: {error}")
            print(f"Station {station_id} failed: {error}", file=sys.stderr, flush=True)

    if failures and not rows:
        raise RuntimeError("; ".join(failures))
    return rows


def capture_stations(
    station_ids: list[int],
    database_url: str,
    excel_path: Path | None,
    timeout: float,
    interval: float,
    duration: float,
) -> int:
    deadline = time.monotonic() + duration
    samples: list[tuple[datetime, list[dict[str, Any]]]] = []

    while time.monotonic() < deadline:
        cycle_started = time.monotonic()
        checked_at = datetime.now().astimezone()
        try:
            rows = collect_station_rows(station_ids, timeout)
            samples.append((checked_at, rows))
        except RuntimeError as error:
            print(f"Capture check failed: {error}", file=sys.stderr, flush=True)

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(remaining, max(0.0, interval - (time.monotonic() - cycle_started))))

    row_count = sum(len(rows) for _, rows in samples)
    print(f"Writing {row_count} buffered rows...", flush=True)
    for checked_at, rows in samples:
        persist_rows(database_url, excel_path, rows, checked_at)
    print(f"Capture complete: {len(samples)} samples, {row_count} rows", flush=True)
    return row_count


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stations",
        nargs="+",
        type=int,
        default=list(DEFAULT_STATIONS),
        help="Station IDs to monitor",
    )
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL", "sqlite:///data/availability.db"),
        help="PostgreSQL URL or sqlite:///path (defaults to DATABASE_URL)",
    )
    parser.add_argument("--excel", type=Path, help="Optional secondary Excel output")
    parser.add_argument("--interval", type=float, default=60.0, help="Seconds between checks")
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--once", action="store_true", help="Check once and exit")
    parser.add_argument(
        "--duration",
        type=float,
        help="Capture for this many seconds, buffer samples, then exit",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.interval <= 0:
        print("Monitor failed: --interval must be greater than zero", file=sys.stderr)
        return 2
    if args.duration is not None:
        if args.duration <= 0:
            print("Monitor failed: --duration must be greater than zero", file=sys.stderr)
            return 2
        capture_stations(
            args.stations,
            args.database_url,
            args.excel,
            args.timeout,
            args.interval,
            args.duration,
        )
        return 0

    while True:
        started_at = time.monotonic()
        try:
            check_stations(args.stations, args.database_url, args.excel, args.timeout)
        except (OSError, ValueError, RuntimeError) as error:
            print(f"Monitor check failed: {error}", file=sys.stderr)
            if args.once:
                return 1

        if args.once:
            return 0
        sleep_seconds = max(0.0, args.interval - (time.monotonic() - started_at))
        next_check = datetime.fromtimestamp(time.time() + sleep_seconds).astimezone()
        print(
            f"Waiting {sleep_seconds:.0f} seconds; next check at "
            f"{next_check.isoformat(timespec='seconds')}",
            flush=True,
        )
        time.sleep(sleep_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
