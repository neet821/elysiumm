import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const source = readFileSync(
  new URL("../src/pages/BackupPage.jsx", import.meta.url),
  "utf8",
);
const frpSource = readFileSync(
  new URL("../src/pages/FrpAdminPage.jsx", import.meta.url),
  "utf8",
);

assert.doesNotMatch(
  source,
  /file\.file_path/,
  "backup page must not consume a private server filesystem path",
);
assert.match(
  source,
  /file\.filename/,
  "backup page should use the safe filename returned by the API",
);
assert.doesNotMatch(
  frpSource,
  /\/home\/frp|status\?\.paths/,
  "FRP administration must not render private server filesystem paths",
);

console.log("backup page privacy checks passed");
