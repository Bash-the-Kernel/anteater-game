#!/usr/bin/env python3
"""Add is_admin column to existing players table."""

from auth import get_db_connection

def add_admin_column():
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("ALTER TABLE players ADD COLUMN is_admin BOOLEAN DEFAULT FALSE")
        conn.commit()
        print("Successfully added is_admin column")
    except Exception as e:
        if "Duplicate column name" in str(e):
            print("Column already exists")
        else:
            print(f"Error: {e}")
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    add_admin_column()