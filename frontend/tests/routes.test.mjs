import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const routesSource = readFileSync(
  new URL("../src/routes.jsx", import.meta.url),
  "utf8",
);

assert.match(
  routesSource,
  /const NotFoundPage = lazy\(\(\) => import\(['"]\.\/pages\/NotFoundPage['"]\)\)/,
  "routes should load the not-found page on demand",
);

assert.doesNotMatch(routesSource, /GameRoomPage|GameDetailPage|GamesPage|RoomsGamesPage|path=['"]\/(?:games|rooms\/games)/, "game routes and pages must be removed");
for (const path of ["/content/*", "/rooms/music", "/rooms/watch", "/music", "/live"]) {
  assert.match(routesSource, new RegExp(`path="${path.replace('*', '\\*')}"`), `stable public route ${path} should exist`);
}
assert.doesNotMatch(routesSource, /AdminBooksPage/, "removed Books editor must not remain in routes");
assert.match(routesSource, /path="\/admin\/\*" element=\{withAuth\(<AdminShell \/>, true\)\}/, "the administrator shell must stay behind the administrator route guard");
for (const path of ["homepage", "users", "rooms", "files", "music", "services"]) {
  assert.match(routesSource, new RegExp(`path="${path}"`), `canonical administrator route ${path} should exist`);
}
assert.match(routesSource, /path="\/admin\/\*" element=\{withAuth\(<AdminShell \/>, true\)\}/, "administrator shell should own admin routes");
assert.match(routesSource, /path="rooms" element=\{<SharedRoomListRedirect \/>\}/, "the old administrator room path should open the shared room list");
assert.doesNotMatch(routesSource, /path="\/music"[^\n]*StandalonePlayerPage/, "the local demo must not occupy the music route");
assert.match(
  routesSource,
  /<Route path="\*" element=\{withUserProps\(NotFoundPage\)\} \/>/,
  "unknown routes should render a not-found page instead of silently returning home",
);
assert.doesNotMatch(routesSource, /temporary-review/, "temporary review pages should be removed from production routes");
