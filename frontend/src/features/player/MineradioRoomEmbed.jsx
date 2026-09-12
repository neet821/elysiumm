// Compatibility import for older route bundles. The room player is now a
// native React implementation; this file intentionally contains no iframe or
// cross-window message bridge.
export { default, NativeAudioAdapter } from '../music/MusicRoomPlayer.jsx'
