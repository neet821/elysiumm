import assert from "node:assert/strict";
import fs from "node:fs";

const html = fs.readFileSync(new URL("../index.html", import.meta.url), "utf8");
const app = fs.readFileSync(new URL("../src/App.jsx", import.meta.url), "utf8");
const themeHook = fs.readFileSync(new URL("../src/theme/useTheme.js", import.meta.url), "utf8");
const css = fs.readFileSync(new URL("../src/index.css", import.meta.url), "utf8");

assert.match(html, /localStorage\.getItem\('theme'\)/, "theme must load before React mounts");
assert.match(html, /prefers-color-scheme/, "theme must fall back to system preference");
assert.match(app, /useTheme/, "App must use the shared theme controller");
assert.match(themeHook, /localStorage\.setItem\('theme'/, "theme changes must persist");
assert.match(themeHook, /startViewTransition/, "theme switch must prefer View Transitions");
assert.match(themeHook, /getBoundingClientRect/, "theme origin must come from the trigger");
assert.match(css, /::view-transition-new\(root\)/, "theme reveal must animate the new root snapshot");
assert.match(css, /--theme-origin-x/, "theme reveal must use the trigger origin");
for (const token of ["--radius-card", "--shadow-card", "--transition-spring", "--surface-color"]) {
  assert.ok(css.includes(token), `missing global design token ${token}`);
}
assert.match(css, /\.home-side-panel\s*\{[\s\S]*?position:\s*absolute/, "desktop sidebar must not reserve a permanent grid column");

console.log("theme system checks passed");
