"""SQLite persistence layer for KEOZ — zero config, always on."""
import sqlite3
import aiosqlite
import json
import time
from pathlib import Path
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager

DB_DIR = Path(".keoz")
DB_PATH = DB_DIR / "keoz.db"
DB_DIR.mkdir(parents=True, exist_ok=True)

SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_atoms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    atom_id TEXT,
    atom_type TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    policy_hash TEXT NOT NULL,
    payload TEXT NOT NULL,           -- JSON
    prev_hash TEXT,                  -- hash-chained
    atom_hash TEXT,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_atoms_policy_version ON audit_atoms(policy_version);
CREATE INDEX IF NOT EXISTS idx_atoms_atom_type ON audit_atoms(atom_type);

CREATE TABLE IF NOT EXISTS approvals (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL,            -- pending, approved, rejected, countered
    request TEXT NOT NULL,           -- JSON BuyerRequest
    proposed_deal TEXT NOT NULL,     -- JSON NegotiationResult
    trigger_reasons TEXT NOT NULL,   -- JSON list
    policy_version TEXT NOT NULL,
    created_at REAL NOT NULL,
    decided_by TEXT,
    decided_at REAL,
    decision_notes TEXT,
    counter_terms TEXT               -- JSON
);
CREATE INDEX IF NOT EXISTS idx_approvals_status ON approvals(status);

CREATE TABLE IF NOT EXISTS policy_versions (
    version TEXT PRIMARY KEY,
    yaml_hash TEXT NOT NULL,
    yaml_content TEXT NOT NULL,
    bounds_hash TEXT NOT NULL,
    compiled_at REAL NOT NULL,
    compiled_by TEXT
);

CREATE TABLE IF NOT EXISTS merchant_configs (
    merchant_id TEXT PRIMARY KEY,
    policy_yaml TEXT NOT NULL,
    active_version TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
"""

def init_db_sync(db_path: Path = DB_PATH):
    """Synchronous database initialization."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(SCHEMA)
        conn.commit()

async def init_db(db_path: Path = DB_PATH):
    """Asynchronous database initialization."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(db_path) as db:
        await db.executescript(SCHEMA)
        await db.commit()

@asynccontextmanager
async def get_db(db_path: Path = DB_PATH):
    """Async database connection context manager."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        yield db

def get_db_sync(db_path: Path = DB_PATH):
    """Sync database connection."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

# Auto-initialize database synchronously on module load
init_db_sync()
