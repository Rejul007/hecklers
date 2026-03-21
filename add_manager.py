#!/usr/bin/env python3
"""
add_manager.py - CLI script to add a manager email to the whitelist.

Usage:
    python add_manager.py <email>

Example:
    python add_manager.py manager@company.com
"""

import sys
import database

def main():
    database.init_db()

    if len(sys.argv) != 2:
        print("Usage: python add_manager.py <email>")
        sys.exit(1)

    email = sys.argv[1]

    success = database.add_manager(email)
    if success:
        print(f"Manager added successfully: {email}")
    else:
        print(f"Manager already exists: {email}")

if __name__ == "__main__":
    main()
