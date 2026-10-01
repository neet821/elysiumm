import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";

const source = readFileSync(
  new URL("../src/pages/AdminFilesPage.jsx", import.meta.url),
  "utf8",
);
const privateFiles = readFileSync(
  new URL("../src/features/admin-files/useAdminPrivateFiles.js", import.meta.url),
  "utf8",
);
const syncBrowser = readFileSync(
  new URL("../src/features/admin-files/useAdminSyncBrowser.js", import.meta.url),
  "utf8",
);
const transferWorkspace = readFileSync(
  new URL("../src/features/admin-files/useAdminTransferWorkspace.js", import.meta.url),
  "utf8",
);
const adminNote = readFileSync(
  new URL("../src/features/admin-files/useAdminNote.js", import.meta.url),
  "utf8",
);
const workspace = readFileSync(
  new URL("../src/features/admin-files/useAdminFilesWorkspace.js", import.meta.url),
  "utf8",
);
const utilities = readFileSync(
  new URL("../src/features/admin-files/adminFilesUtils.js", import.meta.url),
  "utf8",
);
const featureLogic = [privateFiles, syncBrowser, transferWorkspace, workspace, adminNote].join("\n");
const publicTransferPage = readFileSync(
  new URL("../src/pages/TransferPage.jsx", import.meta.url),
  "utf8",
);
const config = readFileSync(new URL("../src/config.js", import.meta.url), "utf8");
const routes = readFileSync(new URL("../src/routes.jsx", import.meta.url), "utf8");
const styles = readFileSync(new URL("../src/index.css", import.meta.url), "utf8");
const featureStylesPath = new URL("../src/features/admin-files/adminFiles.css", import.meta.url);
const featureStyles = existsSync(featureStylesPath)
  ? readFileSync(featureStylesPath, "utf8")
  : "";

for (const label of ["文件同步", "文件中转"]) {
  assert.match(source, new RegExp(label), `Files workspace must include ${label}`);
}
for (const removed of ["READ ONLY / FRP", "ANONYMOUS / 5 MIN IDLE", "实时浏览并下载", "在此页直接上传"]) {
  assert.doesNotMatch(source, new RegExp(removed), `Files workspace must remove ${removed}`);
}
assert.doesNotMatch(source, /管理控制台 \/ 文件/, "Files workspace must remove the duplicate breadcrumb");
assert.doesNotMatch(source, /<h2>文件<\/h2>/, "Files workspace must remove the duplicate page heading");
for (const endpoint of ["ADMIN_FILE_SYNC_STATUS", "ADMIN_FILE_SYNC_BROWSE", "ADMIN_FILE_SYNC_DOWNLOAD", "ADMIN_FILES", "ADMIN_FILE", "ADMIN_TUS", "ADMIN_TUS_RESULT", "ADMIN_TRANSFER_CURRENT_LINK", "ADMIN_TRANSFER_FILES", "ADMIN_TRANSFER_FILE", "ADMIN_TRANSFER_NOTE"]) {
  assert.match(config, new RegExp(`${endpoint}:`), `config must expose ${endpoint}`);
}
assert.match(featureLogic, /responseType:\s*['"]blob['"]/, "downloads must use an authenticated Blob response");
assert.match(utilities, /URL\.createObjectURL/, "download must create a local Blob URL");
assert.match(utilities, /URL\.revokeObjectURL/, "download must release the Blob URL");
assert.match(transferWorkspace, /tusUploads\.addFiles/, "admin uploads must use the resumable upload queue");
assert.match(source, /选择管理员文件上传/, "admin file workspace must expose its private upload picker");
assert.match(source, /选择文件上传/, "admin transfer workspace must expose its upload picker");
assert.match(source, /AdminTusUploadQueue/, "admin uploads must expose the queue and its retry controls");
assert.doesNotMatch(featureLogic, /apiClient\.put\(\s*`\/api\/transfers/, "web uploads must not send transfer files with a one-shot PUT");
assert.match(source, /multiple/, "admin workspaces must allow selecting multiple files");
assert.match(source, /管理员纯文本/, "admin workspace must expose the administrator-only text area");
assert.match(adminNote, /ADMIN_TRANSFER_NOTE/, "admin workspace must persist the administrator-only text");
assert.match(source, /复制文本/, "admin workspace must expose a text copy action");
assert.match(workspace, /setInterval\(loadAdminNote, 5000\)/, "admin workspace must refresh the persistent text");
assert.match(source, /transfer\?\.ready/, "the current share link must be rendered");
assert.match(config, /TRANSFER_PUBLIC_BASE_URL/, "transfer links must use the fixed public host");
assert.match(routes, /path="\/:token"/, "the fixed transfer host must accept token links at its root");
assert.match(routes, /isTransferHost\(\) \? withAuth\(<AdminFilesPage \/>/, "the fixed transfer host must render the unified admin Files workspace");
assert.doesNotMatch(routes, /TransferInboxPage/, "the fixed transfer host must not render a separate transfer page");
assert.equal(
  existsSync(new URL("../src/pages/TransferInboxPage.jsx", import.meta.url)),
  false,
  "the unmounted legacy inbox and its alternate upload path must be retired",
);
assert.match(routes, /path="\/transfer\/:token"\s+element=\{<TransferPage \/>\}/, "public transfer links must keep their read/download page");
assert.doesNotMatch(publicTransferPage, /type="file"|apiClient\.put/, "public transfer links must not expose an upload path");
for (const retiredSelector of [
  ".transfer-inbox-page",
  ".transfer-inbox-upload",
  ".transfer-upload-progress",
  ".transfer-page__upload",
]) {
  assert.equal(
    styles.includes(retiredSelector),
    false,
    `global styles must not retain retired selector ${retiredSelector}`,
  );
}
assert.match(
  source,
  /import ['"]\.\.\/features\/admin-files\/adminFiles\.css['"];?/,
  "the lazy admin Files page must own its feature stylesheet",
);
assert.match(
  featureStyles,
  /\.admin-file-cards\s*\{[^}]*grid-template-columns:\s*repeat\(2,\s*minmax\(0,\s*1fr\)\)/,
  "the Files feature stylesheet needs a responsive card grid",
);
assert.doesNotMatch(
  styles,
  /\.admin-file-cards\s*\{/,
  "admin Files feature styles must not be loaded from the global stylesheet",
);
assert.doesNotMatch(source, /创建中转链接<\/button>/, "the admin workspace must not create an empty link first");
assert.match(source, /item\.path/, "sync file actions must use stable paths");
assert.match(syncBrowser, /filter\(\(item\) => !item\.path\.endsWith\('\/'\)\)/, "sync workspace must list files only");
assert.match(source, /transferFiles\.map/, "transfer files must render one row per file");
assert.match(transferWorkspace, /ADMIN_TRANSFER_FILE\(item\.id\)/, "admins must be able to delete individual transfer files");
assert.doesNotMatch(source, /中转 #|过期：/, "admin transfer rows must not expose session summaries");
assert.doesNotMatch(featureLogic, /device_token_hash|storage_path/, "private sync fields must never be consumed");
assert.doesNotMatch(featureLogic, /file\.url|uploads\/admin_files/, "manual files must never use a public static URL");
assert.match(source, /退出登录/, "the fixed transfer host must expose a logout action for shared devices");
assert.doesNotMatch(
  source,
  /<\/?main\b/,
  "the embedded Files workspace must not create a second main landmark",
);
assert.equal(
  existsSync(new URL("../src/pages/PublicSyncPage.jsx", import.meta.url)),
  false,
  "the separate Public Sync page must be removed",
);
assert.doesNotMatch(routes, /import PublicSyncPage/, "routes must not import the removed sync page");
assert.match(
  featureStyles,
  /\.admin-file-cards\s*\{[^}]*grid-template-columns:\s*repeat\(2,\s*minmax\(0,\s*1fr\)\)/,
  "the Files workspace needs a responsive card grid",
);
assert.match(
  featureStyles,
  /@media\s*\(max-width:\s*760px\)[\s\S]*?\.admin-file-cards\s*\{\s*grid-template-columns:\s*1fr\s*;\s*\}/,
  "the Files workspace must collapse safely on narrow screens",
);

console.log("unified admin Files checks passed");
