# 手动维护 Obsidian 记录 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 移除 Elysium 资料自动查询与封面下载链路，让四类记录完全由 Obsidian 本地模板手动维护，并修复书籍新建入口。

**Architecture:** 服务器保留网站已有的手工媒体展示/编辑接口，但删除资料提供商、封面代理和 Obsidian 专用接口；Obsidian 使用本地模板和一个不联网的标题确认脚本，Bases 新建按钮只在快速创建命令确实存在时拦截，否则交回原生行为。退役代码以不含凭据的归档目录提交到当前 GitHub 分支。

**Tech Stack:** FastAPI/Python, Obsidian Templater/QuickAdd, Elysium Record Review Sync plugin, unittest/Node tests.

**Spec:** 用户 2026-08-24 关于放弃数据库、手动维护记录、归档代码及修复书籍新建按钮的请求。

## Global Constraints

- 先备份本地 Vault、服务器代码和当前未提交改动，再删除 live code。
- 不删除用户现有记录、冲突版本或与本次范围无关的服务。
- Obsidian 新建流程不访问网络、不读取服务器凭据、不下载外部封面。
- 服务器删除资料查询/封面接口并撤销对应专用凭据；历史代码仅放在归档目录。
- 在真实 Obsidian 命令清单和后端测试上验证，不能只检查静态文件。

---

### Task 1: 归档与服务器接口下线

**Files:**
- Create: `archive/retired-obsidian-metadata/README.md` and copies of retired provider/client files.
- Modify: `backend/routers/media.py`, `backend/config.py`, `backend/.env.example`, related live tests.
- Delete from live tree: `backend/media_metadata_service.py`, `backend/media_matching.py` after archiving.
- Test: `backend/tests/test_manual_media_routes_unittest.py`.

- [ ] 记录退役原因、原始提交、备份位置和“服务器不再接受查询/封面请求”。
- [ ] 先新增失败测试，断言四个资料/封面路径不再注册，手工媒体接口仍可用。
- [ ] 移除 provider imports、Obsidian token 校验、资料搜索和封面代理；删除 provider 配置项和旧测试的 live imports。
- [ ] 运行新测试和媒体相关测试，确认无网络资料请求。

### Task 2: Obsidian 本地手动记录流程

**Files:**
- Modify: `资源库/Scripts/elysiumMetadata.js`, four media templates, `.obsidian/plugins/elysium-record-review-sync/main.js`.
- Modify: `资源库/数据库/记录.base` only as needed to keep four fixed folders and safe native fallback.
- Create: `tests/obsidian-local-record-flow.test.mjs`.

- [ ] 新增失败测试：脚本不含服务器地址/凭据读取，四类模板只生成 `source: manual`，未命名书籍能得到标题和正确目录。
- [ ] 把脚本改为本地标题确认和空字段模板，不重命名循环、不联网。
- [ ] 为插件注册四个本地快速新建命令；按钮只有在命令存在且执行成功时才阻止默认事件。
- [ ] 让书籍入口缺少 QuickAdd 时直接回退 Obsidian 原生新建，并给出明确提示。
- [ ] 在真实命令列表中检查 `qa-book`，通过命令执行和文件创建验证书籍按钮。

### Task 3: 远端清理与验收

**Files:**
- Modify remote `/home/elysiumm/app/backend` and `/etc/elysiumm/backend.env` only after backups.
- Create/update archive files on the current Git branch.

- [ ] 部署已验证的 live server changes，删除远端 live provider files，移除已撤销的 metadata env keys。
- [ ] 重启服务并检查健康接口、旧资料路径 404、网站手工媒体读取正常。
- [ ] 清理本地 Obsidian metadata SecretStorage 中的专用凭据，不回显 token。
- [ ] 提交归档和 live changes；记录备份校验和验收结果。
