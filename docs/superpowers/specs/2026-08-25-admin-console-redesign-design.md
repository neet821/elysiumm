# Admin Console and Role-Aware Account Entry Design

## Goal

Make the account icon role-aware and replace the current administrator shell with a compact, responsive white workspace that does not inherit the public site's large header spacing.

## Scope

- Authenticated administrators open `/admin` from the account avatar and retain the homepage administrator shortcut.
- Authenticated ordinary users open `/account` from the same avatar.
- Unauthenticated visitors continue to open `/login`.
- `/admin/*` keeps its existing route names and page modules, but receives a new shell and overview presentation.
- The public header and footer are hidden on `/admin/*`; the administrator shell owns its own back-home control, navigation, and page framing.
- Desktop uses a left navigation rail and a right content column. Mobile uses a compact top header and a horizontally scrollable navigation row.
- Existing backend endpoints, authentication semantics, room/live behavior, Obsidian files, and LiveSync services are out of scope.

## UI Design

The administrator shell is plain white with a thin border and restrained blue accent. The top of the page starts within the viewport rather than after the public header's reserved space. The left rail contains a small Elysium admin mark, a clear “管理控制台” title, grouped navigation links, and a “返回首页” link. The content column contains the active page only.

The overview page begins with a compact title row and refresh action, then a primary status strip and a grid of operational links. Cards show an icon, label, current value, and one-line purpose; they remain simple bordered blocks without shadows or decorative hero space.

## Routing and Error Boundaries

`Header` computes the account target from `isAdmin` before `isAuthenticated`: `/admin`, `/account`, then `/login`. `AppShell` recognizes `/admin` and hides public chrome. The existing `ProtectedRoute requireAdmin` remains the authorization boundary; the new shell does not grant access by itself.

## Verification

- Unit tests cover all three account targets and the administrator shortcut.
- Shell tests cover the new navigation label, active link, back-home link, and absence of the public banner/footer on `/admin`.
- Overview tests continue to mock the existing overview and music status APIs and verify the new accessible headings/cards.
- Run focused tests, lint, production build, and real production DOM/API checks after deployment.
