# `/data` 到 `shared` 迁移追踪

## 目的

历史上的 `/srv/services/elysium/data -> /srv/services/elysium/shared` 是兼容期链接。本次目录整理后生产配置统一使用 `/srv/services/elysium/shared/`，旧数据副本移动到独立备份目录保留，且不再创建该链接。

## 当前约定

- 新代码使用 `/srv/services/elysium/shared/...`。
- 不再为新 release 创建兼容链接；旧数据副本只作为备份保留。
- release、baseline 和 deployment transaction 必须记录是否访问旧路径。
- 任何删除链接的操作都必须是单独的受控变更，并保留恢复命令。

## 退役清单

- [ ] backend env
- [ ] provider state
- [ ] backup scripts
- [ ] health guard
- [ ] systemd
- [ ] Nginx
- [ ] maintenance scripts
- [ ] CI/CD scripts
- [ ] operations documentation
- [x] running processes no longer access `/srv/services/elysium/data/`
- [ ] two successful releases without legacy-path access
- [ ] baseline restore does not require the compatibility link

## 每次发布检查

1. 扫描仓库、systemd、Nginx 和维护脚本中的旧路径。
2. 检查运行进程打开的文件和环境变量。
3. 将新增引用登记到对应清单项，不得静默扩大兼容期。
4. 保留检查输出和 deployment ID，直到两个成功 release 完成。

## 删除前置条件

删除兼容链接后的恢复验证仍需保留；不得重新创建 `data -> shared`。
