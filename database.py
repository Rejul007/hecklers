"""
database.py - SQLite database operations for the AI Onboarding Engine.

Tables:
  - sessions: stores all candidate/session data including resume, JD, skill gaps, questionnaire, pathway
  - skill_tests: stores per-skill verification test data and results
"""

import sqlite3
import json
import uuid
from datetime import datetime
from typing import Optional, Dict, Any


# Path to the SQLite database file
DB_PATH = "onboarding.db"


def get_connection() -> sqlite3.Connection:
    """Return a new SQLite connection with row_factory for dict-like access."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize the database by creating tables if they don't exist."""
    conn = get_connection()
    try:
        cursor = conn.cursor()

        # Sessions table: one row per candidate onboarding session
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                candidate_name TEXT,
                resume_text TEXT,
                resume_data TEXT,          -- JSON: parsed resume fields
                jd_text TEXT,
                jd_data TEXT,              -- JSON: parsed JD fields
                skill_gaps TEXT,           -- JSON: gap analysis result
                questionnaire_questions TEXT,  -- JSON: list of MCQ dicts
                questionnaire_state TEXT,      -- JSON: {answers: {q_id: letter}, current_index}
                proficiency_scores TEXT,       -- JSON: {skill: {level, score, details}}
                pathway TEXT,              -- JSON: full learning pathway
                status TEXT DEFAULT 'setup'    -- setup/analyzing/questionnaire/results/pathway/testing
            )
        """)

        # Skill tests table: one row per skill per session
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS skill_tests (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                skill_name TEXT NOT NULL,
                status TEXT DEFAULT 'not_started',  -- not_started/learning/testing/completed/needs_revision
                questions TEXT,            -- JSON: list of 8 MCQ dicts
                answers TEXT,              -- JSON: {q_id: letter}
                score REAL DEFAULT 0,
                passed INTEGER DEFAULT 0,  -- 0 or 1
                attempts INTEGER DEFAULT 0,
                feedback TEXT,             -- text feedback from Claude
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            )
        """)

        conn.commit()
        print("Database initialized successfully.")
    finally:
        conn.close()


def create_session() -> str:
    """Create a new session and return its ID."""
    session_id = str(uuid.uuid4())
    created_at = datetime.utcnow().isoformat()

    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO sessions (id, created_at, status) VALUES (?, ?, ?)",
            (session_id, created_at, "setup")
        )
        conn.commit()
    finally:
        conn.close()

    return session_id


def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve a session by ID.
    All JSON string fields are automatically parsed into Python objects.
    Returns None if not found.
    """
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()

        if row is None:
            return None

        # Convert sqlite3.Row to a regular dict
        session = dict(row)

        # Parse JSON fields
        json_fields = [
            "resume_data", "jd_data", "skill_gaps",
            "questionnaire_questions", "questionnaire_state",
            "proficiency_scores", "pathway"
        ]
        for field in json_fields:
            if session.get(field):
                try:
                    session[field] = json.loads(session[field])
                except (json.JSONDecodeError, TypeError):
                    session[field] = None

        return session
    finally:
        conn.close()


def update_session(session_id: str, updates: Dict[str, Any]):
    """
    Update one or more fields of a session.
    Complex Python objects are automatically serialized to JSON strings.
    """
    if not updates:
        return

    # Fields that should be stored as JSON
    json_fields = {
        "resume_data", "jd_data", "skill_gaps",
        "questionnaire_questions", "questionnaire_state",
        "proficiency_scores", "pathway"
    }

    # Serialize complex fields to JSON
    serialized = {}
    for key, value in updates.items():
        if key in json_fields and value is not None and not isinstance(value, str):
            serialized[key] = json.dumps(value)
        else:
            serialized[key] = value

    # Build dynamic SET clause
    set_clause = ", ".join(f"{key} = ?" for key in serialized.keys())
    values = list(serialized.values()) + [session_id]

    conn = get_connection()
    try:
        conn.execute(
            f"UPDATE sessions SET {set_clause} WHERE id = ?",
            values
        )
        conn.commit()
    finally:
        conn.close()


def get_skill_test(session_id: str, skill_name: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve a skill test record for a given session + skill.
    Returns None if not found.
    """
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM skill_tests WHERE session_id = ? AND skill_name = ?",
            (session_id, skill_name)
        ).fetchone()

        if row is None:
            return None

        test = dict(row)
        # Parse JSON fields
        for field in ["questions", "answers"]:
            if test.get(field):
                try:
                    test[field] = json.loads(test[field])
                except (json.JSONDecodeError, TypeError):
                    test[field] = None

        test["passed"] = bool(test.get("passed", 0))
        return test
    finally:
        conn.close()


def upsert_skill_test(session_id: str, skill_name: str, updates: Dict[str, Any]):
    """
    Insert or update a skill test record.
    Creates the record if it doesn't exist, updates it otherwise.
    """
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT id FROM skill_tests WHERE session_id = ? AND skill_name = ?",
            (session_id, skill_name)
        ).fetchone()

        # Serialize JSON fields
        serialized = {}
        for key, value in updates.items():
            if key in {"questions", "answers"} and value is not None and not isinstance(value, str):
                serialized[key] = json.dumps(value)
            else:
                serialized[key] = value

        if existing:
            # Update existing record
            set_clause = ", ".join(f"{key} = ?" for key in serialized.keys())
            values = list(serialized.values()) + [existing["id"]]
            conn.execute(
                f"UPDATE skill_tests SET {set_clause} WHERE id = ?",
                values
            )
        else:
            # Insert new record
            test_id = str(uuid.uuid4())
            fields = ["id", "session_id", "skill_name"] + list(serialized.keys())
            placeholders = ", ".join("?" for _ in fields)
            values = [test_id, session_id, skill_name] + list(serialized.values())
            conn.execute(
                f"INSERT INTO skill_tests ({', '.join(fields)}) VALUES ({placeholders})",
                values
            )

        conn.commit()
    finally:
        conn.close()


def get_all_skill_tests(session_id: str) -> list:
    """
    Retrieve all skill test records for a given session.
    Returns a list of dicts with JSON fields parsed.
    """
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM skill_tests WHERE session_id = ? ORDER BY skill_name",
            (session_id,)
        ).fetchall()

        tests = []
        for row in rows:
            test = dict(row)
            for field in ["questions", "answers"]:
                if test.get(field):
                    try:
                        test[field] = json.loads(test[field])
                    except (json.JSONDecodeError, TypeError):
                        test[field] = None
            test["passed"] = bool(test.get("passed", 0))
            tests.append(test)

        return tests
    finally:
        conn.close()
