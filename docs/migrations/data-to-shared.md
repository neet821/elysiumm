# `/data` 到 `shared` 迁移追踪

## 目的

`/srv/services/elysium/data -> /srv/services/elysium/shared` 是兼容期链接。它只在所有运行时、脚本和文档完成迁移后退役，不因某一次 release 成功而自动删除。

## 当前约定

- 新代码使用 `/srv/services/elysium/shared/...`。
- 兼容链接暂时保留，供尚未迁移的旧路径读取。
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
- [ ] running processes no longer access `/srv/services/elysium/data/`
- [ ] two successful releases without legacy-path access
- [ ] baseline restore does not require the compatibility link

## 每次发布检查

1. 扫描仓库、systemd、Nginx 和维护脚本中的旧路径。
2. 检查运行进程打开的文件和环境变量。
3. 将新增引用登记到对应清单项，不得静默扩大兼容期。
4. 保留检查输出和 deployment ID，直到两个成功 release 完成。

## 删除前置条件

只有清单全部完成、两个成功 release 均未访问旧路径、baseline 能独立恢复，并完成人工审查后，才可以提出删除 `data -> shared` 的独立变更。
