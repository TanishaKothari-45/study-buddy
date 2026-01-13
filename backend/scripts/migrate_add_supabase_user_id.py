"""
Migration: Add supabase_user_id column to users table

Run this script to add the new supabase_user_id column to your existing database.
This is a one-time migration for the Supabase Auth integration.

Usage:
    cd backend
    source venv/bin/activate
    python scripts/migrate_add_supabase_user_id.py
"""

import sqlite3
from pathlib import Path

# Database path
DB_PATH = Path(__file__).parent.parent / "data" / "databases" / "sql_app.db"


def migrate():
    if not DB_PATH.exists():
        print(f"Database not found at {DB_PATH}")
        print("No migration needed - database will be created on first run.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Check if column already exists
    cursor.execute("PRAGMA table_info(users)")
    columns = [col[1] for col in cursor.fetchall()]

    if "supabase_user_id" in columns:
        print("✅ Column 'supabase_user_id' already exists. No migration needed.")
        conn.close()
        return

    print("Adding 'supabase_user_id' column to users table...")

    try:
        # Add the new column (without UNIQUE constraint initially for SQLite compatibility)
        cursor.execute("""
            ALTER TABLE users 
            ADD COLUMN supabase_user_id TEXT
        """)
        
        conn.commit()
        print("✅ Migration successful! 'supabase_user_id' column added.")
        
        # Create unique index for faster lookups and to enforce uniqueness
        cursor.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS ix_users_supabase_user_id 
            ON users (supabase_user_id) WHERE supabase_user_id IS NOT NULL
        """)
        conn.commit()
        print("✅ Unique index created for supabase_user_id.")
        
    except sqlite3.Error as e:
        print(f"❌ Migration failed: {e}")
        conn.rollback()
    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
