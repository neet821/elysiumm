# Baseline 外置迁移记录

## 目标

将不可变生产 baseline 从服务运行目录移到独立备份目录，避免历史恢复栈
占用 `/srv/services/elysium` 的运行边界：

```text
/srv/services/elysium/baseline/current-production-20260913-0034
  -> /srv/backups/elysium/baseline/current-production-20260913-0034
```

baseline 本身必须保持完整、自包含、只读，不能改写其中的 `BASELINE.json`
或 `SHA256SUMS`。

## 当前状态

- [x] GitHub 已保存完整代码快照 `archive/pre-slimming-20260913-199c59f`
- [x] `release-preflight.sh` 支持独立的 `--baseline-root`
- [ ] 复制到备份目录并校验 `SHA256SUMS`
- [ ] 在服务停止前原子搬迁 baseline
- [ ] 使用外置 baseline 完成 preflight 和恢复配置路径检查
- [ ] 保留失败回滚目录，直到外置 baseline 验证完成
- [ ] 后续再单独更新/启用 CI/CD 的 baseline 参数

## 约束

- 不删除 baseline，不修改数据库，不改变 `backend-current`、`frontend-current`。
- 移动前后必须比较文件数量、总大小和 `SHA256SUMS`；校验失败立即停止。
- 服务器服务目录不得保留指向备份目录的兼容链接，避免运行时重新依赖 baseline。
- GitHub CI/CD 本次不参与迁移；自动部署保持关闭。
