(function () {
  'use strict';

  var state = {
    audio: new Audio(),
    queue: [],
    index: -1,
    playing: false,
    searchTimer: 0,
    searchRequest: 0,
    trackGeneration: 0,
    lyricRevision: 0,
    lyrics: [],
    lyricIndex: -1,
    settings: { size: 25, lineHeight: 1.45 },
    previousVolume: 0.8,
    statusTimer: 0,
    backgroundRevision: 0,
    immersive: false,
    roomBridgeRequested: false,
    trackController: null,
    lyricController: null
  };

  state.audio.preload = 'metadata';
  state.audio.setAttribute('playsinline', '');
  state.audio.volume = state.previousVolume;

  function byId(id) { return document.getElementById(id); }
  function text(value) { return value == null ? '' : String(value); }
  function syncMobileRuntimeViewport() {
    var root = document.documentElement;
    if (!root) return;
    var visualHeight = window.visualViewport && window.visualViewport.height;
    var height = Math.round(window.innerHeight || visualHeight || 0);
    if (height > 0) root.style.setProperty('--mobile-runtime-viewport-height', height + 'px');
  }
  function installViewportLock() {
    syncMobileRuntimeViewport();
    window.addEventListener('resize', syncMobileRuntimeViewport, { passive: true });
    if (window.visualViewport) window.visualViewport.addEventListener('resize', syncMobileRuntimeViewport, { passive: true });
    document.addEventListener('touchmove', function (event) {
      var target = event.target;
      if (target && typeof target.closest === 'function' && target.closest('button, a, input, textarea, select, #search-results, #blue-room-panel, .br-body')) return;
      event.preventDefault();
    }, { passive: false });
  }
  function firstValue() {
    for (var i = 0; i < arguments.length; i++) {
      if (arguments[i] !== undefined && arguments[i] !== null && String(arguments[i]).trim()) return arguments[i];
    }
    return '';
  }
  function songTitle(song) { return text(firstValue(song && song.name, song && song.title, '未命名歌曲')); }
  function songArtist(song) { return text(firstValue(song && song.artist, song && song.singer, '未知音乐人')); }
  function songId(song) { return text(firstValue(song && song.id, song && song.mid, song && song.songmid, song && song.programId)); }
  function songCover(song) {
    return text(firstValue(song && song.picUrl, song && song.cover, song && song.artwork_url, song && song.albumPic, song && song.album && song.album.picUrl));
  }
  function isRoomMode() { return !!new URLSearchParams(location.search).get('blue-room'); }
  function routeRoomSearchSelection(song) {
    if (!isRoomMode()) return false;
    if (typeof window.__BLUE_ROOM_NATIVE_SEARCH_SELECT === 'function') return window.__BLUE_ROOM_NATIVE_SEARCH_SELECT(song) === true;
    showToast('房间正在加载，请稍后再点歌');
    return true;
  }
  function showToast(message) {
    var el = byId('mobile-runtime-status');
    if (!el) return;
    el.textContent = text(message);
    el.classList.add('is-visible');
    clearTimeout(state.statusTimer);
    state.statusTimer = setTimeout(function () { el.classList.remove('is-visible'); }, 2300);
  }
  function setPlaying(value) {
    state.playing = !!value;
    window.playing = state.playing;
    setPlayIcon(state.playing);
  }
  function setPlayIcon(playing) {
    var icon = byId('play-icon');
    if (!icon) return;
    while (icon.firstChild) icon.removeChild(icon.firstChild);
    var path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path.setAttribute('d', playing ? 'M7 5h3v14H7zm7 0h3v14h-3z' : 'M8 5v14l11-7z');
    icon.appendChild(path);
    var button = byId('play-btn');
    if (button) button.setAttribute('aria-label', playing ? '暂停' : '播放');
  }
  function setVolume(value) {
    var next = Math.max(0, Math.min(1, Number(value) || 0));
    state.audio.volume = next;
    state.audio.muted = next <= 0.01;
    if (next > 0.01) state.previousVolume = next;
    var slider = byId('volume-slider');
    if (slider) slider.value = String(next);
    var valueLabel = byId('volume-value');
    if (valueLabel) valueLabel.textContent = Math.round(next * 100) + '%';
    var volume = byId('volume-btn');
    if (volume) {
      var muted = next <= 0.01;
      volume.classList.toggle('is-muted', muted);
      volume.setAttribute('aria-pressed', muted ? 'true' : 'false');
      volume.setAttribute('aria-label', muted ? '取消静音' : '音量 / 静音');
      volume.title = muted ? '取消静音' : '音量 / 静音';
      var icon = byId('volume-icon');
      if (icon) icon.innerHTML = muted
        ? '<polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon><path d="m15 9 6 6m0-6-6 6"></path>'
        : '<polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon><path d="M15 9.5a4 4 0 0 1 0 5"></path>';
    }
  }
  function toggleMute() { setVolume(state.audio.volume > 0.01 ? 0 : (state.previousVolume || 0.8)); }
  function coverTarget(song) {
    var url = songCover(song);
    if (!url) return '';
    return /^https?:\/\//i.test(url) ? mobileApiUrl('/api/cover?url=' + encodeURIComponent(url)) : url;
  }
  function mobileRuntimeRgbCss(rgb) {
    return 'rgb(' + rgb.map(function (value) { return Math.round(value); }).join(', ') + ')';
  }
  function mobileRuntimeMixRgb(first, second, amount) {
    return first.map(function (value, index) { return value * (1 - amount) + second[index] * amount; });
  }
  function setMobileRuntimeBackground(primary, secondary, base, glow) {
    var root = document.documentElement;
    if (!root) return;
    root.style.setProperty('--mobile-runtime-bg-primary', mobileRuntimeRgbCss(primary));
    root.style.setProperty('--mobile-runtime-bg-secondary', mobileRuntimeRgbCss(secondary));
    root.style.setProperty('--mobile-runtime-bg-base', mobileRuntimeRgbCss(base));
    root.style.setProperty('--mobile-runtime-bg-glow', mobileRuntimeRgbCss(glow));
  }
  function resetMobileRuntimeBackground() {
    setMobileRuntimeBackground([24, 20, 28], [13, 13, 18], [5, 6, 10], [87, 62, 80]);
  }
  function updateMobileRuntimeBackground(url) {
    var revision = ++state.backgroundRevision;
    resetMobileRuntimeBackground();
    if (!url || typeof Image !== 'function') return;
    var image = new Image();
    image.crossOrigin = 'anonymous';
    image.onload = function () {
      if (revision !== state.backgroundRevision) return;
      try {
        var canvas = document.createElement('canvas');
        canvas.width = 32;
        canvas.height = 32;
        var context = canvas.getContext('2d', { willReadFrequently: true });
        if (!context) return;
        context.drawImage(image, 0, 0, canvas.width, canvas.height);
        var pixels = context.getImageData(0, 0, canvas.width, canvas.height).data;
        var average = [0, 0, 0];
        var vivid = [0, 0, 0];
        var totalCount = 0;
        var vividCount = 0;
        for (var i = 0; i < pixels.length; i += 16) {
          var red = pixels[i];
          var green = pixels[i + 1];
          var blue = pixels[i + 2];
          var max = Math.max(red, green, blue);
          var min = Math.min(red, green, blue);
          var saturation = max ? (max - min) / max : 0;
          var luminance = (red * 0.2126 + green * 0.7152 + blue * 0.0722) / 255;
          average[0] += red; average[1] += green; average[2] += blue; totalCount += 1;
          if (saturation > 0.12 && luminance > 0.08) {
            vivid[0] += red; vivid[1] += green; vivid[2] += blue; vividCount += 1;
          }
        }
        if (!totalCount) return;
        average = average.map(function (value) { return value / totalCount; });
        var primary = (vividCount ? vivid.map(function (value) { return value / vividCount; }) : average);
        var secondary = mobileRuntimeMixRgb(primary, average, 0.42);
        var base = mobileRuntimeMixRgb(primary, [5, 6, 10], 0.78);
        var glow = mobileRuntimeMixRgb(primary, [255, 255, 255], 0.34);
        setMobileRuntimeBackground(primary, secondary, base, glow);
      } catch (_) {}
    };
    image.src = url;
  }
  function mobileLyricMeasure(value) {
    return Array.from(text(value)).reduce(function (total, character) {
      return total + (/[^\x00-\xff]/.test(character) ? 1 : 0.56);
    }, 0);
  }
  function fitMobileLyricTypography() {
    var surface = byId('mobile-runtime-lyrics');
    if (!surface) return;
    var width = Math.max(220, surface.clientWidth - 24);
    var baseSize = Math.max(18, Number(state.settings.size) || 25);
    surface.querySelectorAll('.mobile-runtime-lyric-line').forEach(function (line) {
      var original = line.querySelector('.mobile-runtime-lyric-original');
      var units = mobileLyricMeasure(original && original.textContent);
      var estimatedWidth = units * baseSize;
      var scale = estimatedWidth > width * 1.55 ? (width * 1.55) / estimatedWidth : 1;
      line.style.setProperty('--mobile-runtime-line-scale', String(Math.max(0.72, Math.min(1, scale))));
    });
  }
  function updateTrackUi(song) {
    var title = byId('control-title-text');
    var artist = byId('control-artist');
    var cover = byId('control-cover');
    if (title) title.textContent = song ? songTitle(song) : '';
    if (artist) artist.textContent = song ? songArtist(song) : '';
    if (cover) {
      var url = coverTarget(song);
      cover.style.backgroundImage = url ? 'url("' + url.replace(/"/g, '%22') + '")' : '';
      cover.classList.toggle('cover-empty', !url);
      updateMobileRuntimeBackground(url);
    }
  }
  function syncGlobals() {
    window.playQueue = state.queue;
    window.currentIdx = state.index;
    window.currentLocalSong = null;
    window.audio = state.audio;
    window.trackSwitchToken = state.trackGeneration;
  }
  function setupGlobalCompat() {
    try {
      Object.defineProperty(window, 'playQueue', {
        configurable: true,
        get: function () { return state.queue; },
        set: function (value) { state.queue = Array.isArray(value) ? value : []; }
      });
      Object.defineProperty(window, 'currentIdx', {
        configurable: true,
        get: function () { return state.index; },
        set: function (value) { state.index = Number.isFinite(Number(value)) ? Number(value) : -1; }
      });
      Object.defineProperty(window, 'audio', {
        configurable: true,
        get: function () { return state.audio; },
        set: function () {}
      });
      Object.defineProperty(window, 'playing', {
        configurable: true,
        get: function () { return state.playing; },
        set: function (value) { state.playing = !!value; setPlayIcon(state.playing); }
      });
    } catch (_) {}
    syncGlobals();
  }
  function apiJson(url, options) {
    options = options || {};
    var controller = typeof AbortController === 'function' ? new AbortController() : null;
    var timeout = setTimeout(function () { if (controller) controller.abort(); }, options.timeoutMs || 14000);
    var apiUrl = mobileApiUrl(url);
    return fetch(apiUrl, { credentials: 'same-origin', signal: options.signal || (controller ? controller.signal : undefined) })
      .then(function (response) {
        if (!response.ok) throw new Error('请求失败：' + response.status);
        return response.json();
      })
      .finally(function () { clearTimeout(timeout); });
  }
  function mobileApiUrl(url) {
    var path = text(url);
    if (path.indexOf('/api/') !== 0) return path;
    var isMineradioMount = location.pathname.indexOf('/mineradio/') === 0 || new URLSearchParams(location.search).get('blue-room');
    return isMineradioMount ? '/mineradio-api/' + path.slice(5) : path;
  }
  function extractAudioUrl(payload) {
    var data = payload && payload.data;
    if (Array.isArray(data)) data = data[0];
    return text(firstValue(
      payload && payload.url,
      data && data.url,
      payload && payload.audioUrl,
      payload && payload.src,
      data && data.src
    ));
  }
  function lyricTextFromPayload(payload, key) {
    var value = payload && (payload[key] || (payload.data && payload.data[key]));
    if (value && typeof value === 'object') value = value.lyric || value.lrc || value.text;
    return text(value);
  }
  function parseTime(min, sec, fraction) {
    var value = (Number(min) || 0) * 60 + (Number(sec) || 0);
    if (fraction) value += Number('0.' + fraction);
    return value;
  }
  function parseLyrics(raw, translationRaw) {
    var lines = [];
    var translation = {};
    text(translationRaw).split(/\r?\n/).forEach(function (line) {
      var match = line.match(/^\s*\[(\d{1,3}):(\d{1,2})(?:[.:](\d{1,3}))?\](.*)$/);
      if (match) translation[parseTime(match[1], match[2], match[3])] = text(match[4]).trim();
    });
    text(raw).split(/\r?\n/).forEach(function (line) {
      var tags = [], match, re = /\[(\d{1,3}):(\d{1,2})(?:[.:](\d{1,3}))?\]/g;
      while ((match = re.exec(line))) tags.push({ time: parseTime(match[1], match[2], match[3]), end: re.lastIndex });
      if (!tags.length) return;
      var lyric = line.replace(/\[[^\]]+\]/g, '').trim();
      if (!lyric) return;
      tags.forEach(function (tag) {
        var translated = translation[tag.time];
        lines.push({ time: tag.time, text: lyric, translation: translated || '' });
      });
    });
    if (!lines.length) {
      text(raw).split(/\r?\n/).forEach(function (line) {
        var yrc = line.match(/^\[(\d+),(\d+)\](.*)$/);
        if (!yrc) return;
        var body = yrc[3] || '';
        var words = [], wordMatch, wordReg = /\((\d+),(\d+),\d+\)([^()]*)/g;
        while ((wordMatch = wordReg.exec(body))) {
          var word = text(wordMatch[3]).replace(/\s+/g, ' ');
          if (word) words.push(word);
        }
        var fallback = body.replace(/\(\d+,\d+,\d+\)/g, '').replace(/\s+/g, ' ').trim();
        var lyric = (words.join('') || fallback).trim();
        if (lyric) lines.push({ time: (Number(yrc[1]) || 0) / 1000, text: lyric, translation: '' });
      });
    }
    lines.sort(function (a, b) { return a.time - b.time; });
    return lines;
  }
  function lyricEndpoint(song) { return '/api/lyric?id=' + encodeURIComponent(songId(song)); }
  function positionMobileLyrics() {
    var surface = byId('mobile-runtime-lyrics');
    if (!surface || !state.lyrics.length) return;
    var track = surface.querySelector('.mobile-runtime-lyric-track');
    if (!track) return;
    var activeIndex = state.lyricIndex >= 0 ? state.lyricIndex : 0;
    var current = track.children[activeIndex];
    if (!current) return;
    var lyricShift = Math.round(surface.clientHeight / 2 - (current.offsetTop + current.offsetHeight / 2));
    track.style.transform = 'translate3d(0,' + lyricShift + 'px,0)';
  }
  function updateMobileLyricPresentation() {
    var surface = byId('mobile-runtime-lyrics');
    if (!surface) return;
    var lines = surface.querySelectorAll('.mobile-runtime-lyric-line');
    for (var i = 0; i < lines.length; i++) {
      lines[i].classList.toggle('is-current', i === state.lyricIndex);
      lines[i].classList.toggle('is-near', Math.abs(i - state.lyricIndex) === 1);
    }
    positionMobileLyrics();
  }
  function renderMobileLyrics() {
    var surface = byId('mobile-runtime-lyrics');
    if (!surface) return;
    while (surface.firstChild) surface.removeChild(surface.firstChild);
    if (!state.lyrics.length) {
      var empty = document.createElement('div');
      empty.className = 'mobile-runtime-empty';
      empty.textContent = state.index >= 0 ? '暂无歌词' : '搜索一首歌开始播放';
      surface.appendChild(empty);
      return;
    }
    var track = document.createElement('div');
    track.className = 'mobile-runtime-lyric-track';
    for (var i = 0; i < state.lyrics.length; i++) {
      var lyric = state.lyrics[i];
      var line = document.createElement('div');
      line.className = 'mobile-runtime-lyric-line';
      line.setAttribute('data-lyric-index', String(i));
      if (i === state.lyricIndex) line.classList.add('is-current');
      if (Math.abs(i - state.lyricIndex) === 1) line.classList.add('is-near');
      var original = document.createElement('span');
      original.className = 'mobile-runtime-lyric-original';
      original.textContent = lyric.text;
      line.appendChild(original);
      if (lyric.translation) {
        var translated = document.createElement('span');
        translated.className = 'mobile-runtime-lyric-translation';
        translated.textContent = lyric.translation;
        line.appendChild(translated);
      }
      track.appendChild(line);
    }
    surface.appendChild(track);
    fitMobileLyricTypography();
    positionMobileLyrics();
  }
  function updateLyricCursor(force) {
    var time = Number(state.audio.currentTime || 0);
    var next = -1;
    for (var i = 0; i < state.lyrics.length; i++) {
      if (state.lyrics[i].time <= time + 0.04) next = i;
      else break;
    }
    if (!force && next === state.lyricIndex) return;
    state.lyricIndex = next;
    updateMobileLyricPresentation();
  }
  function setLyrics(lines, generation) {
    if (generation !== state.trackGeneration) return;
    state.lyrics = Array.isArray(lines) ? lines : [];
    state.lyricRevision += 1;
    state.lyricIndex = -1;
    renderMobileLyrics();
    updateLyricCursor(true);
  }
  function loadLyrics(song, generation) {
    if (!songId(song)) { setLyrics([], generation); return; }
    if (state.lyricController) state.lyricController.abort();
    state.lyricController = typeof AbortController === 'function' ? new AbortController() : null;
    apiJson(lyricEndpoint(song), { timeoutMs: 7000, signal: state.lyricController && state.lyricController.signal }).then(function (payload) {
      if (generation !== state.trackGeneration) return;
      var raw = lyricTextFromPayload(payload, 'lyric') || lyricTextFromPayload(payload, 'lrc');
      var translated = lyricTextFromPayload(payload, 'tlyric') || lyricTextFromPayload(payload, 'translation');
      setLyrics(parseLyrics(raw, translated), generation);
    }).catch(function () { if (generation === state.trackGeneration) setLyrics([], generation); });
  }
  function updateProgress() {
    var duration = Number(state.audio.duration || 0);
    var current = Number(state.audio.currentTime || 0);
    var ratio = duration > 0 ? Math.max(0, Math.min(1, current / duration)) : 0;
    var fill = byId('progress-fill');
    var time = byId('time-display');
    if (fill) fill.style.width = (ratio * 100) + '%';
    if (time) time.textContent = formatTime(current) + ' / ' + formatTime(duration);
    updateLyricCursor(false);
  }
  function formatTime(value) {
    value = Math.max(0, Number(value) || 0);
    var minutes = Math.floor(value / 60);
    var seconds = Math.floor(value % 60);
    return minutes + ':' + String(seconds).padStart(2, '0');
  }
  function requestPlaybackUrl(song, signal) {
    if (song && song.roomStreamUrl) return Promise.resolve(song.roomStreamUrl);
    if (song && song.localUrl) return Promise.resolve(song.localUrl);
    return apiJson('/api/song/url?id=' + encodeURIComponent(songId(song)) + '&quality=exhigh', { timeoutMs: 14000, signal: signal })
      .then(extractAudioUrl);
  }
  function loadTrack(song, options) {
    options = options || {};
    if (!song) return Promise.resolve(false);
    if (state.trackController) state.trackController.abort();
    state.trackController = typeof AbortController === 'function' ? new AbortController() : null;
    var generation = ++state.trackGeneration;
    state.index = Math.max(0, state.queue.indexOf(song));
    if (state.index < 0) { state.queue = [song]; state.index = 0; }
    syncGlobals();
    updateTrackUi(song);
    setLyrics([], generation);
    state.audio.pause();
    state.audio.removeAttribute('src');
    state.audio.load();
    return requestPlaybackUrl(song, state.trackController && state.trackController.signal).then(function (url) {
      if (generation !== state.trackGeneration) return false;
      if (!url) throw new Error('没有可播放的音频地址');
      state.audio.src = url;
      if (options.resumeAt != null) state.audio.currentTime = Math.max(0, Number(options.resumeAt) || 0);
      return state.audio.play().then(function () {
        setPlaying(true);
        loadLyrics(song, generation);
        return true;
      });
    }).catch(function (error) {
      if (generation !== state.trackGeneration) return false;
      setPlaying(false);
      showToast(error && error.name === 'NotAllowedError' ? '点击播放以启用声音' : (error.message || '歌曲暂时无法播放'));
      loadLyrics(song, generation);
      return false;
    });
  }
  function playQueueAt(index, options) {
    var song = state.queue[Number(index)];
    if (!song) return Promise.resolve(false);
    state.index = Number(index);
    syncGlobals();
    return loadTrack(song, options);
  }
  function togglePlay() {
    if (state.index < 0) return showToast('先搜索并选择一首歌');
    if (state.audio.paused) {
      state.audio.play().then(function () { setPlaying(true); }).catch(function () { showToast('点击播放以启用声音'); });
    } else {
      state.audio.pause();
      setPlaying(false);
    }
  }
  function nextTrack(force) {
    if (!state.queue.length) return false;
    return playQueueAt((state.index + 1 + state.queue.length) % state.queue.length, { userAction: !!force });
  }
  function prevTrack(force) {
    if (!state.queue.length) return false;
    return playQueueAt((state.index - 1 + state.queue.length) % state.queue.length, { userAction: !!force });
  }
  function queueSong(song) {
    if (!song) return;
    var existing = state.queue.some(function (item) { return songId(item) === songId(song); });
    if (!existing) state.queue.push(song);
    if (state.index < 0) playQueueAt(state.queue.indexOf(song));
    else showToast(existing ? '歌曲已在队列中' : '已加入队列');
    syncGlobals();
  }
  function renderSearchResults(songs) {
    var results = byId('search-results');
    if (!results) return;
    while (results.firstChild) results.removeChild(results.firstChild);
    if (!songs.length) {
      var empty = document.createElement('div');
      empty.className = 'mobile-runtime-search-meta';
      empty.textContent = '没有找到相关歌曲';
      results.appendChild(empty);
      results.classList.add('show');
      return;
    }
    songs.slice(0, 18).forEach(function (song) {
      var row = document.createElement('div');
      row.className = 'mobile-runtime-search-result';
      row.tabIndex = 0;
      var image = document.createElement('img');
      image.className = 'mobile-runtime-search-cover';
      image.alt = '';
      image.loading = 'lazy';
      image.src = coverTarget(song);
      image.onerror = function () { image.removeAttribute('src'); };
      var copy = document.createElement('div');
      copy.className = 'mobile-runtime-search-copy';
      var title = document.createElement('strong');
      title.className = 'mobile-runtime-search-title';
      title.textContent = songTitle(song);
      var meta = document.createElement('span');
      meta.className = 'mobile-runtime-search-meta';
      meta.textContent = songArtist(song) + (song.album ? '  ·  ' + text(song.album) : '');
      copy.appendChild(title);
      copy.appendChild(meta);
      var add = document.createElement('button');
      add.className = 'mobile-runtime-search-add';
      add.type = 'button';
      add.textContent = '+';
      add.title = '加入队列';
      add.addEventListener('click', function (event) { event.stopPropagation(); if (!routeRoomSearchSelection(song)) queueSong(song); });
      row.appendChild(image);
      row.appendChild(copy);
      row.appendChild(add);
      row.addEventListener('click', function () {
        if (routeRoomSearchSelection(song)) {
          results.classList.remove('show');
          return;
        }
        state.queue = [song].concat(state.queue.filter(function (item) { return songId(item) !== songId(song); }));
        state.index = 0;
        syncGlobals();
        byId('search-results').classList.remove('show');
        loadTrack(song);
      });
      row.addEventListener('keydown', function (event) { if (event.key === 'Enter') row.click(); });
      results.appendChild(row);
    });
    results.classList.add('show');
  }
  function search(query) {
    query = text(query).trim();
    if (!query) return;
    var request = ++state.searchRequest;
    showToast('正在搜索');
    apiJson('/api/search?keywords=' + encodeURIComponent(query) + '&limit=18', { timeoutMs: 9000 }).then(function (payload) {
      if (request !== state.searchRequest) return;
      renderSearchResults(Array.isArray(payload && payload.songs) ? payload.songs : (Array.isArray(payload && payload.result) ? payload.result : []));
    }).catch(function () { if (request === state.searchRequest) { renderSearchResults([]); showToast('搜索暂时失败'); } });
  }
  function installSearch() {
    var input = byId('search-input');
    var results = byId('search-results');
    if (!input || !results) return;
    input.placeholder = '搜索网易云音乐…';
    input.addEventListener('input', function () {
      clearTimeout(state.searchTimer);
      var value = input.value;
      state.searchTimer = setTimeout(function () { if (value.trim()) search(value); }, 280);
    });
    input.addEventListener('keydown', function (event) { if (event.key === 'Enter') { event.preventDefault(); search(input.value); } });
    input.addEventListener('focus', function () { if (results.childElementCount) results.classList.add('show'); });
    document.addEventListener('click', function (event) {
      if (!byId('search-area').contains(event.target)) results.classList.remove('show');
    });
  }
  function createRoomButton() {
    if (new URLSearchParams(location.search).get('blue-room')) return;
    var top = byId('top-right');
    if (!top || byId('mobile-room-btn')) return;
    top.classList.add('mobile-runtime-top');
    var button = document.createElement('button');
    button.id = 'mobile-room-btn';
    button.className = 'icon-btn';
    button.type = 'button';
    button.title = '听歌房';
    button.setAttribute('aria-label', '听歌房');
    var svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('width', '19'); svg.setAttribute('height', '19'); svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('fill', 'none'); svg.setAttribute('stroke', 'currentColor'); svg.setAttribute('stroke-width', '1.9');
    svg.innerHTML = '<path d="M9 18H5a3 3 0 0 1-3-3v-1a4 4 0 0 1 4-4h3"/><circle cx="7" cy="6" r="3"/><path d="M15 18h4a3 3 0 0 0 3-3v-1a4 4 0 0 0-4-4h-3"/><circle cx="17" cy="6" r="3"/><path d="M9 14h6v7H9z"/>';
    button.appendChild(svg);
    button.addEventListener('click', function () { location.href = '/rooms/music'; });
    top.appendChild(button);
  }
  function installLyricSettings() {
    var stage = byId('mobile-2d-stage');
    var legacyButton = byId('mobile-lyric-settings-btn');
    if (!stage || !legacyButton) return;
    var top = byId('top-right'); if (top) top.classList.add('mobile-runtime-top');
    stage.classList.add('mobile-runtime-stage');
    var surface = document.createElement('div');
    surface.id = 'mobile-runtime-lyrics';
    surface.className = 'mobile-runtime-lyrics';
    var tools = document.createElement('div');
    tools.className = 'mobile-runtime-lyric-tools';
    legacyButton.removeAttribute('onclick');
    legacyButton.title = '歌词字体与排版';
    legacyButton.style.display = 'grid';
    tools.appendChild(legacyButton);
    var settings = document.createElement('section');
    settings.className = 'mobile-runtime-lyric-settings';
    settings.hidden = true;
    settings.setAttribute('aria-label', '歌词字体与排版');
    var heading = document.createElement('h2'); heading.textContent = '字体与排版'; settings.appendChild(heading);
    [['字号', 'size', 18, 42, 1, state.settings.size + 'px'], ['行距', 'lineHeight', 1.15, 2, .05, state.settings.lineHeight.toFixed(2)]]
      .forEach(function (item) {
        var row = document.createElement('label'); row.className = 'mobile-runtime-setting-row';
        var name = document.createElement('span'); name.textContent = item[0];
        var input = document.createElement('input'); input.type = 'range'; input.min = item[2]; input.max = item[3]; input.step = item[4]; input.value = state.settings[item[1]];
        var value = document.createElement('span'); value.className = 'mobile-runtime-setting-value'; value.textContent = item[5];
        input.addEventListener('input', function () { state.settings[item[1]] = Number(input.value); value.textContent = item[1] === 'size' ? input.value + 'px' : Number(input.value).toFixed(2); applyLyricSettings(); });
        row.appendChild(name); row.appendChild(input); row.appendChild(value); settings.appendChild(row);
      });
    tools.appendChild(settings);
    stage.appendChild(surface);
    stage.appendChild(tools);
    stage.addEventListener('click', function () {
      if (state.immersive) setMobileRuntimeImmersive(false);
    });
    document.addEventListener('keydown', function (event) {
      if (state.immersive && event.key === 'Escape') setMobileRuntimeImmersive(false);
    });
    window.addEventListener('resize', function () { fitMobileLyricTypography(); positionMobileLyrics(); }, { passive: true });
    legacyButton.addEventListener('click', function (event) { event.preventDefault(); event.stopPropagation(); settings.hidden = !settings.hidden; });
    applyLyricSettings();
  }
  function applyLyricSettings() {
    var surface = byId('mobile-runtime-lyrics');
    if (!surface) return;
    surface.style.setProperty('--mobile-runtime-lyric-size', state.settings.size + 'px');
    surface.style.setProperty('--mobile-runtime-lyric-line-height', String(state.settings.lineHeight));
    fitMobileLyricTypography();
    positionMobileLyrics();
  }
  function updateImmersiveButton(button, active) {
    if (!button) return;
    button.classList.toggle('active', active);
    button.setAttribute('aria-pressed', active ? 'true' : 'false');
    button.setAttribute('aria-label', active ? '退出沉浸式' : '沉浸式');
    button.title = active ? '退出沉浸式' : '沉浸式';
  }
  function createImmersiveExitButton(immersive) {
    if (!immersive || byId('mobile-runtime-immersive-exit')) return;
    var exitButton = immersive.cloneNode(true);
    exitButton.id = 'mobile-runtime-immersive-exit';
    exitButton.classList.add('mobile-runtime-immersive-exit');
    exitButton.removeAttribute('onclick');
    exitButton.addEventListener('click', function (event) {
      event.preventDefault();
      event.stopPropagation();
      setMobileRuntimeImmersive(!state.immersive);
    });
    document.body.appendChild(exitButton);
  }
  function setMobileRuntimeImmersive(value) {
    state.immersive = !!value;
    document.body.classList.toggle('mobile-runtime-immersive', state.immersive);
    updateImmersiveButton(byId('immersive-btn'), state.immersive);
    updateImmersiveButton(byId('mobile-runtime-immersive-exit'), state.immersive);
  }
  function installControls() {
    var bottom = byId('bottom-bar');
    if (!bottom) return;
    bottom.classList.add('mobile-runtime-controls');
    [['play-btn', togglePlay], ['prev-btn', prevTrack], ['next-btn', nextTrack]].forEach(function (entry) {
      var button = byId(entry[0]);
      if (!button) return;
      button.removeAttribute('onclick');
      button.addEventListener('click', function (event) { event.preventDefault(); entry[1](true); });
    });
    var volume = byId('volume-btn');
    var volumeControl = byId('volume-control');
    if (volume) {
      volume.removeAttribute('onclick');
      volume.addEventListener('click', function (event) {
        event.preventDefault();
        event.stopPropagation();
        toggleMute();
        if (volumeControl) volumeControl.classList.toggle('is-open');
      });
    }
    if (volumeControl) {
      volumeControl.addEventListener('click', function (event) { event.stopPropagation(); });
      document.addEventListener('click', function () { volumeControl.classList.remove('is-open'); });
    }
    var immersive = byId('immersive-btn');
    if (immersive) {
      immersive.removeAttribute('onclick');
      immersive.addEventListener('click', function (event) {
        event.preventDefault();
        event.stopPropagation();
        setMobileRuntimeImmersive(!state.immersive);
      });
      createImmersiveExitButton(immersive);
      setMobileRuntimeImmersive(false);
    }
    var slider = byId('volume-slider');
    if (slider) {
      slider.addEventListener('input', function () { setVolume(slider.value); });
      slider.addEventListener('change', function () { setVolume(slider.value); });
    }
    var transport = bottom.querySelector('.control-cluster.transport');
    if (transport && volumeControl) transport.appendChild(volumeControl);
    if (transport && immersive) transport.appendChild(immersive);
    ['control-cover', 'control-title', 'control-artist'].forEach(function (id) {
      var target = byId(id);
      if (!target) return;
      target.removeAttribute('onclick');
      target.removeAttribute('onkeydown');
    });
    var home = byId('home-btn');
    if (home) {
      home.removeAttribute('onclick');
      var homeIcon = home.querySelector('svg');
      if (homeIcon) homeIcon.innerHTML = '<path d="M19 12H5M11 18l-6-6 6-6" />';
      home.title = '返回';
      home.setAttribute('aria-label', '返回');
      home.addEventListener('click', function () { if (history.length > 1) history.back(); else location.href = '/'; });
    }
    setVolume(state.audio.volume);
  }
  function installAudio() {
    state.audio.addEventListener('play', function () { setPlaying(true); });
    state.audio.addEventListener('pause', function () { setPlaying(false); });
    state.audio.addEventListener('timeupdate', updateProgress, { passive: true });
    state.audio.addEventListener('loadedmetadata', updateProgress, { passive: true });
    state.audio.addEventListener('ended', function () { if (!isRoomMode()) nextTrack(false); });
  }
  function installCompatibility() {
    window.togglePlay = togglePlay;
    window.nextTrack = nextTrack;
    window.prevTrack = prevTrack;
    window.playQueueAt = playQueueAt;
    window.setPlayIcon = setPlayIcon;
    window.showToast = showToast;
    window.setSearchMode = function () {};
    window.dismissSplash = function () {};
    window.setOriginalLyricsState = function (lines) { setLyrics(Array.isArray(lines) ? lines : [], state.trackGeneration); };
    window.applyOriginalLyricsState = function () { renderMobileLyrics(); };
    window.beginListenSession = function () {};
    window.updateListenStatsTick = function () {};
    window.finalizeListenSession = function () {};
  }
  function boot() {
    document.body.classList.add('mobile-runtime-active', 'mobile-device', 'mobile-2d-ui');
    installViewportLock();
    var legacyStage = byId('mobile-2d-stage');
    if (legacyStage) {
      legacyStage.setAttribute('aria-label', '移动端歌词');
      var oldLyrics = byId('mobile-2d-lyrics'); if (oldLyrics) oldLyrics.remove();
      var oldEmpty = byId('mobile-2d-empty'); if (oldEmpty) oldEmpty.remove();
    }
    var status = document.createElement('div'); status.id = 'mobile-runtime-status'; status.className = 'mobile-runtime-status'; status.setAttribute('role', 'status'); status.setAttribute('aria-live', 'polite'); document.body.appendChild(status);
    setupGlobalCompat();
    installCompatibility();
    installSearch();
    installLyricSettings();
    installControls();
    installAudio();
    createRoomButton();
    renderMobileLyrics();
  }
  window.MineradioMobileRuntime = { boot: boot, state: state, renderMobileLyrics: renderMobileLyrics };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, { once: true });
  else boot();
})();
