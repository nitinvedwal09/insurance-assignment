import json
import sqlite3
import time
import uuid
from contextlib import closing
from pathlib import Path
from typing import Optional

DATA_DIR = Path(__file__).parent.parent / "data"
DB_PATH = DATA_DIR / "app.db"
IMAGES_DIR = DATA_DIR / "images"


def _connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS transactions (
            transaction_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            query TEXT NOT NULL,
            image_path TEXT,
            damage_result TEXT,
            ocr_result TEXT,
            policy_result TEXT,
            escalation_result TEXT,
            llm_response TEXT,
            latencies_ms TEXT,
            config_used TEXT,
            bandit_choices TEXT,
            feedback_score INTEGER,
            feedback_at TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS bandit_arms (
            context_key TEXT PRIMARY KEY,
            pulls INTEGER NOT NULL DEFAULT 0,
            total_reward REAL NOT NULL DEFAULT 0
        )
        """
    )
    return conn


def new_transaction_id() -> str:
    return uuid.uuid4().hex


def save_image(transaction_id: str, image_bytes: bytes, suffix: str = ".jpg") -> str:
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    path = IMAGES_DIR / f"{transaction_id}{suffix}"
    path.write_bytes(image_bytes)
    return f"images/{path.name}"


def create_transaction(
    transaction_id: str,
    query: str,
    image_path: Optional[str],
    damage_result: Optional[dict],
    ocr_result: Optional[dict],
    policy_result: Optional[dict],
    escalation_result: Optional[dict],
    llm_response: str,
    latencies_ms: dict,
    config_used: dict,
    bandit_choices: list[dict],
) -> None:
    with closing(_connect()) as conn:
        conn.execute(
            """
            INSERT INTO transactions
                (transaction_id, created_at, query, image_path, damage_result,
                 ocr_result, policy_result, escalation_result, llm_response,
                 latencies_ms, config_used, bandit_choices)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                transaction_id,
                time.strftime("%Y-%m-%dT%H:%M:%S"),
                query,
                image_path,
                json.dumps(damage_result) if damage_result is not None else None,
                json.dumps(ocr_result) if ocr_result is not None else None,
                json.dumps(policy_result) if policy_result is not None else None,
                json.dumps(escalation_result) if escalation_result is not None else None,
                llm_response,
                json.dumps(latencies_ms),
                json.dumps(config_used),
                json.dumps(bandit_choices),
            ),
        )
        conn.commit()


def get_transaction(transaction_id: str) -> Optional[dict]:
    with closing(_connect()) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM transactions WHERE transaction_id = ?", (transaction_id,)
        ).fetchone()
        return dict(row) if row else None


def save_feedback(transaction_id: str, score: int) -> bool:
    with closing(_connect()) as conn:
        cursor = conn.execute(
            "UPDATE transactions SET feedback_score = ?, feedback_at = ? WHERE transaction_id = ?",
            (score, time.strftime("%Y-%m-%dT%H:%M:%S"), transaction_id),
        )
        conn.commit()
        return cursor.rowcount > 0


def get_arm_stats(context_key: str) -> tuple[int, float]:
    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT pulls, total_reward FROM bandit_arms WHERE context_key = ?", (context_key,)
        ).fetchone()
        return (row[0], row[1]) if row else (0, 0.0)


def update_arm(context_key: str, reward: float) -> None:
    with closing(_connect()) as conn:
        conn.execute(
            """
            INSERT INTO bandit_arms (context_key, pulls, total_reward) VALUES (?, 1, ?)
            ON CONFLICT(context_key) DO UPDATE SET
                pulls = pulls + 1,
                total_reward = total_reward + excluded.total_reward
            """,
            (context_key, reward),
        )
        conn.commit()


def all_arm_stats() -> list[dict]:
    with closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT context_key, pulls, total_reward FROM bandit_arms ORDER BY context_key"
        ).fetchall()
        return [
            {
                "context_key": r[0],
                "pulls": r[1],
                "total_reward": r[2],
                "avg_reward": r[2] / r[1] if r[1] else 0.0,
            }
            for r in rows
        ]
