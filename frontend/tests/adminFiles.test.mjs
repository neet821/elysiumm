import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";

const source = readFileSync(
  new URL("../src/pages/AdminFilesPage.jsx", import.meta.url),
  "utf8",
);
const config = readFileSync(new URL("../src/config.js", import.meta.url), "utf8");
const routes = readFileSync(new URL("../src/routes.jsx", import.meta.url), "utf8");
const styles = readFileSync(new URL("../src/index.css", import.meta.url), "utf8");

for (const label of ["手动文件", "同步设备", "同步文件", "同步动态"]) {
  assert.match(source, new RegExp(label), `Files workspace must include ${label}`);
}
for (const endpoint of [
  "ADMIN_FILES",
  "ADMIN_FILE_UPLOAD",
  "ADMIN_FILE_DOWNLOAD",
  "ADMIN_FILE",
  "PUBLIC_SYNC_DEVICES",
  "PUBLIC_SYNC_ROTATE",
  "PUBLIC_SYNC_REVOKE",
]) {
  assert.match(config, new RegExp(`${endpoint}:`), `config must expose ${endpoint}`);
}
assert.match(source, /responseType:\s*['"]blob['"]/, "downloads must use an authenticated Blob response");
assert.match(source, /URL\.createObjectURL/, "download must create a local Blob URL");
assert.match(source, /URL\.revokeObjectURL/, "download must release the Blob URL");
assert.match(source, /file\.id/, "manual file actions must use stable database ids");
assert.match(source, /device_token/, "one-time device responses must be handled explicitly");
assert.match(source, /navigator\.clipboard\.writeText/, "one-time secrets need an explicit copy action");
assert.doesNotMatch(source, /device_token_hash|storage_path/, "private sync fields must never be consumed");
assert.doesNotMatch(source, /file\.url|uploads\/admin_files/, "manual files must never use a public static URL");
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
  routes,
  /path="\/tools\/public-sync"[\s\S]*?<LegacyRedirect to="\/account\/admin\/files" preserveSearch hash=\{true\} \/>/,
  "the old sync route must preserve query and hash through the unified Files page",
);
assert.match(styles, /\.admin-files__device-grid/, "the Files workspace needs a responsive device grid");
assert.match(
  styles,
  /@media \(max-width: 680px\)[\s\S]*?\.admin-files__intro[\s\S]*?flex-direction: column/,
  "the Files workspace must collapse safely on narrow screens",
);

console.log("unified admin Files checks passed");
