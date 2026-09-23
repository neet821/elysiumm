"""Metadata fingerprint prevents a package-only model refactor changing tables."""

import hashlib
import json
import sys
import unittest
from pathlib import Path

from sqlalchemy import PrimaryKeyConstraint

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import models  # noqa: E402


class ModelMetadataContractTest(unittest.TestCase):
    def test_existing_table_metadata_is_unchanged(self):
        metadata = models.Base.metadata
        payload = []
        for table in sorted(metadata.tables.values(), key=lambda item: item.name):
            columns = [
                {
                    "name": column.name,
                    "type": str(column.type),
                    "nullable": column.nullable,
                    "primary_key": column.primary_key,
                    "unique": column.unique,
                    "index": column.index,
                    "foreign_keys": sorted(
                        f"{foreign_key.target_fullname}:{foreign_key.ondelete}:{foreign_key.onupdate}"
                        for foreign_key in column.foreign_keys
                    ),
                    "default": bool(column.default),
                    "server_default": bool(column.server_default),
                }
                for column in table.columns
            ]
            constraints = []
            for constraint in table.constraints:
                if isinstance(constraint, PrimaryKeyConstraint):
                    continue
                constraints.append(
                    {
                        "kind": type(constraint).__name__,
                        "name": constraint.name,
                        "columns": sorted(column.name for column in constraint.columns),
                        "sql": str(getattr(constraint, "sqltext", "")),
                    }
                )
            indexes = sorted(
                (index.name, sorted(column.name for column in index.columns), index.unique)
                for index in table.indexes
            )
            payload.append(
                {
                    "table": table.name,
                    "columns": columns,
                    "constraints": sorted(
                        constraints,
                        key=lambda item: (
                            item["kind"],
                            item["name"] or "",
                            item["columns"],
                            item["sql"],
                        ),
                    ),
                    "indexes": indexes,
                }
            )

        signature = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        self.assertEqual(len(payload), 58)
        self.assertEqual(
            signature,
            "e8ca705e9599120e4cca05c157794075e7a8d4602eef8558604888accf98fdd5",
        )


if __name__ == "__main__":
    unittest.main()
