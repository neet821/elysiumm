import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";

const source = readFileSync(
  new URL("../src/pages/AdminFilesPage.jsx", import.meta.url),
  "utf8",
);
const config = readFileSync(new URL("../src/config.js", import.meta.url), "utf8");
const routes = readFileSync(new URL("../src/routes.jsx", import.meta.url), "utf8");
const styles = readFileSync(new URL("../src/index.css", import.meta.url), "utf8");

for (const label of ["文件同步", "文件中转"]) {
  assert.match(source, new RegExp(label), `Files workspace must include ${label}`);
}
for (const removed of ["READ ONLY / FRP", "ANONYMOUS / 5 MIN IDLE", "实时浏览并下载", "在此页直接上传"]) {
  assert.doesNotMatch(source, new RegExp(removed), `Files workspace must remove ${removed}`);
}
for (const endpoint of ["ADMIN_FILE_SYNC_STATUS", "ADMIN_FILE_SYNC_BROWSE", "ADMIN_FILE_SYNC_DOWNLOAD", "ADMIN_TRANSFERS", "ADMIN_TRANSFER_CURRENT_LINK", "ADMIN_TRANSFER", "ADMIN_TRANSFER_FILES"]) {
  assert.match(config, new RegExp(`${endpoint}:`), `config must expose ${endpoint}`);
}
assert.match(source, /responseType:\s*['"]blob['"]/, "downloads must use an authenticated Blob response");
assert.match(source, /URL\.createObjectURL/, "download must create a local Blob URL");
assert.match(source, /URL\.revokeObjectURL/, "download must release the Blob URL");
assert.match(source, /apiClient\.put\(/, "admin transfer uploads must use the transfer API");
assert.match(source, /type=["']file["']/, "admin transfer workspace must expose a file picker");
assert.match(source, /transfer\?\.ready/, "the share link must wait for a successful upload");
assert.match(config, /TRANSFER_PUBLIC_BASE_URL/, "transfer links must use the fixed public host");
assert.match(routes, /path="\/:token"/, "the fixed transfer host must accept token links at its root");
assert.match(routes, /isTransferHost\(\) \? withAuth\(<AdminFilesPage \/>/, "the fixed transfer host must render the unified admin Files workspace");
assert.doesNotMatch(routes, /TransferInboxPage/, "the fixed transfer host must not render a separate transfer page");
assert.doesNotMatch(source, /创建中转链接<\/button>/, "the admin workspace must not create an empty link first");
assert.match(source, /item\.path/, "sync file actions must use stable paths");
assert.match(source, /filter\(\(item\) => !item\.path\.endsWith\('\/'\)\)/, "sync workspace must list files only");
assert.match(source, /item\.files\?\.map/, "transfer rows must render concrete file names");
assert.doesNotMatch(source, /device_token_hash|storage_path/, "private sync fields must never be consumed");
assert.doesNotMatch(source, /file\.url|uploads\/admin_files/, "manual files must never use a public static URL");
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
assert.match(styles, /\.admin-file-cards\s*\{[^}]*grid-template-columns:repeat\(2,minmax\(0,1fr\)\)/, "the Files workspace needs a responsive card grid");
assert.match(
  styles,
  /@media\(max-width:760px\)[\s\S]*?\.admin-file-cards\{grid-template-columns:1fr\}/,
  "the Files workspace must collapse safely on narrow screens",
);

console.log("unified admin Files checks passed");
