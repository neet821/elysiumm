#!/usr/bin/env bash
set -euo pipefail

ROOT=${1:-/home/neet821/Downloads/testt}
API=${SPLAYER_API:-http://127.0.0.1:25884/api/netease}
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

declare -A IDS=(
  ["Frente! - Bizarre Love Triangle.flac"]=2587970
  ["许茹芸 - 泪海.flac"]=307594
  ["Elliott Smith - Between The Bars.flac"]=17566198
  ["Paramore - Ain't It Fun.flac"]=26197534
  ["Fiona Apple - Carrion.flac"]=17823137
)

for file in "${!IDS[@]}"; do
  input="$ROOT/$file"
  [[ -f "$input" ]] || { echo "missing: $input" >&2; exit 1; }
  id=${IDS[$file]}
  stem=${file%.flac}
  detail="$WORK/$id.detail.json"
  lyric="$WORK/$id.lyric.json"
  curl -fsS "$API/song/detail?ids=$id" -o "$detail"
  curl -fsS "$API/lyric/new?id=$id" -o "$lyric"

  title=$(jq -r '.songs[0].name' "$detail")
  artist=$(jq -r '.songs[0].ar | map(.name) | join(" / ")' "$detail")
  album=$(jq -r '.songs[0].al.name' "$detail")
  track=$(jq -r '.songs[0].no // 1' "$detail")
  disc=$(jq -r '.songs[0].disc // 1' "$detail")
  duration=$(jq -r '.songs[0].dt' "$detail")
  published=$(jq -r '.songs[0].publishTime // 0' "$detail")
  year=$(date -u -d "@$((published / 1000))" +%Y 2>/dev/null || true)
  [[ "$year" =~ ^[0-9]{4}$ ]] || year=""
  cover="$ROOT/$stem.jpg"
  cover_url=$(jq -r '.songs[0].al.picUrl' "$detail" | sed 's#^http:#https:#')
  curl -fsSL "$cover_url?param=1200y1200" -o "$cover"

  jq -r '.lrc.lyric // ""' "$lyric" > "$ROOT/$stem.lrc"
  jq -r '.tlyric.lyric // ""' "$lyric" > "$ROOT/$stem.translation.lrc"
  jq -c '{id:(.id // null), yrc:(.yrc.lyric // ""), klyric:(.klyric.lyric // "")}' "$lyric" > "$ROOT/$stem.yrc.json"
  jq -n --argjson id "$id" --arg title "$title" --arg artist "$artist" --arg album "$album" \
    --argjson track "$track" --argjson disc "$disc" --arg year "$year" --argjson duration_ms "$duration" \
    '{splayer_id:$id,title:$title,artist:$artist,album:$album,track_number:$track,disc_number:$disc,release_year:$year,duration_ms:$duration_ms}' \
    > "$ROOT/$stem.metadata.json"

  # Keep the original audio stream untouched; only add metadata and cover.
  metaflac --remove-tag=TITLE --remove-tag=ARTIST --remove-tag=ALBUM --remove-tag=TRACKNUMBER \
    --remove-tag=DISCNUMBER --remove-tag=DATE --remove-tag=SPLAYER_ID --remove-tag=LYRICS \
    --remove-tag=TRANSLATION --remove-tag=COMMENT "$input"
  metaflac --set-tag="TITLE=$title" --set-tag="ARTIST=$artist" --set-tag="ALBUM=$album" \
    --set-tag="TRACKNUMBER=$track" --set-tag="DISCNUMBER=$disc" --set-tag="SPLAYER_ID=$id" \
    --set-tag="MUSICBRAINZ_TRACKID=splayer:$id" --set-tag="COMMENT=Elysium fixed test catalog" \
    ${year:+--set-tag="DATE=$year"} --set-tag-from-file="LYRICS=$ROOT/$stem.lrc" \
    --set-tag-from-file="TRANSLATION=$ROOT/$stem.translation.lrc" --import-picture-from="$cover" "$input"

  actual=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$input")
  python3 - "$actual" "$duration" <<'PY'
import sys
actual=float(sys.argv[1]); expected=float(sys.argv[2])/1000
if abs(actual-expected) > 0.01:
    raise SystemExit(f'duration changed: {actual} vs {expected}')
PY
  metaflac --list --block-type=STREAMINFO,VORBIS_COMMENT,PICTURE "$input" >/dev/null
  printf 'prepared %s (%s)\n' "$stem" "$id"
done

find "$ROOT" -maxdepth 1 -type f \( -name '*.flac' -o -name '*.jpg' -o -name '*.lrc' -o -name '*.json' \) -print0 \
  | sort -z | xargs -0 sha256sum > "$ROOT/SHA256SUMS"
printf 'wrote %s/SHA256SUMS\n' "$ROOT"
