# Elysium migration release record

本文件只记录迁移相关的当前边界；综合清理验收见
[docs/release-checklist.md](../release-checklist.md)。基线为
`archive/pre-core-cleanup-2026-08-30`，本次没有生产迁移。

## Current chain

空库验证已从 `0001_legacy_baseline` 升级到
`0023_remove_game_platform`，包含 `0009_phase10_books_files_admin` 和
`0010_repair_legacy_gaps`；autogenerate 无新操作，历史迁移保持不可变。

## Preserved schema boundary

Books 的 `/api/books`、后台 Books 服务/ORM，以及 `books`、`book_lists`、
`book_list_items` 表仍被媒体首页、媒体服务和后台/迁移测试消费，故本次不退役、
不删除表，也不新增 Alembic 忽略项。Archive HTTP router 的退役是代码层变更，
不改变 `0018_public_archive_types` 或任何生产数据。

## Verification

```bash
backend/.venv/bin/python backend/run_migrations.py
backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_*_unittest.py' -v
git diff --check
```

生产升级仍须先运行迁移前备份和 [deployment](../deployment.md) 中的显式回滚流程。
