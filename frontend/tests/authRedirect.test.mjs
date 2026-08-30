import assert from "node:assert/strict";

import {
  buildLoginRedirect,
  consumeAuthRedirect,
  AUTH_REDIRECT_STORAGE_KEY,
  getSafeRedirectTarget,
  getPostLoginTarget,
  saveAuthRedirect,
  shouldBypassAuthRedirect,
} from "../src/utils/authRedirect.js";

const protectedRoomLocation = {
  pathname: "/tools/sync-room/42",
  search: "?from=invite",
  hash: "#chat",
};

assert.equal(
  buildLoginRedirect(protectedRoomLocation),
  "/login?redirect=%2Ftools%2Fsync-room%2F42%3Ffrom%3Dinvite%23chat",
  "login redirect should preserve the full protected page URL",
);

assert.equal(
  getSafeRedirectTarget("/admin/agent-console"),
  "/admin/agent-console",
  "internal absolute paths are safe redirect targets",
);

assert.equal(
  getSafeRedirectTarget("https://evil.example/phish"),
  "/",
  "external redirect targets should fall back to home",
);

assert.equal(
  getSafeRedirectTarget("//evil.example/phish"),
  "/",
  "protocol-relative redirect targets should fall back to home",
);

assert.equal(getPostLoginTarget('/rooms/watch/42', { role: 'user' }), '/rooms/watch/42');
assert.equal(getPostLoginTarget('/rooms/music', { role: 'user' }), '/rooms/music');
assert.equal(getPostLoginTarget('/live', { role: 'user' }), '/live');
assert.equal(getPostLoginTarget('/admin/files', { role: 'user' }), '/admin/files');
assert.equal(getPostLoginTarget('/admin/homepage', { role: 'user' }), '/');
assert.equal(getPostLoginTarget('/account', { role: 'user' }), '/');
assert.equal(getPostLoginTarget('/admin/homepage', { role: 'admin' }), '/');

assert.equal(
  shouldBypassAuthRedirect("/login"),
  true,
  "login page should not redirect to itself",
);

assert.equal(
  shouldBypassAuthRedirect("/register"),
  true,
  "register page should not redirect to login",
);

const storage = new Map();
const mockStorage = {
  getItem: (key) => storage.get(key) || null,
  removeItem: (key) => storage.delete(key),
  setItem: (key, value) => storage.set(key, value),
};

saveAuthRedirect(protectedRoomLocation, mockStorage);
assert.equal(
  storage.get(AUTH_REDIRECT_STORAGE_KEY),
  "/tools/sync-room/42?from=invite#chat",
  "auth redirect should be saved for later login",
);

assert.equal(
  consumeAuthRedirect(mockStorage),
  "/tools/sync-room/42?from=invite#chat",
  "saved auth redirect should be returned once",
);

assert.equal(
  storage.has(AUTH_REDIRECT_STORAGE_KEY),
  false,
  "saved auth redirect should be cleared after use",
);
