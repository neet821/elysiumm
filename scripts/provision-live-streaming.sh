#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MEDIAMTX_VERSION="v1.18.2"
CONFIG_SOURCE="$ROOT_DIR/deployment/live/mediamtx.yml"
UNIT_SOURCE="$ROOT_DIR/deployment/live/elysiumm-mediamtx.service"
NGINX_SOURCE="$ROOT_DIR/deployment/live/nginx-live.conf"
MEDIAMTX_INSTALL_DIR="/usr/local/libexec/elysium"

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

if ! getent group elysium-live >/dev/null; then
  groupadd --system elysium-live
fi
if ! id elysium-live >/dev/null 2>&1; then
  useradd --system --gid elysium-live --home-dir /nonexistent \
    --shell /usr/sbin/nologin elysium-live
fi
if ! id www-data >/dev/null 2>&1; then
  echo "The backend service user www-data is missing" >&2
  exit 2
fi

case "$(uname -m)" in
  x86_64) release_arch="amd64" ;;
  aarch64|arm64) release_arch="arm64" ;;
  *)
    echo "Unsupported architecture: $(uname -m)" >&2
    exit 2
    ;;
esac

archive="mediamtx_${MEDIAMTX_VERSION}_linux_${release_arch}.tar.gz"
download_root="$(mktemp -d /tmp/elysium-mediamtx.XXXXXX)"
cleanup() {
  if [[ "$download_root" == /tmp/elysium-mediamtx.* ]]; then
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
  install -d -o root -g elysium-live -m 0750 "$MEDIAMTX_INSTALL_DIR"
  install -o root -g root -m 0755 mediamtx "$MEDIAMTX_INSTALL_DIR/mediamtx"
)

install -d -o root -g root -m 0755 /etc/elysium
install -d -o elysium-live -g elysium-live -m 0750 \
  /srv/services/elysium/shared/uploads/live-recordings
install -o root -g elysium-live -m 0640 \
  "$CONFIG_SOURCE" /etc/elysium/mediamtx.yml
install -o root -g root -m 0644 \
  "$UNIT_SOURCE" /etc/systemd/system/elysiumm-mediamtx.service
install -o root -g root -m 0644 \
  "$NGINX_SOURCE" /etc/nginx/snippets/elysium-live.conf
if [[ ! -e /etc/elysium/mediamtx.env ]]; then
  install -o root -g root -m 0600 /dev/null /etc/elysium/mediamtx.env
fi

systemctl daemon-reload
systemctl enable --now elysiumm-mediamtx.service

echo "MediaMTX installed. Include /etc/nginx/snippets/elysium-live.conf in the Elysium server block, then validate and reload Nginx."
