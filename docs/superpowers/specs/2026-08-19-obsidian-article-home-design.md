# Obsidian Article Home Design

## Goal

将 `elysiumm.top` 首页重做为一个极简的 Obsidian Markdown 文章入口：从服务器上的 `网站内容/文章` 目录读取文章，解析 YAML Frontmatter 生成首页预览，点击后阅读正文。

## Scope

- 只实现文章首页、文章正文阅读、文章图片/相对链接读取和健康检查。
- 不保留现有 Elysium 前端首页的视觉和交互。
- 不新增登录、后台编辑、搜索、评论、标签筛选或其他产品功能。
- 部署前保留现有站点文件和 Nginx 配置备份，验证失败可回滚。

## Product behavior

1. 首页列出文章，默认按 Frontmatter 中的 `date` 倒序；缺少日期时按文件修改时间倒序。
2. 每篇文章展示标题、日期/分类等已有 Frontmatter 信息、封面和预览文字。
3. 兼容文章开头标准 `---` YAML Frontmatter；同时兼容标题后紧接 YAML 区块的现有文件格式。
4. 封面字段兼容 `cover`、`image`、`thumbnail`；预览字段兼容 `description`、`excerpt`、`summary`，都不存在时从正文首段生成。
5. 点击文章进入稳定的 `/article/<slug>` 地址；正文由 Markdown 转换为安全 HTML，图片和相对链接以该文章文件所在目录为基准。
6. 页面使用浏览器式排版：白底、黑字、系统字体、细边框、清晰链接；无渐变、阴影、装饰插画、3D、动画和复杂导航。
7. 移动端保持可读，文章列表和正文宽度随视口收缩，不出现横向滚动。

## Architecture

- Node.js 单进程应用负责静态页面、文章 API、Markdown 解析和安全的媒体文件服务。
- 前端使用原生浏览器 API 与单一 stylesheet，避免引入框架和不必要依赖。
- 服务端只允许读取配置的文章根目录及其子目录；所有路径在解析后必须仍位于根目录内，防止路径穿越。
- API：`GET /api/articles` 返回文章索引，`GET /api/articles/:slug` 返回正文，`GET /media/:slug/*path` 返回文章附件，`GET /api/health` 返回服务状态。
- 文章根目录通过环境变量配置，部署时定位并显式写入服务器环境文件；不把 Obsidian 内容复制进 Git 仓库。

## Deployment

- 本地先完成单元测试、构建和真实浏览器验收。
- 服务器创建独立应用目录和 systemd 服务，Nginx 将 `elysiumm.top` 的首页/API/媒体请求代理到新应用。
- 保留现有 `/home/elysiumm`、`/var/www/elysiumm` 和 Nginx 配置的可恢复备份。
- 发布后检查 HTTPS 首页、文章列表、至少一篇正文、封面/媒体、健康接口和 Nginx 配置；任何一项失败都不宣称完成。

## Verification

- 解析测试：标准 Frontmatter、标题后 YAML、日期排序、缺失摘要回退、封面相对路径。
- 安全测试：路径穿越、无效 slug、未授权读取文章根目录外文件。
- 应用测试：文章索引、文章正文、媒体文件和健康接口。
- 构建测试：生产构建无错误。
- 浏览器测试：桌面和窄屏首页、点击文章、返回首页、正文图片和无控制台错误。
- 公网测试：`https://elysiumm.top/`、`/api/health`、真实文章地址及媒体响应。
