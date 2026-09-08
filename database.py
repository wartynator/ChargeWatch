"""Database storage for connector availability snapshots."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Any


CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS connector_availability (
    id {id_type},
    station_id BIGINT NOT NULL,
    connector_id TEXT NOT NULL,
    evse_id TEXT NOT NULL,
    state TEXT NOT NULL,
    checked_at TEXT NOT NULL,
    name TEXT NOT NULL,
    address TEXT NOT NULL
)
"""


def _values(rows: list[dict[str, Any]], checked_at: datetime) -> list[tuple[Any, ...]]:
    timestamp = checked_at.isoformat(timespec="seconds")
    return [
        (
            row["station_id"],
            str(row["connector_id"]),
            str(row["evse_id"]),
            row["state"],
            timestamp,
            row["name"],
            row["address"],
        )
        for row in rows
    ]


def save_snapshot(
    database_url: str, rows: list[dict[str, Any]], checked_at: datetime
) -> None:
    if database_url.startswith(("postgres://", "postgresql://")):
        _save_postgres(database_url, rows, checked_at)
        return
    _save_sqlite(database_url, rows, checked_at)


def _save_sqlite(
    database_url: str, rows: list[dict[str, Any]], checked_at: datetime
) -> None:
    prefix = "sqlite:///"
    database_path = database_url[len(prefix) :] if database_url.startswith(prefix) else database_url
    Path(database_path).parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(database_path)) as connection:
        connection.execute(CREATE_TABLE_SQL.format(id_type="INTEGER PRIMARY KEY AUTOINCREMENT"))
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_availability_checked_at "
            "ON connector_availability (checked_at)"
        )
        connection.executemany(
            """
            INSERT INTO connector_availability
                (station_id, connector_id, evse_id, state, checked_at, name, address)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            _values(rows, checked_at),
        )
        connection.commit()


def _save_postgres(
    database_url: str, rows: list[dict[str, Any]], checked_at: datetime
) -> None:
    import psycopg

    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(CREATE_TABLE_SQL.format(id_type="BIGSERIAL PRIMARY KEY"))
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_availability_checked_at "
                "ON connector_availability (checked_at)"
            )
            cursor.executemany(
                """
                INSERT INTO connector_availability
                    (station_id, connector_id, evse_id, state, checked_at, name, address)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                _values(rows, checked_at),
            )