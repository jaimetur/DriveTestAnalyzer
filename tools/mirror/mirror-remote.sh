#!/bin/bash
# Runs on the mirror Mac, called over SSH by tools/mirror/mirror-sync.sh of the development Mac (read
# tools/mirror/README.md): the Python environment and the launchd agent of the mirror application, and the
# databases each synchronization brings, applied while the application is stopped for a moment.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CONFIG_FILE="$HOME/.config/drivetest-analyzer/mirror-app.conf"
AGENT="com.drivetestanalyzer.mirror-app"
PLIST="$HOME/Library/LaunchAgents/$AGENT.plist"
APP_LOG="$HOME/Library/Logs/$AGENT.log"
PATH="/opt/homebrew/bin:/usr/local/bin:/Library/Frameworks/Python.framework/Versions/3.15/bin:$PATH"
USER_ID="$(id -u)"

log() {
  printf '[%s] mirror: %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >&2
}

die() {
  log "$*"
  exit 1
}

load_config() {
  [ -f "$CONFIG_FILE" ] || die "The mirror application is not installed on this Mac ($CONFIG_FILE is missing)."
  # shellcheck disable=SC1090
  . "$CONFIG_FILE"
  : "${MIRROR_STORAGE:?}" "${MIRROR_PORT:?}" "${MIRROR_LABEL:?}"
}

python_is_recent() {
  "$1" -c 'import sys; sys.exit(0 if sys.version_info[:2] >= (3, 15) else 1)' 2>/dev/null
}

install_dependencies() {
  log "Installing the Python dependencies"
  "$REPO/.venv/bin/python" -m pip install -q --upgrade pip > /dev/null 2>&1
  "$REPO/.venv/bin/python" -m pip install -q -r "$REPO/requirements.txt" || die "The Python dependencies could not be installed."
}

# The checkout runs from its own .venv on this Mac (Python 3.15), made here when it is missing or older.
ensure_venv() {
  if ! { [ -x "$REPO/.venv/bin/python" ] && python_is_recent "$REPO/.venv/bin/python"; }; then
    local base="" candidate
    for candidate in python3.15 /Library/Frameworks/Python.framework/Versions/3.15/bin/python3.15 /opt/homebrew/bin/python3.15; do
      if command -v "$candidate" > /dev/null 2>&1 && python_is_recent "$(command -v "$candidate")"; then
        base="$(command -v "$candidate")"
        break
      fi
    done
    [ -n "$base" ] || die "Python 3.15 is not installed on this Mac."
    [ -e "$REPO/.venv" ] && mv "$REPO/.venv" "$REPO/.venv.before-mirror-$(date +%Y%m%d-%H%M%S)"
    log "Creating the Python environment with $base"
    "$base" -m venv "$REPO/.venv" || die "The Python environment could not be created."
  fi
  install_dependencies
}

agent_loaded() {
  launchctl print "gui/$USER_ID/$AGENT" > /dev/null 2>&1
}

port_listening() {
  lsof -nP -iTCP:"$MIRROR_PORT" -sTCP:LISTEN > /dev/null 2>&1
}

# Another server of the application on the same port (the macOS launcher, a terminal) gives way to the mirror.
quit_other_servers() {
  port_listening || return 0
  log "Stopping the DriveTest Analyzer server that listens on port $MIRROR_PORT"
  osascript -e 'tell application "DriveTest Analyzer" to quit' > /dev/null 2>&1 || true
  local waited=0
  while port_listening && [ "$waited" -lt 30 ]; do
    sleep 1
    waited=$((waited + 1))
  done
  if port_listening; then
    lsof -nP -tiTCP:"$MIRROR_PORT" -sTCP:LISTEN | xargs kill 2>/dev/null || true
    sleep 3
  fi
  port_listening && die "Port $MIRROR_PORT is still taken on this Mac."
  osascript -e 'tell application "System Events" to delete login item "DriveTest Analyzer"' > /dev/null 2>&1 \
    || log "If DriveTest Analyzer is among the login items of this Mac, remove it: it would take port $MIRROR_PORT from the mirror after a restart."
}

stop_app() {
  if agent_loaded; then
    launchctl bootout "gui/$USER_ID/$AGENT" 2>/dev/null || true
  fi
  local waited=0
  while port_listening; do
    [ "$waited" -ge 60 ] && die "Something still listens on port $MIRROR_PORT a minute after stopping the mirror application."
    sleep 1
    waited=$((waited + 1))
  done
}

wait_for_answer() {
  local waited=0 code
  while [ "$waited" -lt 300 ]; do
    code="$(curl -s -o /dev/null -m 3 -w '%{http_code}' "http://127.0.0.1:$MIRROR_PORT/healthz" 2>/dev/null)"
    if [ -n "$code" ] && [ "$code" != "000" ]; then
      log "Mirror application up on port $MIRROR_PORT (/healthz $code)"
      return 0
    fi
    sleep 2
    waited=$((waited + 2))
  done
  die "The mirror application did not answer on port $MIRROR_PORT within five minutes (see $APP_LOG)."
}

start_app() {
  [ -f "$PLIST" ] || die "The agent of the mirror application is not installed ($PLIST is missing)."
  agent_loaded || launchctl bootstrap "gui/$USER_ID" "$PLIST" || die "launchd refused the agent $AGENT."
  wait_for_answer
}

xml_escape() {
  printf '%s' "$1" | sed -e 's/&/\&amp;/g' -e 's/</\&lt;/g' -e 's/>/\&gt;/g'
}

write_plist() {
  mkdir -p "$(dirname "$PLIST")" "$(dirname "$APP_LOG")"
  agent_loaded && launchctl bootout "gui/$USER_ID/$AGENT" 2>/dev/null
  cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$AGENT</string>
  <key>ProgramArguments</key>
  <array><string>$(xml_escape "$REPO")/.venv/bin/python</string><string>$(xml_escape "$REPO")/src/main.py</string></array>
  <key>WorkingDirectory</key><string>$(xml_escape "$REPO")</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    <key>HOME</key><string>$(xml_escape "$HOME")</string>
    <key>LANG</key><string>en_US.UTF-8</string>
    <key>APP_CONFIG_DIR</key><string>$(xml_escape "$MIRROR_STORAGE")/config</string>
    <key>APP_DATA_DIR</key><string>$(xml_escape "$MIRROR_STORAGE")/data</string>
    <key>DRIVETEST_ANALYZER_BIND_PORT</key><string>$MIRROR_PORT</string>
    <key>DRIVETEST_ANALYZER_MIRROR_OF</key><string>$(xml_escape "$MIRROR_LABEL")</string>
    <key>DRIVETEST_ANALYZER_DESIGN_WARMUP</key><string>0</string>
  </dict>
  <key>KeepAlive</key><true/>
  <key>RunAtLoad</key><true/>
  <key>ThrottleInterval</key><integer>10</integer>
  <key>StandardOutPath</key><string>$(xml_escape "$APP_LOG")</string>
  <key>StandardErrorPath</key><string>$(xml_escape "$APP_LOG")</string>
</dict>
</plist>
EOF
}

# install <storage> <port> <label> [--replace-data]: the environment, the storage folders and the agent (not
# started: the first synchronization starts it once it has applied the databases).
install_app() {
  local storage="${1:-}" port="${2:-}" label="${3:-}" replace=0
  [ "${4:-}" = "--replace-data" ] && replace=1
  [ -n "$storage" ] && [ -n "$port" ] && [ -n "$label" ] || die "install needs the storage folder, the port and the label."
  mkdir -p "$(dirname "$CONFIG_FILE")"
  printf 'MIRROR_STORAGE=%q\nMIRROR_PORT=%q\nMIRROR_LABEL=%q\n' "$storage" "$port" "$label" > "$CONFIG_FILE"
  load_config
  ensure_venv
  quit_other_servers
  if [ -d "$storage" ] && [ -n "$(ls -A "$storage" 2>/dev/null)" ] && [ ! -f "$storage/.mirror-storage" ]; then
    [ "$replace" -eq 1 ] || die "$storage already holds data of its own. Run install with --replace-mirror-data to set it aside (kept beside it, renamed) and take the data of the development Mac."
    local aside="$storage.before-mirror-$(date +%Y%m%d-%H%M%S)"
    mv "$storage" "$aside" || die "$storage could not be set aside."
    log "The data $storage held is kept in $aside"
  fi
  mkdir -p "$storage/config" "$storage/data" || die "The storage folders could not be created."
  date > "$storage/.mirror-storage"
  write_plist
  log "Mirror application installed; it starts when the first synchronization applies the databases."
}

# The databases the development Mac sent to .mirror-incoming replace those of the storage as APFS clones (an
# instant, whatever their size) while the application is stopped; databases it no longer has go.
apply_databases() {
  load_config
  local incoming="$MIRROR_STORAGE/.mirror-incoming" snapshot live relative applied=0 removed=0
  [ -d "$incoming" ] || die "There are no databases to apply ($incoming is missing)."
  stop_app
  while IFS= read -r snapshot; do
    [ -n "$snapshot" ] || continue
    relative="${snapshot#"$incoming"/}"
    live="$MIRROR_STORAGE/$relative"
    mkdir -p "$(dirname "$live")"
    rm -f "$live-wal" "$live-shm" "$live-journal"
    if ! cp -c "$snapshot" "$live.mirror-tmp" 2>/dev/null; then
      cp "$snapshot" "$live.mirror-tmp" || die "The database $relative could not be copied."
    fi
    mv -f "$live.mirror-tmp" "$live" || die "The database $relative could not be put in place."
    applied=$((applied + 1))
  done <<< "$(find "$incoming" -type f -name '*.db')"
  while IFS= read -r live; do
    [ -n "$live" ] || continue
    relative="${live#"$MIRROR_STORAGE"/}"
    if [ ! -f "$incoming/$relative" ]; then
      rm -f "$live" "$live-wal" "$live-shm" "$live-journal"
      removed=$((removed + 1))
    fi
  done <<< "$(find "$MIRROR_STORAGE/config" "$MIRROR_STORAGE/data" -type f -name '*.db' \
    -not -path '*/scheduled-backups/*' -not -path '*/.workspace-trash/*' -not -path '*/transfer-packages/*' -not -path '*/.cache/*' 2>/dev/null)"
  log "$applied databases applied, $removed removed."
  start_app
}

show_status() {
  load_config
  if agent_loaded; then echo "Agent $AGENT: loaded"; else echo "Agent $AGENT: not loaded"; fi
  echo "Application: $(curl -s -m 5 "http://127.0.0.1:$MIRROR_PORT/healthz" || echo 'not answering')"
  echo "Storage: $(du -sh "$MIRROR_STORAGE" 2>/dev/null | cut -f1) in $MIRROR_STORAGE"
  echo "Checkout: $(cd "$REPO" && git rev-parse --abbrev-ref HEAD 2>/dev/null) $(cd "$REPO" && git rev-parse --short HEAD 2>/dev/null)"
}

uninstall_app() {
  load_config
  stop_app
  rm -f "$PLIST" "$CONFIG_FILE"
  log "The agent of the mirror application is removed; the checkout and $MIRROR_STORAGE stay."
}

command="${1:-}"
[ $# -gt 0 ] && shift
case "$command" in
  install) install_app "$@" ;;
  deps) install_dependencies ;;
  apply) apply_databases ;;
  restart) load_config; stop_app; start_app ;;
  stop) load_config; stop_app ;;
  start) load_config; start_app ;;
  status) show_status ;;
  uninstall) uninstall_app ;;
  *) echo "Usage: mirror-remote.sh install <storage> <port> <label> [--replace-data] | deps | apply | restart | stop | start | status | uninstall" >&2; exit 1 ;;
esac
