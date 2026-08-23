# Elysium 3D Room Design

## Product shape

Build a desktop-first personal room that is composed for three controlled camera views. The uploaded bay-window room is the spatial reference: a long desk sits in front of a wide window, while a low record cabinet, shelves, poster, and photo grid form the right-side visual counterweight. The render language follows pure-line-room's method—simple Three.js geometry with light fills and dark outlines—but the room layout, camera system, environment, navigation, and interactions are new.

## Chosen approach

Use Vite, vanilla JavaScript, and Three.js. This keeps the page lightweight and avoids a UI framework while still allowing maintainable modules. All visible furniture is built from Box, Plane, Cylinder, Sphere, and Buffer geometries. An outlined-mesh factory applies the active palette to fills and edges, so later recoloring does not require model changes.

The room is intentionally camera-complete rather than architecturally complete. Geometry outside the three visible compositions is omitted unless it prevents a visual gap.

## Scene and composition

- `overview`: front-left diagonal view containing the desk, window, and right-wall collection in one composition.
- `desk`: seated eye-level view centered on the monitor and bay window.
- `right`: near-orthogonal view of the record player, record storage, shelves, poster, and photo wall.
- Camera transitions interpolate both position and look target with a cubic easing curve. Pointer parallax is applied only after the base camera pose is calculated and is clamped to a few degrees.
- The shell uses a floor, partial back wall, right return, crown/base trim, and purpose-built window framing. A single scenery layer behind the whole bay prevents seams between panes.

## Environment

`EnvironmentController` owns the effective time state, palette, room light, lamp contribution, page background, outline colors, and scenery. `AUTO` maps local time to morning, day, evening, or night. Manual `DAY`, `EVENING`, and `NIGHT` selections stop automatic overrides until `AUTO` is selected again.

Nature, city, cloudy, and night are local SVG panorama assets. An asset map contains their URLs, so replacing the files or URLs is sufficient to change the view. The first version does not call a weather API.

## Interaction and navigation

Every interactive object has a visible group and an invisible proxy registered with one raycaster. Hover changes the pointer, strengthens the object's outline, and shows a small label. Interaction is locked during camera/page transitions.

Type A objects focus the camera before opening a hash route overlay:

- monitor -> `#/projects`
- photo wall -> `#/gallery`
- books -> `#/reading`
- poster/media -> `#/movies`

Closing a page or using browser Back returns to the previous 3D camera preset. Hash routes survive refresh without server rewrite rules.

Type B objects remain in the scene:

- record player toggles synthesized music and animates the record/tonearm;
- record rack cycles album accent colors and the current album label;
- lamp toggles a warm point light and visible glow;
- window cycles scenery;
- the environment controls switch AUTO/DAY/EVENING/NIGHT directly.

## UI

The WebGL canvas fills the viewport. A restrained overlay provides the title, current environment, three camera buttons, time selector, sound state, contextual hover hint, and a compact interaction legend. Typography, fine borders, rounded pills, and muted colors support the line-art scene rather than covering it. On smaller desktop widths, controls wrap and nonessential explanatory copy is hidden.

## Quality and testing

- Unit tests cover local-time classification and manual override behavior.
- Browser tests cover all camera controls, Type A navigation and return, record player, lamp, scenery cycling, time mode, resize, direct route refresh, and console/page errors.
- Visual screenshots are inspected at 1920x1080 and 2560x1440 for all three cameras.
- Rendering caps device pixel ratio and avoids shadows/post-processing/high-poly assets.

## Deliberate Phase 2 scope

Advanced PBR materials, modeled outdoor architecture, live weather, production music streaming, complete content pages, mobile-first composition, and editable room customization are outside this phase.
