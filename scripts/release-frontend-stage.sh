#!/usr/bin/env bash
# Source-only helpers for staging and reverting the static frontend tree.

FRONTEND_SWITCHED=0
STAGE_DIR=""
PREVIOUS_DIR=""
FAILED_DIR=""
STAGED_WEB_ROOT=""

prepare_staged_frontend() {
  local source_dir=${1:?source directory is required}
  local web_root=${2:?web root is required}
  local release_id=${3:?release id is required}
  local parent

  if [[ ! "$release_id" =~ ^[A-Za-z0-9_.-]+$ ]]; then
    echo "frontend-stage: unsafe release id" >&2
    return 1
  fi
  if [[ ! -d "$source_dir" || ! -d "$web_root" ]]; then
    echo "frontend-stage: source and current web root must be directories" >&2
    return 1
  fi
  source_dir=$(realpath "$source_dir")
  STAGED_WEB_ROOT=$(realpath "$web_root")
  parent=$(dirname "$STAGED_WEB_ROOT")
  PREVIOUS_DIR="$parent/.blue-album-previous-$release_id"
  FAILED_DIR="$parent/.blue-album-failed-$release_id"
  if [[ -e "$PREVIOUS_DIR" || -e "$FAILED_DIR" ]]; then
    echo "frontend-stage: release directories already exist" >&2
    return 1
  fi
  STAGE_DIR=$(mktemp -d "$parent/.blue-album-stage-${release_id}-XXXXXX")
  cp -a "$source_dir/." "$STAGE_DIR/"
  if [[ -d "$STAGED_WEB_ROOT/movie-rank" ]]; then
    cp -a "$STAGED_WEB_ROOT/movie-rank" "$STAGE_DIR/movie-rank"
  fi
  FRONTEND_SWITCHED=0
}

activate_staged_frontend() {
  if [[ -z "$STAGE_DIR" || -z "$STAGED_WEB_ROOT" || ! -d "$STAGE_DIR" ]]; then
    echo "frontend-stage: no prepared release" >&2
    return 1
  fi
  mv -- "$STAGED_WEB_ROOT" "$PREVIOUS_DIR"
  if ! mv -- "$STAGE_DIR" "$STAGED_WEB_ROOT"; then
    mv -- "$PREVIOUS_DIR" "$STAGED_WEB_ROOT"
    return 1
  fi
  FRONTEND_SWITCHED=1
}

restore_staged_frontend() {
  if [[ "$FRONTEND_SWITCHED" -ne 1 || -z "$PREVIOUS_DIR" || ! -d "$PREVIOUS_DIR" ]]; then
    return 0
  fi
  if [[ -e "$FAILED_DIR" ]]; then
    echo "frontend-stage: failed-release directory already exists" >&2
    return 1
  fi
  mv -- "$STAGED_WEB_ROOT" "$FAILED_DIR"
  if ! mv -- "$PREVIOUS_DIR" "$STAGED_WEB_ROOT"; then
    mv -- "$FAILED_DIR" "$STAGED_WEB_ROOT"
    return 1
  fi
  FRONTEND_SWITCHED=0
}

commit_staged_frontend() {
  local parent
  if [[ "$FRONTEND_SWITCHED" -ne 1 || -z "$PREVIOUS_DIR" ]]; then
    echo "frontend-stage: no active staged release" >&2
    return 1
  fi
  parent=$(dirname "$STAGED_WEB_ROOT")
  if [[ "$PREVIOUS_DIR" != "$parent/.blue-album-previous-"* ]]; then
    echo "frontend-stage: refusing unsafe cleanup path" >&2
    return 1
  fi
  if ! rm -rf -- "$PREVIOUS_DIR"; then
    return 1
  fi
  FRONTEND_SWITCHED=0
}
