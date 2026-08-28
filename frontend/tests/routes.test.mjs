import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const routesSource = readFileSync(
  new URL("../src/routes.jsx", import.meta.url),
  "utf8",
);

assert.match(
  routesSource,
  /const NotFoundPage = lazy\(\(\) => import\("\.\/pages\/NotFoundPage"\)\);/,
  "routes should load the not-found page on demand",
);

assert.doesNotMatch(routesSource, /GameRoomPage|GameDetailPage|GamesPage|RoomsGamesPage|path=['"]\/(?:games|rooms\/games)/, "game routes and pages must be removed");
for (const path of ["/archive", "/collection", "/books", "/tools", "/music"]) {
  assert.match(routesSource, new RegExp(`path="${path}"`), `stable public route ${path} should exist`);
}
assert.match(routesSource, /const AdminBooksPage = lazy\(\(\) => import\("\.\/pages\/AdminBooksPage"\)\);/, "routes should load the Books content editor on demand");
assert.match(routesSource, /path="\/account\/admin"[\s\S]*?withAuth\(<AdminShell \/>, true\)/, "the canonical administrator shell must stay behind the administrator route guard");
for (const path of ["content/homepage", "content/collection", "content/books", "content/photos", "users", "rooms", "files", "services", "services/frp", "backups", "security"]) {
  assert.match(routesSource, new RegExp(`path="${path}"`), `canonical administrator route ${path} should exist`);
}
for (const [legacyPath, destination] of [
  ["/account/admin/homepage", "/account/admin/content/homepage"],
  ["/admin/users", "/account/admin/users"],
  ["/admin/photos", "/account/admin/content/photos"],
  ["/admin/files", "/account/admin/files"],
  ["/admin/agent-console", "/account/admin/services"],
  ["/tools/backup", "/account/admin/backups"],
  ["/tools/frp", "/account/admin/services/frp"],
  ["/tools/public-sync", "/account/admin/files"],
]) {
  assert.match(routesSource, new RegExp(`path="${legacyPath.replaceAll('/', '\\/')}"[\\s\\S]*?LegacyRedirect to="${destination.replaceAll('/', '\\/')}" preserveSearch`), `legacy administrator route ${legacyPath} should preserve search while redirecting to ${destination}`);
}
assert.match(routesSource, /path="rooms" element=\{<SharedRoomListRedirect \/>\}/, "the old administrator room path should open the shared room list");
assert.match(routesSource, /path="\/posts" element=\{<LegacyRedirect to="\/archive\?type=writing" \/>\}/, "legacy posts should redirect to Archive writings");
assert.match(routesSource, /path="\/photos" element=\{<LegacyRedirect to="\/archive\?type=photo" \/>\}/, "legacy photos should redirect to Archive photos");
assert.match(routesSource, /path="\/messages" element=\{<LegacyRedirect to="\/" hash="messages" \/>\}/, "legacy messages should redirect to the home message anchor");
assert.match(routesSource, /const ToolsPage = lazy\(\(\) => import\("\.\/pages\/ToolsPage"\)\);/, "routes should load the tools dashboard on demand");
assert.match(routesSource, /path="\/tools" element=\{withUserProps\(ToolsPage\)\}/, "the public tools shell should render in place");
assert.match(routesSource, /path="\/tools\/links"[\s\S]*?<LegacyRedirect to="\/account\/admin\/content\/collection" preserveSearch hash=\{true\} \/>/, "legacy links should preserve query and hash while redirecting to administrator Collection management");
assert.match(routesSource, /path="\/account\/collection"[\s\S]*?withAuth\(<LegacyRedirect to="\/account\/admin\/content\/collection" preserveSearch hash=\{true\} \/>, true\)/, "legacy private Collection must require an administrator before redirecting");
assert.match(routesSource, /path="content\/collection" element=\{<PrivateCollectionPage \/>\}/, "private Collection should live in the canonical administrator content area");
assert.match(routesSource, /path="\/collection"[\s\S]*?withAuth\(withUserProps\(CollectionPage\)\)/, "collection should require login");
assert.match(routesSource, /path="\/books"[\s\S]*?withAuth\(<BooksPage \/>, true\)/, "books should require an administrator");
assert.match(routesSource, /path="\/music"[\s\S]*?withAuth\(<MusicLobbyPage \/>\)/, "music should open the authenticated room lobby");
assert.doesNotMatch(routesSource, /path="\/music"[^\n]*StandalonePlayerPage/, "the local demo must not occupy the music route");
assert.match(
  routesSource,
  /<Route path="\*" element=\{withUserProps\(NotFoundPage\)\} \/>/,
  "unknown routes should render a not-found page instead of silently returning home",
);
assert.doesNotMatch(routesSource, /temporary-review/, "temporary review pages should be removed from production routes");
