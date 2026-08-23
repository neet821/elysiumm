# Mineradio in Blue Album

This directory vendors the browser-capable player from XxHuberrr/Mineradio v1.1.1.
The upstream GPL-3.0 license and visual-identity notice are preserved in `LICENSE`
and `NOTICE.md`.

Blue Album embeds the original browser application in music-room mode. The
standalone upstream application remains intact; the room query parameter adds a
narrow same-origin bridge without replacing its cover stage, lyrics, particles,
or visual-effects console.

The current extraction boundary is:

- `/music/rooms/:roomId` loads `/mineradio/?blue-room=:roomId` from the vendored
  v1.1.1 server;
- room mode hides upstream account, login, personal library, home, search, and
  weather surfaces while preserving its player and effects;
- the same-origin bridge translates Blue Album snapshots into original
  Mineradio playback and lyric state;
- room membership, catalog search, voting, queue, upload, member, chat, and
  reconnect logic remain owned by Blue Album and are shown in the embedded room
  drawer;
- provider credentials remain server-side and are never posted into the frame.

No upstream copyright or license file has been removed or replaced.
