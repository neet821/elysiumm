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

assert.match(routesSource, /path="\/games\/rooms\/:roomId"/, "game room route should exist");
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
  ["/admin/rooms", "/account/admin/rooms"],
  ["/admin/photos", "/account/admin/content/photos"],
  ["/admin/files", "/account/admin/files"],
  ["/admin/agent-console", "/account/admin/services"],
  ["/tools/backup", "/account/admin/backups"],
  ["/tools/frp", "/account/admin/services/frp"],
  ["/tools/public-sync", "/account/admin/files"],
]) {
  assert.match(routesSource, new RegExp(`path="${legacyPath.replaceAll('/', '\\/')}"[\\s\\S]*?LegacyRedirect to="${destination.replaceAll('/', '\\/')}" preserveSearch`), `legacy administrator route ${legacyPath} should preserve search while redirecting to ${destination}`);
}
assert.match(routesSource, /path="\/posts" element=\{<LegacyRedirect to="\/archive\?type=writing" \/>\}/, "legacy posts should redirect to Archive writings");
assert.match(routesSource, /path="\/photos" element=\{<LegacyRedirect to="\/archive\?type=photo" \/>\}/, "legacy photos should redirect to Archive photos");
assert.match(routesSource, /path="\/messages" element=\{<LegacyRedirect to="\/" hash="messages" \/>\}/, "legacy messages should redirect to the home message anchor");
assert.match(routesSource, /const ToolsPage = lazy\(\(\) => import\("\.\/pages\/ToolsPage"\)\);/, "routes should load the tools dashboard on demand");
assert.match(routesSource, /path="\/tools" element=\{withUserProps\(ToolsPage, styles, isDark\)\}/, "the public tools shell should render in place");
assert.match(routesSource, /path="\/tools\/links"[\s\S]*?<LegacyRedirect to="\/account\/admin\/content\/collection" preserveSearch hash=\{true\} \/>/, "legacy links should preserve query and hash while redirecting to administrator Collection management");
assert.match(routesSource, /path="\/account\/collection"[\s\S]*?withAuth\(<LegacyRedirect to="\/account\/admin\/content\/collection" preserveSearch hash=\{true\} \/>, true\)/, "legacy private Collection must require an administrator before redirecting");
assert.match(routesSource, /path="content\/collection" element=\{<PrivateCollectionPage \/>\}/, "private Collection should live in the canonical administrator content area");
assert.match(routesSource, /path="\/collection"[\s\S]*?withAuth\(withUserProps\(CollectionPage, styles, isDark\)\)/, "collection should require login");
assert.match(routesSource, /path="\/books"[\s\S]*?withAuth\(<BooksPage \/>, true\)/, "books should require an administrator");
assert.match(routesSource, /path="\/music"[\s\S]*?withAuth\(<MusicLobbyPage \/>\)/, "music should open the authenticated room lobby");
assert.doesNotMatch(routesSource, /path="\/music"[^\n]*StandalonePlayerPage/, "the local demo must not occupy the music route");
const gameRoomSource = readFileSync(new URL("../src/pages/GameRoomPage.jsx", import.meta.url), "utf8");
const gameControllerSource = readFileSync(new URL("../src/features/games/useGameRoom.js", import.meta.url), "utf8");
assert.match(gameRoomSource, /useGameRoom\(roomId, user\)/, "game room page must use the shared controller");
assert.match(gameControllerSource, /path:\s*['"]\/ws\/socket\.io['"]/, "game room must use the mounted Socket.IO path");
assert.match(
  gameControllerSource,
  /auth:\s*\{\s*token:\s*localStorage\.getItem\(['"]token['"]\)\s*\}/,
  "game room Socket.IO connection must authenticate with the access token",
);
assert.doesNotMatch(
  gameControllerSource,
  /join_game_room[^\n]*user_id/,
  "game room join must not send a client-claimed user id",
);

const gameBoardSource = readFileSync(new URL("../src/components/GameBoard.jsx", import.meta.url), "utf8");
assert.doesNotMatch(
  gameBoardSource,
  /game_state|currentPlayer|cursor-not-allowed relative/,
  "game board must render the safe server view instead of the disabled local board",
);

assert.match(gameControllerSource, /request_game_snapshot/, "game room restore must request a fresh personalized snapshot");
assert.doesNotMatch(gameControllerSource, /setInterval\([^)]*loadRoom|2000/, "game room must not use polling as its authority");

assert.match(
  routesSource,
  /<Route path="\*" element=\{withUserProps\(NotFoundPage, styles, isDark\)\} \/>/,
  "unknown routes should render a not-found page instead of silently returning home",
);
