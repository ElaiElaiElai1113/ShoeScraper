from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Generator

import pytest

from sneakers.db import init_db

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def db_conn() -> Generator[sqlite3.Connection, None, None]:
    """In-memory SQLite database with schema initialized."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    yield conn
    conn.close()


def load_fixture(retailer: str, filename: str) -> str:
    """Load a saved HTML fixture file."""
    path = FIXTURES_DIR / retailer / filename
    if not path.exists():
        raise FileNotFoundError(f"Fixture not found: {path}")
    return path.read_text()
