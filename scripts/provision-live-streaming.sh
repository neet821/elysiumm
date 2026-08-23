#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MEDIAMTX_VERSION="v1.18.2"
CONFIG_SOURCE="$ROOT_DIR/ops/live/mediamtx.yml"
UNIT_SOURCE="$ROOT_DIR/ops/live/blue-album-mediamtx.service"
NGINX_SOURCE="$ROOT_DIR/ops/live/nginx-live.conf"

check_assets() {
  test -s "$CONFIG_SOURCE"
  test -s "$UNIT_SOURCE"
  test -s "$NGINX_SOURCE"
  LIVE_CONFIG_ONLY=1 python3 "$ROOT_DIR/scripts/check-release-config.py"
}

if [[ "${1:-}" == "--check" ]]; then
  check_assets
  echo "Live streaming deployment assets are valid."
  exit 0
fi

if [[ "${1:-}" != "--install" ]]; then
  echo "Usage: $0 --check | --install" >&2
  exit 2
fi

if [[ "$(id -u)" -ne 0 ]]; then
  echo "--install must be run as root" >&2
  exit 2
fi

check_assets

case "$(uname -m)" in
  x86_64) release_arch="amd64" ;;
  aarch64|arm64) release_arch="arm64" ;;
  *)
    echo "Unsupported architecture: $(uname -m)" >&2
    exit 2
    ;;
esac

archive="mediamtx_${MEDIAMTX_VERSION}_linux_${release_arch}.tar.gz"
download_root="$(mktemp -d /tmp/blue-album-live.XXXXXX)"
cleanup() {
  if [[ "$download_root" == /tmp/blue-album-live.* ]]; then
    rm -rf -- "$download_root"
  fi
}
trap cleanup EXIT

curl --fail --location --silent --show-error \
  "https://github.com/bluenviron/mediamtx/releases/download/${MEDIAMTX_VERSION}/${archive}" \
  --output "$download_root/$archive"
curl --fail --location --silent --show-error \
  "https://github.com/bluenviron/mediamtx/releases/download/${MEDIAMTX_VERSION}/checksums.sha256" \
  --output "$download_root/checksums.sha256"
(
  cd "$download_root"
  grep "\\*${archive}$" checksums.sha256 | sha256sum --check -
  tar -xzf "$archive" mediamtx
  install -o root -g root -m 0755 mediamtx /usr/local/bin/mediamtx
)

if ! getent group blue-album-live >/dev/null; then
  groupadd --system blue-album-live
fi
if ! id blue-album-live >/dev/null 2>&1; then
  useradd --system --gid blue-album-live --home-dir /nonexistent \
    --shell /usr/sbin/nologin blue-album-live
fi
if ! id www-data >/dev/null 2>&1; then
  echo "The backend service user www-data is missing" >&2
  exit 2
fi
usermod -a -G blue-album-live www-data

install -d -o root -g blue-album-live -m 0750 /etc/blue-album
install -d -o blue-album-live -g blue-album-live -m 0750 \
  /srv/blue-album/live/recordings
install -o root -g blue-album-live -m 0640 \
  "$CONFIG_SOURCE" /etc/blue-album/mediamtx.yml
install -o root -g root -m 0644 \
  "$UNIT_SOURCE" /etc/systemd/system/blue-album-mediamtx.service
install -o root -g root -m 0644 \
  "$NGINX_SOURCE" /etc/nginx/snippets/blue-album-live.conf
if [[ ! -e /etc/blue-album/live.env ]]; then
  install -o root -g blue-album-live -m 0600 /dev/null /etc/blue-album/live.env
fi

systemctl daemon-reload
systemctl enable --now blue-album-mediamtx.service

echo "MediaMTX installed. Include /etc/nginx/snippets/blue-album-live.conf in the Blue Album server block, then validate and reload Nginx."
