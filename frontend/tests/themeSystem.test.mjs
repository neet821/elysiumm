import assert from "node:assert/strict";
import fs from "node:fs";

const html = fs.readFileSync(new URL("../index.html", import.meta.url), "utf8");
const app = fs.readFileSync(new URL("../src/App.jsx", import.meta.url), "utf8");
const css = fs.readFileSync(new URL("../src/index.css", import.meta.url), "utf8");

assert.doesNotMatch(html, /localStorage\.getItem\(['"]theme['"]\)/, "formal pages must not load a user theme");
assert.doesNotMatch(html, /prefers-color-scheme/, "formal pages must not follow a system theme");
assert.doesNotMatch(app, /useTheme/, "formal shell must not mount the theme controller");
assert.match(css, /--surface-page:\s*#fff/i, "formal pages must use a white surface");
assert.match(css, /--text-primary:\s*#111/i, "formal pages must use black text");
assert.match(css, /--shadow-card:\s*none/i, "formal pages must not use card shadows");
assert.match(css, /--radius-card:\s*0/i, "formal pages must not use rounded cards");

console.log("plain service theme checks passed");
