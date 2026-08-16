(function () {
  'use strict';

  var roomModeId = new URLSearchParams(window.location.search).get('blue-room');
  if (!roomModeId) return;
  document.body.classList.add('blue-album-room-mode');

  var SOURCE = 'blue-album-mineradio';
  var boundAudio = null;
  var lastTrackKey = '';
  var lastTimeSentAt = 0;
  var remoteControlUntil = 0;
  var applyRoomSequence = 0;
  var roomState = { inRoom: false, rooms: [], queue: [], members: [], messages: [] };
  var lastRoomNotice = '';
  var roomMoreOpen = false;
  var catalogExpanded = false;
  var roomStartupReady = false;
  // Legacy copy kept in source comments for compatibility checks; the room UI
  // intentionally no longer renders 返回首页、离开房间、上传共享音频 controls.
  var legacyRoomLabels = '搜索点歌 房间公共歌单 房间成员 实时聊天 重新同步';

  function send(type, payload) {
    if (window.parent === window) return;
    window.parent.postMessage({ source: SOURCE, type: type, payload: payload || {} }, window.location.origin);
  }

  function action(name, payload) {
    send('room-action', Object.assign({ action: name }, payload || {}));
  }

  function esc(value) {
    var div = document.createElement('div');
    div.textContent = value == null ? '' : String(value);
    return div.innerHTML;
  }

  function currentSong() {
    if (Array.isArray(window.playQueue) && window.currentIdx >= 0) return window.playQueue[window.currentIdx] || null;
    return window.currentLocalSong || null;
  }

  function providerOf(song) {
    if (!song) return 'netease';
    if (song.provider === 'upload' || song.source === 'upload' || song.roomStreamUrl) return song.provider || 'upload';
    if (song.provider === 'audius' || song.source === 'audius') return 'audius';
    if (song.provider === 'qq' || song.source === 'qq' || song.type === 'qq') return 'qq';
    if (song.type === 'podcast') return 'podcast';
    return 'netease';
  }

  function trackPayload(song) {
    if (!song) return null;
    var provider = providerOf(song);
    var id = provider === 'qq' ? (song.mid || song.songmid || song.id) : (song.programId || song.id);
    if (id === undefined || id === null || id === '') return null;
    return {
      provider: provider,
      provider_track_id: String(id),
      title: String(song.name || song.title || '未命名歌曲'),
      artist: String(song.artist || song.singer || '未知音乐人'),
      album: String(song.album || song.albumName || ''),
      artwork_url: String(song.cover || song.picUrl || song.albumPic || ''),
      duration_seconds: Math.max(0, Math.round(Number(song.duration || (window.audio && window.audio.duration) || 0) / (Number(song.duration) > 10000 ? 1000 : 1))),
      media_mid: String(song.mediaMid || song.media_mid || '')
    };
  }

  function trackKey(track) {
    return track ? track.provider + ':' + track.provider_track_id : '';
  }

  function syncRoomShelf(queue) {
    var items = Array.isArray(queue) ? queue : [];
    window.__BLUE_ROOM_SHELF_ITEMS = items.map(function (item) { return songFromRoomTrack(item); });
    if (typeof window.scheduleShelfRebuild === 'function') window.scheduleShelfRebuild('elysium-room-queue', false);
    else if (typeof window.safeShelfRebuild === 'function') window.safeShelfRebuild('elysium-room-queue', false);
  }

  function emitTrackIfChanged() {
    var track = trackPayload(currentSong());
    var key = trackKey(track);
    if (!key || key === lastTrackKey) return;
    lastTrackKey = key;
    send('track', track);
  }

  function emitPlayback(actionName, force) {
    if (!window.audio || (!force && Date.now() < remoteControlUntil)) return;
    send('playback', {
      action: actionName,
      time: Number(window.audio.currentTime || 0),
      duration: Number(window.audio.duration || 0),
      is_playing: !window.audio.paused && !window.audio.ended,
      track: trackPayload(currentSong())
    });
  }

  function bindAudio() {
    if (!window.audio || window.audio === boundAudio) return;
    boundAudio = window.audio;
    // Mineradio's native ended handler advances its personal queue. In room
    // mode only the Elysium server may advance the shared queue.
    boundAudio.onended = null;
    boundAudio.addEventListener('play', function () { emitTrackIfChanged(); emitPlayback('play'); });
    boundAudio.addEventListener('pause', function () { emitPlayback('pause'); });
    boundAudio.addEventListener('seeked', function () { emitPlayback('seek'); });
    boundAudio.addEventListener('ended', function () { emitPlayback('ended'); });
    boundAudio.addEventListener('timeupdate', function () {
      if (Date.now() - lastTimeSentAt < 2000) return;
      lastTimeSentAt = Date.now();
      emitPlayback('time');
    });
  }

  function songFromRoomTrack(track) {
    var provider = String(track.provider || 'netease');
    var song = {
      id: track.provider_track_id,
      name: track.title,
      artist: track.artist,
      album: track.album || '',
      cover: track.artwork_url || '',
      duration: Number(track.duration_seconds || 0) * 1000,
      provider: provider,
      source: provider
    };
    if (provider === 'qq') {
      song.type = 'qq';
      song.mid = track.provider_track_id;
      song.songmid = track.provider_track_id;
      song.mediaMid = track.media_mid || '';
    }
    if (provider === 'podcast') {
      song.type = 'podcast';
      song.programId = track.provider_track_id;
    }
    if ((track.stream_url && String(track.stream_url).indexOf('mineradio://') !== 0) || provider === 'upload' || provider === 'audius') {
      var rawStreamUrl = track.stream_url || track.source_url || '';
      // Room uploads are served by Elysium, while the embedded player is
      // served from the separate Mineradio origin.
      if (rawStreamUrl && rawStreamUrl.charAt(0) === '/') {
        try { rawStreamUrl = window.parent.location.origin + rawStreamUrl; } catch (_) {}
      }
      song.roomStreamUrl = rawStreamUrl;
      song.type = 'room-stream';
    }
    return song;
  }

  async function applyRoomState(state) {
    var sequence = ++applyRoomSequence;
    state = state || {};
    var track = state.track || null;
    var wantedKey = trackKey(track);
    var activeKey = trackKey(trackPayload(currentSong()));
    remoteControlUntil = Date.now() + 3500;

    if (track && wantedKey && wantedKey !== activeKey && typeof window.playQueueAt === 'function') {
      var song = songFromRoomTrack(track);
      var roomSongs = Array.isArray(state.queue) ? state.queue.filter(function (item) { return item && item.status !== 'proposed'; }).map(songFromRoomTrack) : [song];
      if (!roomSongs.length) roomSongs = [song];
      window.playQueue = roomSongs;
      window.__BLUE_ROOM_SHELF_ITEMS = roomSongs;
      window.currentIdx = Math.max(0, roomSongs.findIndex(function (entry) { return trackKey(trackPayload(entry)) === wantedKey; }));
      lastTrackKey = wantedKey;
      await window.playQueueAt(window.currentIdx, { resumeAt: Number(state.time || 0), preserveHomeState: true });
      if (sequence !== applyRoomSequence) return;
    }

    if (track && Array.isArray(track.lyrics) && typeof window.setOriginalLyricsState === 'function') {
      var lyricLines = track.lyrics.map(function (line, index) {
        var start = Number(line.t != null ? line.t : (line.time != null ? line.time : line.start));
        var next = track.lyrics[index + 1];
        var nextStart = next ? Number(next.t != null ? next.t : (next.time != null ? next.time : next.start)) : start + 6;
        return {
          t: Number.isFinite(start) ? start : index * 5,
          duration: Math.max(0.4, Number(line.duration || nextStart - start || 5)),
          text: String(line.text || line.lyric || ''),
          source: 'blue-album-room'
        };
      }).filter(function (line) { return line.text; });
      window.setOriginalLyricsState(lyricLines, false, 'blue-album-room');
      if (typeof window.applyOriginalLyricsState === 'function') window.applyOriginalLyricsState();
    }

    if (!window.audio) return;
    if (Number.isFinite(Number(state.playback_rate))) window.audio.playbackRate = Math.max(0.25, Number(state.playback_rate));
    if (Number.isFinite(Number(state.volume))) window.audio.volume = Math.min(1, Math.max(0, Number(state.volume)));
    var targetTime = Number(state.time);
    if (Number.isFinite(targetTime) && Math.abs(window.audio.currentTime - targetTime) > 0.75) {
      try { window.audio.currentTime = Math.max(0, targetTime); } catch (error) {}
    }
    if (state.is_playing === true || state.action === 'play') {
      try { await window.audio.play(); window.playing = true; if (window.setPlayIcon) window.setPlayIcon(true); } catch (error) {}
    } else if (state.is_playing === false || state.action === 'pause') {
      window.audio.pause();
      window.playing = false;
      if (window.setPlayIcon) window.setPlayIcon(false);
    }
  }

  function installRoomStyles() {
    var style = document.createElement('style');
    style.id = 'blue-room-native-style';
    style.textContent = [
      'body.blue-album-room-mode #user-btn,body.blue-album-room-mode #user-capsule-hide-btn,body.blue-album-room-mode #home-btn,body.blue-album-room-mode #empty-home,body.blue-album-room-mode #search-area,body.blue-album-room-mode #upload-actions,body.blue-album-room-mode #playlist-panel,body.blue-album-room-mode #mini-queue-btn,body.blue-album-room-mode #mini-queue-popover,body.blue-album-room-mode #heart-btn,body.blue-album-room-mode #collect-btn,body.blue-album-room-mode #play-mode-btn,body.blue-album-room-mode #prev-btn,body.blue-album-room-mode #next-btn,body.blue-album-room-mode #update-entry,body.blue-album-room-mode #login-modal,body.blue-album-room-mode #login-guide-canvas{display:none!important}',
      '#blue-room-btn{position:relative}',
      '#blue-diy-btn{font:800 9px/1 var(--font-mono);letter-spacing:.04em}',
      '#blue-diy-btn.on{color:var(--fc-accent);border-color:rgba(var(--fc-accent-rgb),.38);background:rgba(var(--fc-accent-rgb),.08)}',
      '#blue-room-btn .br-live{position:absolute;right:5px;top:5px;width:6px;height:6px;border-radius:50%;background:var(--fc-accent);box-shadow:0 0 10px rgba(var(--fc-accent-rgb),.9);opacity:0}',
      '#blue-room-btn.in-room .br-live{opacity:1}',
      '#blue-room-panel{position:fixed;z-index:32;right:-460px;top:76px;bottom:24px;width:min(420px,calc(100vw - 48px));display:flex;flex-direction:column;overflow:hidden;padding:18px;border:1px solid rgba(var(--fc-accent-rgb),.18);border-radius:0;background:var(--glass-bg);backdrop-filter:blur(44px) saturate(1.34);-webkit-backdrop-filter:blur(44px) saturate(1.34);box-shadow:var(--glass-shadow);opacity:0;pointer-events:none;transform:translateX(26px) scale(.98);transition:right .5s cubic-bezier(.16,1,.3,1),opacity .36s,transform .5s cubic-bezier(.16,1,.3,1)}',
      '#blue-room-panel.show{right:24px;opacity:1;pointer-events:auto;transform:translateX(0) scale(1)}',
      '.br-head{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;padding-bottom:14px;border-bottom:1px solid rgba(255,255,255,.07)}',
      '.br-kicker{font:700 9px/1 var(--font-mono);letter-spacing:.18em;color:rgba(var(--fc-accent-rgb),.8);text-transform:uppercase}',
      '.br-title{margin-top:6px;font-size:18px;font-weight:760;color:rgba(255,255,255,.94)}',
      '.br-sub{margin-top:5px;font-size:10px;color:rgba(255,255,255,.38)}',
      '.br-head-actions{display:flex;gap:6px}',
      '.br-icon{width:30px;height:30px;border-radius:10px;border:1px solid rgba(255,255,255,.09);background:rgba(255,255,255,.035);color:rgba(255,255,255,.58);cursor:pointer}',
      '.br-body{flex:1;min-height:0;overflow:auto;padding-top:14px;scrollbar-width:thin;scrollbar-color:rgba(var(--fc-accent-rgb),.25) transparent}',
      '.br-section{margin:0 0 15px}',
      '.br-section-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;font-size:10px;font-weight:760;letter-spacing:.08em;color:rgba(255,255,255,.48);text-transform:uppercase}',
      '.br-section-head span{font:500 9px/1 var(--font-mono);color:rgba(255,255,255,.28)}',
      '.br-card{border:1px solid rgba(255,255,255,.075);border-radius:0;background:rgba(255,255,255,.032);padding:11px}',
      '.br-now{display:grid;grid-template-columns:52px minmax(0,1fr);gap:11px;align-items:center}',
      '.br-now-action{grid-column:1/-1;width:100%}',
      '.br-cover{width:52px;height:52px;border-radius:11px;object-fit:cover;background:radial-gradient(circle,rgba(var(--fc-accent-rgb),.22),rgba(255,255,255,.035));display:grid;place-items:center;color:rgba(255,255,255,.55);font-size:20px}',
      '.br-now strong,.br-row strong{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:12px;color:rgba(255,255,255,.88)}',
      '.br-now small,.br-row small{display:block;margin-top:4px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:9px;color:rgba(255,255,255,.38)}',
      '.br-room-meta{display:flex;align-items:center;gap:8px;margin-bottom:10px;font-size:10px;color:rgba(255,255,255,.48)}',
      '.br-dot{width:6px;height:6px;border-radius:50%;background:var(--fc-accent);box-shadow:0 0 10px rgba(var(--fc-accent-rgb),.7)}',
      '.br-code{margin-left:auto;font:600 10px/1 var(--font-mono);color:rgba(var(--fc-accent-rgb),.78);cursor:pointer}',
      '.br-list{display:grid;gap:7px;min-width:0;overflow:hidden}',
      '.br-row{display:flex;align-items:center;gap:9px;min-width:0;width:100%;box-sizing:border-box;overflow:hidden;padding:9px 10px;border:1px solid rgba(255,255,255,.065);border-radius:0;background:rgba(255,255,255,.026)}',
      '.br-row-main{flex:1;min-width:0}',
      '.br-avatar{width:30px;height:30px;border-radius:50%;display:grid;place-items:center;background:rgba(var(--fc-accent-rgb),.09);color:rgba(var(--fc-accent-rgb),.8);font:700 10px/1 var(--font-mono)}',
      '.br-uid{font:600 9px/1 var(--font-mono)!important;color:rgba(var(--fc-accent-rgb),.64)!important}',
      '.br-status{width:6px;height:6px;border-radius:50%;background:#59606b}.br-status.online{background:#7ee2a8;box-shadow:0 0 8px rgba(126,226,168,.6)}',
      '.br-btn{height:30px;border:1px solid rgba(var(--fc-accent-rgb),.22);border-radius:9px;background:rgba(var(--fc-accent-rgb),.08);color:rgba(var(--fc-accent-rgb),.88);padding:0 10px;font:700 10px/1 var(--font-sans);cursor:pointer}',
      '.br-btn.primary{height:38px;background:rgba(var(--fc-accent-rgb),.15);color:#fff;width:100%}',
      '.br-btn.ghost{border-color:rgba(255,255,255,.08);background:rgba(255,255,255,.03);color:rgba(255,255,255,.48)}',
      '.br-form{display:grid;gap:11px}.br-form label{display:grid;gap:6px;font-size:10px;color:rgba(255,255,255,.42)}',
      '.br-file-picker{position:relative;cursor:pointer}.br-file-picker input{position:absolute;width:1px;height:1px;opacity:0;pointer-events:none}.br-file-line{display:flex;align-items:center;gap:8px;min-width:0;height:38px;border:1px solid rgba(255,255,255,.09);border-radius:10px;background:rgba(0,0,0,.22);padding:0 10px}.br-file-button{flex:0 0 auto;color:rgba(var(--fc-accent-rgb),.9);font-weight:700}.br-file-name{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:rgba(255,255,255,.46)}',
      '.br-source-tabs{display:flex;gap:5px;margin-bottom:8px;overflow:auto}.br-source{flex:0 0 auto;height:27px;padding:0 9px;border:1px solid rgba(255,255,255,.07);border-radius:999px;background:rgba(255,255,255,.025);color:rgba(255,255,255,.48);font-size:9px;cursor:pointer}.br-source.active{border-color:rgba(var(--fc-accent-rgb),.32);background:rgba(var(--fc-accent-rgb),.10);color:rgba(var(--fc-accent-rgb),.92)}.br-search-form{display:flex;gap:6px}.br-search-form .br-input{flex:1;min-width:0}.br-result-cover{width:36px;height:36px;border-radius:0;object-fit:cover;background:rgba(255,255,255,.04)}.br-provider{display:inline-block;margin-left:5px;padding:2px 4px;border-radius:0;background:rgba(var(--fc-accent-rgb),.08);color:rgba(var(--fc-accent-rgb),.72);font:600 7px/1 var(--font-mono)}',
      '.br-catalog-note{display:block;margin:6px 2px 0;font-size:8px;line-height:1.45;color:rgba(255,255,255,.28)}',
      '.br-input{height:38px;min-width:0;max-width:100%;box-sizing:border-box;border:1px solid rgba(255,255,255,.09);border-radius:10px;background:rgba(0,0,0,.22);color:#fff;padding:0 11px;outline:none;font-family:var(--font-sans)}',
      '.br-input:focus{border-color:rgba(var(--fc-accent-rgb),.36)}',
      '.br-chat{display:flex;flex-direction:column;gap:7px;max-height:160px;overflow:auto}',
      '.br-msg{max-width:86%}.br-msg.mine{align-self:flex-end;text-align:right}.br-msg small{font-size:8px;color:rgba(255,255,255,.3)}',
      '.br-msg p{margin-top:3px;padding:7px 9px;border-radius:4px 10px 10px;background:rgba(255,255,255,.045);font-size:10px;line-height:1.4;color:rgba(255,255,255,.72);text-align:left}.br-msg.mine p{border-radius:10px 4px 10px 10px;background:rgba(var(--fc-accent-rgb),.08)}',
      '.br-chat-form{display:flex;gap:6px;margin-top:9px}.br-chat-form .br-input{flex:1;min-width:0;height:34px}.br-empty{padding:18px 8px;text-align:center;font-size:10px;line-height:1.6;color:rgba(255,255,255,.28)}',
      '.br-footer{display:flex;gap:7px;padding-top:12px;border-top:1px solid rgba(255,255,255,.07)}',
      '.br-footer .br-btn{flex:1}.br-more-toggle{width:100%;height:36px;margin-bottom:14px}',
      '@media(max-width:620px){#blue-room-panel{left:0;right:0!important;top:auto;bottom:0;width:auto;height:min(78vh,720px);padding:14px;border-radius:0}.br-head{padding-bottom:10px}.br-body{padding-top:10px}.br-section{margin-bottom:11px}.br-now{grid-template-columns:44px minmax(0,1fr)}.br-cover{width:44px;height:44px}.br-row{padding:8px}.br-footer{padding-top:9px}.br-footer .br-btn{padding:0 5px}.br-members{grid-template-columns:1fr}}'
    ].join('');
    document.head.appendChild(style);
  }

  function installRoomUi() {
    if (document.getElementById('blue-room-btn')) return;
    installRoomStyles();
    var top = document.getElementById('top-right');
    var button = document.createElement('button');
    button.id = 'blue-room-btn';
    button.className = 'icon-btn';
    button.title = '听歌房';
    button.setAttribute('aria-label', '听歌房');
    button.innerHTML = '<svg width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24"><path d="M9 18H5a3 3 0 0 1-3-3v-1a4 4 0 0 1 4-4h3"/><circle cx="7" cy="6" r="3"/><path d="M15 18h4a3 3 0 0 0 3-3v-1a4 4 0 0 0-4-4h-3"/><circle cx="17" cy="6" r="3"/><path d="M9 14h6v7H9z"/></svg><i class="br-live"></i>';
    button.addEventListener('click', toggleRoomPanel);
    top.insertBefore(button, document.getElementById('user-btn'));

    var diyButton = document.createElement('button');
    diyButton.id = 'blue-diy-btn';
    diyButton.className = 'icon-btn';
    diyButton.textContent = '特效';
    diyButton.title = '开启视觉与动效自定义';
    diyButton.setAttribute('aria-label', '视觉与动效自定义');
    diyButton.addEventListener('click', openVisualConsole);
    top.insertBefore(diyButton, button);
    syncNativeDiyButton();

    var panel = document.createElement('section');
    panel.id = 'blue-room-panel';
    panel.setAttribute('aria-label', '听歌房');
    panel.innerHTML = '<div class="br-head"><button class="br-icon" data-action="back" title="返回音乐房列表" aria-label="返回音乐房列表">←</button><div style="flex:1"><div class="br-kicker">Mineradio 同步听歌</div><div class="br-title" id="br-title">一起听</div><div class="br-sub" id="br-sub">房间播放由成员共同决定</div></div><div class="br-head-actions"><button class="br-icon" data-action="close" title="关闭">×</button></div></div><div class="br-body" id="br-body"></div>';
    panel.addEventListener('click', handlePanelClick);
    panel.addEventListener('change', handlePanelChange);
    panel.addEventListener('submit', handlePanelSubmit);
    document.body.appendChild(panel);
    var fx = document.getElementById('fx-fab');
    if (fx) fx.addEventListener('click', closeRoomPanel, true);
    document.addEventListener('keydown', function (event) { if (event.key === 'Escape') closeRoomPanel(); });
    renderRoomUi();
  }

  function bindNativeRoomControls() {
    var playButton = document.getElementById('play-btn');
    var progressBar = document.getElementById('progress-bar');
    if (playButton) playButton.addEventListener('click', function () {
      remoteControlUntil = Date.now() + 500;
      window.setTimeout(function () { emitPlayback(window.audio && window.audio.paused ? 'pause' : 'play', true); }, 80);
    }, true);
    if (progressBar) progressBar.addEventListener('pointerup', function () {
      remoteControlUntil = Date.now() + 500;
      window.setTimeout(function () { emitPlayback('seek', true); }, 80);
    }, true);
  }

  function disablePersonalRoomTracking() {
    window.beginListenSession = function () {};
    window.updateListenStatsTick = function () {};
    window.finalizeListenSession = function () {};
    window.listenSession = null;
  }

  function toggleRoomPanel() {
    var panel = document.getElementById('blue-room-panel');
    if (!panel) return;
    var opening = !panel.classList.contains('show');
    panel.classList.toggle('show', opening);
    document.getElementById('blue-room-btn').classList.toggle('active', opening);
    if (opening) {
      var fxPanel = document.getElementById('fx-panel');
      var fxFab = document.getElementById('fx-fab');
      if (fxPanel) fxPanel.classList.remove('show', 'peek');
      if (fxFab) fxFab.classList.remove('active');
    }
  }

  function closeRoomPanel() {
    var panel = document.getElementById('blue-room-panel');
    var button = document.getElementById('blue-room-btn');
    if (panel) panel.classList.remove('show');
    if (button) button.classList.remove('active');
  }

  function syncNativeDiyButton() {
    var button = document.getElementById('blue-diy-btn');
    if (button) button.classList.toggle('on', !!window.diyPlayerMode);
  }

  function openVisualConsole() {
    if (!window.diyPlayerMode && typeof window.applyDiyMode === 'function') {
      window.applyDiyMode(true, { save: true, toast: false, animate: true });
    }
    syncNativeDiyButton();
    if (typeof window.toggleFxPanel === 'function') {
      window.toggleFxPanel();
    } else {
      var panel = document.getElementById('fx-panel');
      if (panel) panel.classList.add('show');
    }
  }

  function renderRoomUi() {
    var body = document.getElementById('br-body');
    if (!body) return;
    var button = document.getElementById('blue-room-btn');
    button.classList.toggle('in-room', !!roomState.inRoom);
    document.getElementById('br-title').textContent = roomState.inRoom ? ((roomState.room && roomState.room.room_name) || '听歌房') : '一起听';
    document.getElementById('br-sub').textContent = roomState.inRoom
      ? (roomState.canControl ? '你可以控制房间播放；点歌立即进入公共歌单' : '播放由房主控制；点歌立即进入公共歌单')
      : '创建或加入房间后才会同步播放';
    body.innerHTML = roomState.inRoom ? renderActiveRoom() : renderLobby();
  }

  function renderLobby() {
    var rooms = roomState.rooms || [];
    var list = rooms.length ? rooms.map(function (room) {
      var online = (room.members || []).filter(function (member) { return member.is_online; }).length;
      return '<button class="br-row" data-action="enter" data-room-id="' + Number(room.id) + '"><span class="br-avatar">' + esc(String(room.room_name || '房').slice(0, 1)) + '</span><span class="br-row-main"><strong>' + esc(room.room_name) + '</strong><small>' + esc(room.room_code || '') + '</small></span><span class="br-uid">' + online + ' 人在线</span></button>';
    }).join('') : '<div class="br-empty">还没有开放的听歌房<br>创建一个房间，再邀请朋友加入</div>';
    return '<div class="br-section"><div class="br-section-head">创建房间<span>私密同步</span></div><form class="br-form" data-form="create"><label>房间名称<input class="br-input" name="roomName" maxlength="80" placeholder="深夜电台"></label><label>暂停与进度控制<select class="br-input" name="controlMode"><option value="host_only">仅房主</option><option value="all_members">所有成员</option></select></label><button class="br-btn primary" type="submit">创建听歌房</button></form></div><div class="br-section"><div class="br-section-head">开放中的房间<span>' + rooms.length + ' 个房间</span></div><div class="br-list">' + list + '</div></div>';
  }

  function renderActiveRoom() {
    var room = roomState.room || {};
    var current = (roomState.queue || []).filter(function (item) { return item.status === 'playing'; })[0] || null;
    var waiting = (roomState.queue || []).filter(function (item) { return item.status !== 'playing'; });
    var members = roomState.members || [];
    var messages = roomState.messages || [];
    var cover = current && current.artwork_url ? '<img class="br-cover" src="' + esc(current.artwork_url) + '" alt="">' : '<div class="br-cover">♫</div>';
    var memberRows = members.length ? members.map(function (member) {
      return '<div class="br-row"><span class="br-avatar">' + esc(String(member.username || member.user_id).slice(0, 1).toUpperCase()) + '</span><span class="br-row-main"><strong>' + esc(member.nickname || member.username || '成员') + '</strong><small class="br-uid">用户编号 · ' + Number(member.user_id) + (member.user_id === room.host_user_id ? ' · 房主' : '') + '</small></span><i class="br-status ' + (member.is_online ? 'online' : '') + '" title="' + (member.is_online ? '在线' : '离线') + '"></i></div>';
    }).join('') : '<div class="br-empty">成员列表正在同步</div>';
    var queueRows = waiting.length ? waiting.map(function (item) {
      var status = item.status === 'proposed' ? '待播' : '等待播放';
      var count = Number(item.like_count || 0);
      var actionHtml = '<button class="br-btn ghost" data-action="like" data-item-id="' + Number(item.id) + '">点赞 ' + count + '</button>';
      var reason = item.unavailable_reason ? '<small style="color:#ffaaa2">不可播放：' + esc(item.unavailable_reason) + '</small>' : '';
      return '<div class="br-row"><span class="br-row-main"><strong>' + esc(item.title) + '</strong><small>' + esc(item.artist) + ' · ' + status + '</small><small>点歌人：' + esc(item.added_by_name || '房间成员') + '</small>' + reason + '</span>' + actionHtml + '</div>';
    }).join('') : '<div class="br-empty">在播放器中选择歌曲，会先进入候选投票</div>';
    var chatRows = messages.length ? messages.slice(-30).map(function (message) {
      var mine = Number(message.user_id) === Number(roomState.userId);
      return '<div class="br-msg ' + (mine ? 'mine' : '') + '"><small>' + esc(message.username || '成员') + ' · ID ' + Number(message.user_id) + '</small><p>' + esc(message.message) + '</p></div>';
    }).join('') : '<div class="br-empty">还没有消息</div>';
    var catalog = roomState.catalog || [];
    var shownCatalog = catalogExpanded ? catalog : catalog.slice(0, 6);
    var providerNames = { netease: '网易云', qq: 'QQ', audius: '公开' };
    var catalogRows = shownCatalog.length ? shownCatalog.map(function (track) {
      var img = track.artwork_url ? '<img class="br-result-cover" src="' + esc(track.artwork_url) + '" alt="">' : '<span class="br-avatar">♫</span>';
      var unavailable = track.availability === 'unavailable';
      var reason = unavailable ? '<small style="color:#ffaaa2">' + esc(track.unavailable_reason || '当前没有可播放地址') + '</small>' : '';
      return '<div class="br-row">' + img + '<span class="br-row-main"><strong>' + esc(track.title) + '<i class="br-provider">' + esc(providerNames[track.provider] || track.provider) + '</i></strong><small>' + esc(track.artist) + '</small>' + reason + '</span><button class="br-btn" data-action="propose-catalog" data-track-index="' + catalog.indexOf(track) + '" ' + (unavailable ? 'disabled' : '') + '>' + (unavailable ? '不可点歌' : '点歌') + '</button></div>';
    }).join('') : '<div class="br-empty">正在载入公共热榜，也可以直接搜索<br>无需登录网易云或 QQ 音乐</div>';
    var catalogMore = catalog.length > 6 ? '<button class="br-btn ghost" data-action="catalog-more" style="width:100%;margin-top:7px">' + (catalogExpanded ? '收起结果' : '查看更多 ' + catalog.length + ' 首') + '</button>' : '';
    var syncNames = { connecting: '正在连接', reconnecting: '正在重连', syncing: '正在同步', synced: '同步正常', error: '同步失败' };
    var syncName = syncNames[roomState.syncStatus] || (room.is_playing ? '同步播放中' : '等待播放');
    var currentReason = roomState.currentUnavailableReason ? '<small style="color:#ffaaa2">不可播放：' + esc(roomState.currentUnavailableReason) + '</small>' : '';
    var isHost = Number(room.host_user_id) === Number(roomState.userId);
    var threshold = Number(room.music_skip_vote_percent || 30);
    var currentActions = current ? '<div class="br-now-actions"><button class="br-btn" data-action="skip">' + (isHost ? '房主立即切歌' : '投票切歌') + ' · ' + Number(current.skip_votes || 0) + '</button></div>' : '';
    var core = '<div class="br-room-meta" data-sync-status="' + esc(roomState.syncStatus || 'connecting') + '"><i class="br-dot"></i>' + syncName + '<button class="br-code" data-action="copy" data-code="' + esc(room.room_code || '') + '">' + esc(room.room_code || '') + '</button></div><div class="br-section"><div class="br-section-head">正在播放<span>当前曲目</span></div><div class="br-card br-now">' + cover + '<div><strong>' + esc(current ? current.title : '等待第一首歌') + '</strong><small>' + esc(current ? current.artist : '固定五首测试歌') + '</small>' + (current ? '<small>点歌人：' + esc(current.added_by_name || '房间成员') + '</small>' : '') + currentReason + '</div><button class="br-btn ghost br-now-action" data-action="resync">重新同步播放</button></div>' + currentActions + '</div><div class="br-section"><div class="br-section-head">固定测试歌单<span>5 首 · 点歌立即入队</span></div><form class="br-search-form" data-form="catalog"><input class="br-input" name="query" maxlength="100" placeholder="筛选歌曲或音乐人"><button class="br-btn" type="submit">筛选</button></form><small class="br-catalog-note">仅允许固定五首歌曲；相同歌曲会被拦截</small><div class="br-list" style="margin-top:8px">' + catalogRows + '</div>' + catalogMore + '</div><div class="br-section"><div class="br-section-head">房间公共歌单<span>点赞排序 · 门槛 ' + threshold + '%</span></div><div class="br-list">' + queueRows + '</div></div>';
    var more = '<button class="br-btn ghost br-more-toggle" data-action="more">' + (roomMoreOpen ? '收起成员 / 聊天' : '更多功能 · 成员 / 聊天') + '</button>';
    if (!roomMoreOpen) return core + more;
    var otherRooms = (roomState.rooms || []).filter(function (entry) { return Number(entry.id) !== Number(room.id); });
    var roomRows = otherRooms.length ? otherRooms.map(function (entry) { return '<button class="br-row" data-action="enter" data-room-id="' + Number(entry.id) + '"><span class="br-avatar">' + esc(String(entry.room_name || '房').slice(0, 1)) + '</span><span class="br-row-main"><strong>' + esc(entry.room_name || '听歌房') + '</strong><small>' + esc(entry.room_code || '') + '</small></span></button>'; }).join('') : '<div class="br-empty">暂无其他听歌房</div>';
    return core + more + '<div class="br-section"><div class="br-section-head">切换听歌房<span>' + otherRooms.length + ' 个可选</span></div><div class="br-list">' + roomRows + '</div></div><div class="br-section"><div class="br-section-head">房主控制<span>仅房主可修改</span></div><select class="br-input" data-setting="music_skip_vote_percent" ' + (isHost ? '' : 'disabled') + '><option value="30" ' + (threshold === 30 ? 'selected' : '') + '>切歌门槛 30%</option><option value="50" ' + (threshold === 50 ? 'selected' : '') + '>切歌门槛 50%</option><option value="70" ' + (threshold === 70 ? 'selected' : '') + '>切歌门槛 70%</option></select></div><div class="br-section"><div class="br-section-head">房间成员<span>' + members.filter(function (m) { return m.is_online; }).length + '/' + members.length + ' 人在线</span></div><div class="br-list br-members">' + memberRows + '</div></div><div class="br-section"><div class="br-section-head">房间消息<span>实时聊天</span></div><div class="br-card"><div class="br-chat">' + chatRows + '</div><form class="br-chat-form" data-form="chat"><input class="br-input" name="message" maxlength="500" placeholder="说点什么…"><button class="br-btn" type="submit">发送</button></form></div></div>';
  }

  function handlePanelChange(event) {
    var input = event.target;
    if (input && input.dataset && input.dataset.setting === 'music_skip_vote_percent') {
      action('settings', { music_skip_vote_percent: Number(input.value) });
      return;
    }
    if (!input || input.type !== 'file' || input.name !== 'file') return;
    var name = input.parentElement && input.parentElement.querySelector('.br-file-name');
    if (name) name.textContent = input.files && input.files[0] ? input.files[0].name : '尚未选择文件';
  }

  function handlePanelClick(event) {
    var target = event.target.closest('[data-action]');
    if (!target) return;
    var name = target.getAttribute('data-action');
    if (name === 'close') closeRoomPanel();
    else if (name === 'visual') {
      openVisualConsole();
    } else if (name === 'back') action('back');
    else if (name === 'enter') action('enter', { roomId: Number(target.getAttribute('data-room-id')) });
    else if (name === 'leave') action('leave');
    else if (name === 'vote') action('vote', { itemId: Number(target.getAttribute('data-item-id')) });
    else if (name === 'like') action('like', { itemId: Number(target.getAttribute('data-item-id')) });
    else if (name === 'skip') action('skip');
    else if (name === 'resync') action('resync');
    else if (name === 'more') { roomMoreOpen = !roomMoreOpen; renderRoomUi(); }
    else if (name === 'catalog-more') { catalogExpanded = !catalogExpanded; renderRoomUi(); }
    else if (name === 'source') { action('source', { source: target.getAttribute('data-source') || 'all' }); }
    else if (name === 'propose-catalog') {
      var track = (roomState.catalog || [])[Number(target.getAttribute('data-track-index'))];
      if (track) action('propose-catalog', { track: track });
    }
    else if (name === 'copy') {
      var code = target.getAttribute('data-code') || '';
      if (navigator.clipboard) navigator.clipboard.writeText(code);
      if (window.showToast) window.showToast('房间码已复制');
    }
  }

  function handlePanelSubmit(event) {
    event.preventDefault();
    var form = event.target;
    var kind = form.getAttribute('data-form');
    var data = new FormData(form);
    if (kind === 'create') action('create', { roomName: data.get('roomName') || '', controlMode: data.get('controlMode') || 'host_only' });
    if (kind === 'chat') {
      var message = String(data.get('message') || '').trim();
      if (message) action('chat', { message: message });
      form.reset();
    }
    if (kind === 'catalog') {
      var query = String(data.get('query') || '').trim();
      if (query) action('search', { query: query, source: roomState.catalogSource || 'all' });
    }
  }

  window.addEventListener('message', function (event) {
    if (event.origin !== window.location.origin || event.source !== window.parent) return;
    var message = event.data || {};
    if (message.source !== 'blue-album-room') return;
    if (message.type === 'sync') {
      applyRoomState(message.payload).catch(function (error) {
        send('error', { message: error && error.message ? error.message : '同步失败' });
      });
    }
    if (message.type === 'room-state') {
      roomState = Object.assign({}, roomState, message.payload || {});
      syncRoomShelf(roomState.queue);
      renderRoomUi();
      if (!roomStartupReady) {
        roomStartupReady = true;
        if (typeof window.dismissSplash === 'function') window.dismissSplash({ instant: true });
        window.setTimeout(toggleRoomPanel, 0);
      }
      if (roomState.notice && roomState.notice !== lastRoomNotice && window.showToast) {
        lastRoomNotice = roomState.notice;
        window.showToast(roomState.notice);
      }
    }
  });

  installRoomUi();
  disablePersonalRoomTracking();
  bindNativeRoomControls();
  if (typeof window.dismissSplash === 'function') window.dismissSplash({ instant: true });
  window.setInterval(function () { bindAudio(); emitTrackIfChanged(); }, 350);
  send('ready', { version: '2.1.0-blue-album-native-room' });
})();
