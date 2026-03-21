#!/usr/bin/env python3
"""
remove_manager.py - CLI script to remove a manager from the whitelist.

Usage:
    python remove_manager.py <email>

Example:
    python remove_manager.py manager@company.com
"""

import sys
import sqlite3
import database

def main():
    database.init_db()

    if len(sys.argv) != 2:
        print("Usage: python remove_manager.py <email>")
        sys.exit(1)

    email = sys.argv[1].lower().strip()

    conn = database.get_connection()
    try:
        cursor = conn.execute("DELETE FROM managers WHERE email = ?", (email,))
        conn.commit()
        if cursor.rowcount > 0:
            # Also invalidate any active sessions for this manager
            conn.execute(
                "DELETE FROM manager_sessions WHERE manager_email = ?", (email,)
            )
            conn.commit()
            print(f"Manager removed: {email}")
        else:
            print(f"No manager found with email: {email}")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
