# Elysium 文件上传

## 谁可以上传

网页上传只允许已登录管理员。公开中转链接仍可查看文件和下载，但不能创建或续传上传。FastAPI 会在每次创建、查询进度、续传、取消和确认结果时检查管理员身份与上传所有权；浏览器只访问同源 `/api/admin/tus/`，不会拿到 tusd 地址或服务器路径。

## 一次上传经过哪里

```text
管理员文件页（Uppy）
        ↓ Bearer 身份，每次请求重新验证
FastAPI /api/admin/tus/（权限、配额、文件校验、最终入库）
        ↓ 仅 127.0.0.1
tusd（断点与临时分片）
        ↓ 完整后校验并原子移动
管理员私有文件 / 管理员创建的中转文件
```

暂存数据放在 release 目录之外的共享私有目录，所以切换后端版本或重启进程不会清除未完成上传。上传预约单独保存在 `TusUploadReservation`，过期任务由后台清理；最终文件仍使用原有文件表、私有下载地址和 Range 下载处理。

## 代码入口

| 职责 | 位置 |
| --- | --- |
| 上传权限、tus HTTP 转发 | `backend/routers/admin_tus.py` |
| 配额、校验、原子发布与过期清理 | `backend/tus_upload_service.py`、`backend/tus_cleanup_task.py` |
| 管理员页面和续传队列 | `frontend/src/pages/AdminFilesPage.jsx`、`frontend/src/features/admin-files/` |
| loopback 服务和公网请求转发 | `deployment/systemd/elysiumm-tusd.service`、`deployment/nginx/elysiumm.conf` |
| 本地预览 | `scripts/local-preview.sh` |

本地预览会尝试启动固定版本 tusd。没有可用二进制时会明确提示可续传上传不可用，但继续启动网站的其他功能；后端接口同时返回 503，页面上的上传按钮禁用。可用 `TUSD_BINARY` 指定已校验的可执行文件。生产 backend 服务显式启用上传，并由 CD 将同一 CI run 校验过的 tusd 放入对应不可变发布版本。

## 第三方组件与许可

| 组件 | 固定版本 | 用途 | 许可 |
| --- | --- | --- | --- |
| `@uppy/core` | `6.0.0`（`frontend/package-lock.json`） | 管理员续传队列 | MIT（包元数据） |
| `@uppy/tus` | `6.0.0`（`frontend/package-lock.json`） | tus 客户端 | MIT（包元数据） |
| `tus/tusd` | `v2.10.0`，Linux x86_64 | 本机续传暂存服务 | MIT；许可证随运行二进制保存于 `backend/third_party_licenses/tusd/LICENSE.txt` |

tusd 发布压缩包 SHA-256 固定为 `68bd62773a494c621b2b806dfaa03a57aac44044c9757440a17765283fbd7a68`，二进制 SHA-256 固定为 `b01e54afb2449738cee6114aeca65b1b339b3e56bcbe301ce7b7bcd3db37537c`。更新版本时同步修改安装脚本、CI/CD、运行配置和此表，并重新审查许可。
