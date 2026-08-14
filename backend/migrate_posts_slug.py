"""
Migration to ensure all posts have unique, non-empty slugs
"""
from database import engine
from sqlalchemy import text
import sys


def migrate():
    print("Starting posts slug migration...")
    try:
        with engine.begin() as conn:
            # 1) Replace NULL or empty slug with post-{id}
            print("  - Updating null/empty slugs to post-<id> values")
            conn.execute(text("UPDATE posts SET slug = 'post-' || id WHERE slug IS NULL OR TRIM(slug) = ''"))

            # 2) Fix duplicate slugs by appending the id
            print("  - Ensuring slug uniqueness: fixing any duplicates")
            # Find duplicates via SQL and update later ones
            duplicates = conn.execute(text("SELECT slug, COUNT(*) as cnt FROM posts GROUP BY slug HAVING cnt > 1")).fetchall()
            for row in duplicates:
                slug = row[0]
                # Fetch posts with this slug ordered by id
                posts = conn.execute(text("SELECT id FROM posts WHERE slug = :slug ORDER BY id"), {"slug": slug}).fetchall()
                # Skip the first (keep as-is), append -<id> for subsequent ones
                keep = True
                for p in posts:
                    pid = p[0]
                    if keep:
                        keep = False
                        continue
                    new_slug = f"{slug}-{pid}"
                    conn.execute(text("UPDATE posts SET slug = :new_slug WHERE id = :id"), {"new_slug": new_slug, "id": pid})
        print("Migration completed successfully.")
        return True
    except Exception as e:
        print(f"Migration failed: {e}")
        return False


if __name__ == '__main__':
    ok = migrate()
    sys.exit(0 if ok else 1)
