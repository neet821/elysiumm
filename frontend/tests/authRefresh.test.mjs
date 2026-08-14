import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const configSource = readFileSync(
  new URL("../src/config.js", import.meta.url),
  "utf8",
);
const authContextSource = readFileSync(
  new URL("../src/contexts/AuthContext.jsx", import.meta.url),
  "utf8",
);
const requestSource = readFileSync(
  new URL("../src/utils/request.js", import.meta.url),
  "utf8",
);

assert.match(
  configSource,
  /USER_INFO:\s*`\$\{API_BASE_URL\}\/api\/auth\/me`/,
  "user info should use the unified auth/me endpoint",
);
assert.match(
  configSource,
  /REFRESH:\s*`\$\{API_BASE_URL\}\/api\/auth\/refresh`/,
  "config should expose the refresh endpoint",
);
assert.match(
  configSource,
  /LOGOUT:\s*`\$\{API_BASE_URL\}\/api\/auth\/logout`/,
  "config should expose the logout endpoint",
);

assert.match(
  authContextSource,
  /localStorage\.getItem\("refresh_token"\)/,
  "auth context should restore refresh token from storage",
);
assert.match(
  authContextSource,
  /localStorage\.setItem\("refresh_token",\s*refresh_token\)/,
  "auth context should store refresh token after login",
);
assert.match(
  authContextSource,
  /apiClient\.post\(API_ENDPOINTS\.LOGOUT/,
  "logout should notify the backend endpoint",
);

assert.match(
  requestSource,
  /API_ENDPOINTS\.REFRESH/,
  "request client should call the refresh endpoint on expired access token",
);
assert.match(
  requestSource,
  /originalRequest\._retry/,
  "request client should retry each failed request at most once",
);
assert.match(
  requestSource,
  /refresh_token/,
  "request client should send the refresh token when renewing access",
);
