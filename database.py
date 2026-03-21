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

        # Add firebase_uid and user_email to sessions if not present (migration)
        try:
            cursor.execute("ALTER TABLE sessions ADD COLUMN firebase_uid TEXT")
        except sqlite3.OperationalError:
            pass
        try:
            cursor.execute("ALTER TABLE sessions ADD COLUMN user_email TEXT")
        except sqlite3.OperationalError:
            pass

        # Managers whitelist table — just emails, auth handled by Firebase
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS managers (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                created_at TEXT NOT NULL
            )
        """)

        # Migration: drop password_hash column if the table was created with old schema
        cols = [row[1] for row in cursor.execute("PRAGMA table_info(managers)").fetchall()]
        if "password_hash" in cols:
            cursor.execute("ALTER TABLE managers RENAME TO managers_old")
            cursor.execute("""
                CREATE TABLE managers (
                    id TEXT PRIMARY KEY,
                    email TEXT UNIQUE NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            cursor.execute(
                "INSERT INTO managers (id, email, created_at) SELECT id, email, created_at FROM managers_old"
            )
            cursor.execute("DROP TABLE managers_old")

        # Manager sessions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS manager_sessions (
                token TEXT PRIMARY KEY,
                manager_id TEXT NOT NULL,
                manager_email TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (manager_id) REFERENCES managers(id)
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


import secrets


def add_manager(email: str) -> bool:
    """Add a manager email to the whitelist. Returns True if added, False if already exists."""
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT id FROM managers WHERE email = ?", (email.lower().strip(),)
        ).fetchone()
        if existing:
            return False
        manager_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO managers (id, email, created_at) VALUES (?, ?, ?)",
            (manager_id, email.lower().strip(), datetime.utcnow().isoformat())
        )
        conn.commit()
        return True
    finally:
        conn.close()


def list_managers() -> list:
    """Return all manager emails in the whitelist."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, email, created_at FROM managers ORDER BY created_at DESC"
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def remove_manager(email: str) -> bool:
    """Remove a manager from the whitelist. Returns True if removed, False if not found."""
    conn = get_connection()
    try:
        cursor = conn.execute(
            "DELETE FROM managers WHERE email = ?", (email.lower().strip(),)
        )
        if cursor.rowcount > 0:
            conn.execute(
                "DELETE FROM manager_sessions WHERE manager_email = ?",
                (email.lower().strip(),)
            )
            conn.commit()
            return True
        conn.commit()
        return False
    finally:
        conn.close()


def verify_manager_email(email: str) -> Optional[Dict[str, Any]]:
    """Check if an email is in the manager whitelist. Returns manager dict or None."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM managers WHERE email = ?", (email.lower().strip(),)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def create_manager_session(manager_id: str, manager_email: str) -> str:
    """Create a manager session token and return it."""
    token = secrets.token_hex(32)
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO manager_sessions (token, manager_id, manager_email, created_at) VALUES (?, ?, ?, ?)",
            (token, manager_id, manager_email, datetime.utcnow().isoformat())
        )
        conn.commit()
    finally:
        conn.close()
    return token


def verify_manager_session(token: str) -> Optional[Dict[str, Any]]:
    """Verify a manager session token. Returns session dict or None."""
    if not token:
        return None
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM manager_sessions WHERE token = ?", (token,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def delete_manager_session(token: str):
    """Delete a manager session (logout)."""
    conn = get_connection()
    try:
        conn.execute("DELETE FROM manager_sessions WHERE token = ?", (token,))
        conn.commit()
    finally:
        conn.close()


def update_session_user(session_id: str, firebase_uid: str, user_email: str):
    """Link a Firebase user to a session."""
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE sessions SET firebase_uid = ?, user_email = ? WHERE id = ?",
            (firebase_uid, user_email, session_id)
        )
        conn.commit()
    finally:
        conn.close()


def delete_session(session_id: str) -> bool:
    """Delete a session and all its skill tests. Returns True if deleted."""
    conn = get_connection()
    try:
        conn.execute("DELETE FROM skill_tests WHERE session_id = ?", (session_id,))
        cursor = conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def get_all_employees() -> list:
    """
    Return a summary of all employees who have reached the pathway stage.
    Joins sessions with skill_tests to compute progress per employee.
    """
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT id, candidate_name, user_email, firebase_uid,
                   proficiency_scores, skill_gaps, pathway, status, created_at
            FROM sessions
            WHERE status = 'pathway' OR pathway IS NOT NULL
            ORDER BY created_at DESC
        """).fetchall()

        employees = []
        for row in rows:
            session = dict(row)

            # Parse JSON fields
            for field in ["proficiency_scores", "skill_gaps", "pathway"]:
                if session.get(field):
                    try:
                        session[field] = json.loads(session[field])
                    except Exception:
                        session[field] = None

            # Skill test stats
            tests = conn.execute(
                "SELECT skill_name, status, score, passed FROM skill_tests WHERE session_id = ?",
                (session["id"],)
            ).fetchall()

            total_skills = len(tests)
            completed = sum(1 for t in tests if t["passed"])
            in_progress = sum(1 for t in tests if t["status"] in ("learning", "testing", "needs_revision") and not t["passed"])

            # Overall assessment score: average of proficiency_scores
            prof = session.get("proficiency_scores") or {}
            scores = [v["score"] for v in prof.values() if isinstance(v, dict) and "score" in v]
            assessment_score = round(sum(scores) / len(scores)) if scores else None

            # Skill gaps summary
            gaps_raw = session.get("skill_gaps") or {}
            skill_gaps = gaps_raw.get("skill_gaps", []) if isinstance(gaps_raw, dict) else []

            # Per-skill topic details from the learning pathway
            skill_details = {}
            pathway = session.get("pathway") or {}
            for skill_entry in pathway.get("skills", []):
                sname = skill_entry.get("skill_name", "")
                if not sname:
                    continue
                skill_details[sname] = {
                    "topics": [step.get("focus", "") for step in skill_entry.get("learning_steps", []) if step.get("focus")],
                    "prerequisites": skill_entry.get("prerequisites", []),
                    "practice_project": skill_entry.get("practice_project", ""),
                    "reasoning": skill_entry.get("reasoning", ""),
                }

            # Display name: candidate_name > user_email > session id
            display_name = session.get("candidate_name") or session.get("user_email") or session["id"][:8]

            employees.append({
                "session_id": session["id"],
                "display_name": display_name,
                "user_email": session.get("user_email") or "",
                "assessment_score": assessment_score,
                "total_skills": total_skills,
                "completed_skills": completed,
                "in_progress_skills": in_progress,
                "skill_gaps": skill_gaps,
                "skill_details": skill_details,
                "status": session.get("status"),
                "created_at": session.get("created_at"),
            })

        return employees
    finally:
        conn.close()
