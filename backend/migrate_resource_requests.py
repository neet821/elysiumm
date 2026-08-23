"""
Migration script to add is_anonymous and is_private columns to resource_requests table
"""
from sqlalchemy import create_engine, text
from database import engine
import sys

def migrate():
    """Add missing columns to resource_requests table"""

    print("Starting migration...")

    try:
        with engine.connect() as conn:
            # Check if columns already exist
            result = conn.execute(text("PRAGMA table_info(resource_requests)"))
            columns = [row[1] for row in result]

            print(f"Current columns: {columns}")

            # Add is_anonymous column if not exists
            if 'is_anonymous' not in columns:
                print("Adding is_anonymous column...")
                conn.execute(text(
                    "ALTER TABLE resource_requests ADD COLUMN is_anonymous BOOLEAN DEFAULT 0"
                ))
                conn.commit()
                print("✓ Added is_anonymous column")
            else:
                print("✓ is_anonymous column already exists")

            # Add is_private column if not exists
            if 'is_private' not in columns:
                print("Adding is_private column...")
                conn.execute(text(
                    "ALTER TABLE resource_requests ADD COLUMN is_private BOOLEAN DEFAULT 0"
                ))
                conn.commit()
                print("✓ Added is_private column")
            else:
                print("✓ is_private column already exists")

        print("\n✅ Migration completed successfully!")
        return True

    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = migrate()
    sys.exit(0 if success else 1)
