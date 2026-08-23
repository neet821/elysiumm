"""Dialect-aware SQL used only by legacy bootstrap migrations."""


def post_slug_backfill_sql(dialect_name: str) -> str:
    if str(dialect_name).lower() in {"mysql", "mariadb"}:
        expression = "CONCAT('post-', id)"
    else:
        expression = "'post-' || id"
    return (
        f"UPDATE posts SET slug = {expression} "
        "WHERE slug IS NULL OR TRIM(slug) = ''"
    )
