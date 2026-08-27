var mobile2dLyricsState = { key: '', index: -1, visible: false };

function isMobile2dUi() {
  return !!(document.body && document.body.classList.contains('mobile-2d-ui'));
}

function mobile2dLyricValue(value) {
  return String(value == null ? '' : value).replace(/\s+/g, ' ').trim();
}

function mobile2dLyricLineAt(index) {
  if (typeof lyricsLines === 'undefined' || !Array.isArray(lyricsLines)) return null;
  if (index < 0 || index >= lyricsLines.length) return null;
  return lyricsLines[index] || null;
}

function mobile2dLyricStyle(stage) {
  var scale = Number(typeof fx !== 'undefined' && fx && fx.lyricScale);
  var lineHeight = Number(typeof fx !== 'undefined' && fx && fx.lyricLineHeight);
  var weight = Number(typeof fx !== 'undefined' && fx && fx.lyricWeight);
  stage.style.setProperty('--mobile-2d-lyric-scale', String(Math.max(0.72, Math.min(1.24, isFinite(scale) ? scale : 1))));
  stage.style.setProperty('--mobile-2d-lyric-line-height', String(Math.max(1.04, Math.min(1.65, isFinite(lineHeight) ? lineHeight : 1.18))));
  stage.style.setProperty('--mobile-2d-lyric-weight', String(Math.max(500, Math.min(900, isFinite(weight) ? weight : 720))));
}

function mobile2dAppendLyricRow(parent, line, role) {
  var text = mobile2dLyricValue(line && line.text);
  if (!text) return;
  var row = document.createElement('div');
  row.className = 'mobile-2d-lyric-row ' + role;
  row.textContent = text;
  if (role === 'current') {
    var translation = mobile2dLyricValue(line && line.translation);
    if (translation) {
      var translationEl = document.createElement('span');
      translationEl.className = 'mobile-2d-lyric-translation';
      translationEl.textContent = translation;
      row.appendChild(translationEl);
    }
  }
  parent.appendChild(row);
}

function updateMobile2dLyrics() {
  if (!isMobile2dUi()) return;
  var stage = document.getElementById('mobile-2d-stage');
  var lyrics = document.getElementById('mobile-2d-lyrics');
  var empty = document.getElementById('mobile-2d-empty');
  if (!stage || !lyrics || !empty) return;
  mobile2dLyricStyle(stage);

  var hasAudio = !!(typeof audio !== 'undefined' && audio && audio.src && !audio.ended);
  var lines = typeof lyricsLines !== 'undefined' && Array.isArray(lyricsLines) ? lyricsLines : [];
  var isPlaying = hasAudio && !audio.paused && (typeof playing === 'undefined' || playing !== false);
  var index = -1;
  if (isPlaying && lines.length) {
    var time = isFinite(Number(audio.currentTime)) ? Math.max(0, Number(audio.currentTime)) : 0;
    var adjustedTime = typeof getAdjustedLyricPlaybackTime === 'function' ? getAdjustedLyricPlaybackTime(time) : time;
    index = typeof findStageLyricIndexAtTime === 'function' ? findStageLyricIndexAtTime(adjustedTime) : -1;
  }
  var current = mobile2dLyricLineAt(index);
  var fallback = index < 0 && isPlaying && typeof currentLyricFallbackText === 'function'
    ? mobile2dLyricValue(currentLyricFallbackText())
    : '';
  var currentText = mobile2dLyricValue(current && current.text) || fallback;
  var key = [
    isPlaying ? 'playing' : 'idle',
    index,
    currentText,
    mobile2dLyricValue(current && current.translation),
    Number(typeof fx !== 'undefined' && fx && fx.lyricScale) || 1,
    Number(typeof fx !== 'undefined' && fx && fx.lyricLineHeight) || 1.18,
    Number(typeof fx !== 'undefined' && fx && fx.lyricWeight) || 720
  ].join('|');

  if (key !== mobile2dLyricsState.key) {
    lyrics.textContent = '';
    if (currentText) {
      mobile2dAppendLyricRow(lyrics, current || { text: currentText }, 'current');
      if (index >= 0) {
        mobile2dAppendLyricRow(lyrics, mobile2dLyricLineAt(index - 1), 'previous');
        mobile2dAppendLyricRow(lyrics, mobile2dLyricLineAt(index + 1), 'next');
      }
    }
    mobile2dLyricsState.key = key;
    mobile2dLyricsState.index = index;
  }

  var hasLyric = !!currentText;
  mobile2dLyricsState.visible = hasLyric;
  stage.classList.toggle('has-lyrics', hasLyric);
  empty.textContent = isPlaying ? (lines.length ? '歌词暂不可用' : '歌词载入中…') : '搜索一首歌开始播放';
}
