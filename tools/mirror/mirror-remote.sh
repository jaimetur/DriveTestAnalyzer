#!/bin/bash
# Runs on the mirror Mac, called over SSH by tools/mirror/mirror-sync.sh of the development Mac (read
# tools/mirror/README.md): the Python environment of the checkout, what runs the mirror application (the macOS
# launcher the mirror already has, or a launchd agent), and the databases each synchronization brings, applied
# while the application is stopped for a moment.
set -u

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CONFIG_FILE="$HOME/.config/drivetest-analyzer/mirror-app.conf"
AGENT="com.drivetestanalyzer.mirror-app"
PLIST="$HOME/Library/LaunchAgents/$AGENT.plist"
APP_LOG="$HOME/Library/Logs/$AGENT.log"
LAUNCHER_ID="com.jaimetur.drivetestanalyzer.launcher"
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
  MIRROR_RUNNER="${MIRROR_RUNNER:-agent}"
  MIRROR_LAUNCHER="${MIRROR_LAUNCHER:-}"
}

python_is_recent() {
  "$1" -c 'import sys; sys.exit(0 if sys.version_info[:2] >= (3, 15) else 1)' 2>/dev/null
}

# A Python 3.15 to make the environment with: the one installed, else Homebrew's.
find_base_python() {
  local candidate
  for candidate in python3.15 /opt/homebrew/bin/python3.15 /Library/Frameworks/Python.framework/Versions/3.15/bin/python3.15 /usr/local/bin/python3.15; do
    if command -v "$candidate" > /dev/null 2>&1 && python_is_recent "$(command -v "$candidate")"; then
      command -v "$candidate"
      return 0
    fi
  done
  if command -v brew > /dev/null 2>&1; then
    log "Installing Python 3.15 with Homebrew"
    brew install python@3.15 > /dev/null 2>&1 || die "Python 3.15 could not be installed with Homebrew."
    if [ -x /opt/homebrew/bin/python3.15 ] && python_is_recent /opt/homebrew/bin/python3.15; then
      echo /opt/homebrew/bin/python3.15
      return 0
    fi
  fi
  die "Python 3.15 is not installed on this Mac."
}

install_dependencies() {
  log "Installing the Python dependencies"
  "$REPO/.venv/bin/python" -m pip install -q --upgrade pip > /dev/null 2>&1
  "$REPO/.venv/bin/python" -m pip install -q -r "$REPO/requirements.txt" || die "The Python dependencies could not be installed."
}

# The checkout runs from its own .venv on this Mac (Python 3.15, the one the macOS launcher reuses), made here
# when it is missing or older.
ensure_venv() {
  if ! { [ -x "$REPO/.venv/bin/python" ] && python_is_recent "$REPO/.venv/bin/python"; }; then
    local base
    base="$(find_base_python)" || exit 1
    [ -e "$REPO/.venv" ] && mv "$REPO/.venv" "$REPO/.venv.before-mirror-$(date +%Y%m%d-%H%M%S)"
    log "Creating the Python environment with $base"
    "$base" -m venv "$REPO/.venv" || die "The Python environment could not be created."
  fi
  install_dependencies
}

agent_loaded() {
  launchctl print "gui/$USER_ID/$AGENT" > /dev/null 2>&1
}

launcher_running() {
  pgrep -q -f 'DriveTest Analyzer.app/Contents/MacOS/DriveTestAnalyzerLauncher'
}

server_running() {
  pgrep -q -f "$REPO/src/main.py"
}

port_listening() {
  lsof -nP -iTCP:"$MIRROR_PORT" -sTCP:LISTEN > /dev/null 2>&1
}

# Neither the launcher, nor its server, nor anything on the port is left.
wait_launcher_gone() {
  local limit="$1" waited=0
  while launcher_running || server_running || port_listening; do
    [ "$waited" -ge "$limit" ] && return 1
    sleep 1
    waited=$((waited + 1))
  done
  return 0
}

wait_port_free() {
  local limit="$1" waited=0
  while port_listening; do
    [ "$waited" -ge "$limit" ] && return 1
    sleep 1
    waited=$((waited + 1))
  done
  return 0
}

# The macOS launcher the mirror runs the application with: the copy of the checkout, else the installed one.
find_launcher() {
  local candidate
  for candidate in "$REPO/macos-launcher/DriveTest Analyzer.app" "/Applications/DriveTest Analyzer.app" "$HOME/Applications/DriveTest Analyzer.app"; do
    [ -d "$candidate" ] && { echo "$candidate"; return 0; }
  done
  return 1
}

# Quitting the launcher stops its server cleanly. macOS may not let a remote session send it the quit event (it
# asks on the screen of the mirror the first time): the launcher is then ended, and its launch script, which
# keeps watching it, stops the server just the same.
#
# The launcher is only gone once its server has finished shutting down and its launch script has removed the PID
# file: opened while that file still names a live server, the launcher stops that server and quits instead of
# starting one.
quit_launcher() {
  if launcher_running; then
    log "Asking the DriveTest Analyzer launcher to stop the server and quit"
    osascript -e 'with timeout of 8 seconds' -e "tell application id \"$LAUNCHER_ID\" to quit" -e 'end timeout' > /dev/null 2>&1 || true
    if ! wait_launcher_gone 30; then
      pkill -f 'DriveTest Analyzer.app/Contents/MacOS/DriveTestAnalyzerLauncher' 2>/dev/null || true
      wait_launcher_gone 30 || true
    fi
  fi
  # A server the launcher left behind (the launcher was force quit) is stopped as its launch script would.
  if server_running; then
    pkill -f "$REPO/src/main.py" 2>/dev/null || true
    if ! wait_launcher_gone 15; then
      pkill -9 -f "$REPO/src/main.py" 2>/dev/null || true
      sleep 1
    fi
  fi
  rm -f "$REPO/.drivetest-analyzer-runtime/server.pid"
  ! port_listening
}

# Another server of the application on the same port (a terminal, the launcher in agent mode) gives way.
quit_other_servers() {
  port_listening || return 0
  quit_launcher
  port_listening || return 0
  log "Stopping the process that listens on port $MIRROR_PORT"
  lsof -nP -tiTCP:"$MIRROR_PORT" -sTCP:LISTEN | xargs kill 2>/dev/null || true
  wait_port_free 10 || die "Port $MIRROR_PORT is still taken on this Mac."
}

stop_app() {
  if [ "$MIRROR_RUNNER" = "launcher" ]; then
    quit_launcher || die "The launcher did not free port $MIRROR_PORT within a minute."
  else
    agent_loaded && { launchctl bootout "gui/$USER_ID/$AGENT" 2>/dev/null || true; }
    wait_port_free 60 || die "Something still listens on port $MIRROR_PORT a minute after stopping the mirror application."
  fi
}

wait_for_answer() {
  local waited=0 code
  while [ "$waited" -lt 300 ]; do
    code="$(curl -s -o /dev/null -m 3 -w '%{http_code}' "http://127.0.0.1:$MIRROR_PORT/healthz" 2>/dev/null)"
    if [ -n "$code" ] && [ "$code" != "000" ]; then
      log "Mirror application up on port $MIRROR_PORT (/healthz $code)"
      return 0
    fi
    # The launcher gave up (it shows why on the screen of the mirror): waiting longer brings nothing.
    if [ "$MIRROR_RUNNER" = "launcher" ] && [ "$waited" -ge 20 ] && ! launcher_running && ! server_running; then
      return 1
    fi
    sleep 2
    waited=$((waited + 2))
  done
  return 1
}

start_app() {
  if [ "$MIRROR_RUNNER" = "launcher" ]; then
    [ -d "$MIRROR_LAUNCHER" ] || die "The launcher $MIRROR_LAUNCHER is missing."
    local attempt
    for attempt in 1 2; do
      if port_listening; then
        break
      fi
      # A launcher open without its server (it showed an error), or a server without its launcher, goes first.
      quit_launcher
      log "Opening the DriveTest Analyzer launcher"
      open "$MIRROR_LAUNCHER" || die "The launcher could not be opened (is the user of the mirror logged in on its screen?)."
      wait_for_answer && return 0
      log "The launcher did not start the server (attempt $attempt)."
    done
    wait_for_answer || die "The mirror application did not answer on port $MIRROR_PORT (see $REPO/.drivetest-analyzer-runtime/server.log and the screen of the mirror)."
    return 0
  fi
  [ -f "$PLIST" ] || die "The agent of the mirror application is not installed ($PLIST is missing)."
  agent_loaded || launchctl bootstrap "gui/$USER_ID" "$PLIST" || die "launchd refused the agent $AGENT."
  wait_for_answer || die "The mirror application did not answer on port $MIRROR_PORT within five minutes (see $APP_LOG)."
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

# install <storage> <port> <label> [--runner launcher|agent] [--replace-data]: the environment, the storage folders
# and what runs the application (not started: the first synchronization starts it once the databases are applied).
# With the launcher, the application reads its storage from storage-paths.conf of the checkout and its mirror
# mode from the mirror-of file of the configuration folder, which the synchronization leaves alone.
install_app() {
  local storage="${1:-}" port="${2:-}" label="${3:-}" runner="" replace=0 launcher=""
  shift 3 2>/dev/null || true
  while [ $# -gt 0 ]; do
    case "$1" in
      --runner) runner="$2"; shift 2 ;;
      --replace-data) replace=1; shift ;;
      *) die "Unknown install option $1." ;;
    esac
  done
  [ -n "$storage" ] && [ -n "$port" ] && [ -n "$label" ] || die "install needs the storage folder, the port and the label."
  if [ -z "$runner" ]; then
    if find_launcher > /dev/null; then runner=launcher; else runner=agent; fi
  fi
  if [ "$runner" = "launcher" ]; then
    launcher="$(find_launcher)" || die "This Mac has no DriveTest Analyzer launcher; install with --runner agent."
    case "$storage" in
      "$HOME/DriveTestAnalyzer") ;;
      *) log "The launcher reads the storage from storage-paths.conf of the checkout (~/DriveTestAnalyzer): $storage must be what it names." ;;
    esac
  fi
  mkdir -p "$(dirname "$CONFIG_FILE")"
  printf 'MIRROR_STORAGE=%q\nMIRROR_PORT=%q\nMIRROR_LABEL=%q\nMIRROR_RUNNER=%q\nMIRROR_LAUNCHER=%q\n' \
    "$storage" "$port" "$label" "$runner" "$launcher" > "$CONFIG_FILE"
  load_config
  ensure_venv
  quit_other_servers
  if [ -d "$storage" ] && [ -n "$(ls -A "$storage" 2>/dev/null)" ] && [ ! -f "$storage/.mirror-storage" ]; then
    [ "$replace" -eq 1 ] || die "$storage already holds data of its own. Run install with --replace-mirror-data to set it aside (kept beside it, renamed) and take the data of the development Mac."
    local aside="$storage.before-mirror-$(date +%Y%m%d-%H%M%S)"
    mv "$storage" "$aside" || die "$storage could not be set aside."
    log "The data $storage held is kept in $aside"
    # The storage starts as an APFS clone of that data (no time, no space): the first synchronization then
    # sends only what differs from the development Mac instead of every CDR. Its backups, packages, trash and
    # caches are not part of a mirror; the copy set aside keeps them.
    if cp -cR "$aside" "$storage" 2>/dev/null; then
      rm -rf "$storage/data/scheduled-backups" "$storage/data/transfer-packages" "$storage/data/.workspace-trash" "$storage/.mirror-incoming"
      find "$storage/data" -type d -name '.cache' -prune -exec rm -rf {} + 2>/dev/null
      log "The storage starts as a clone of that data"
    else
      rm -rf "$storage"
    fi
  fi
  mkdir -p "$storage/config" "$storage/data" || die "The storage folders could not be created."
  date > "$storage/.mirror-storage"
  if [ "$runner" = "launcher" ]; then
    printf '%s\n' "$label" > "$storage/config/mirror-of"
    if agent_loaded; then launchctl bootout "gui/$USER_ID/$AGENT" 2>/dev/null; fi
    rm -f "$PLIST"
    log "Mirror application installed, run by $launcher; it starts when the first synchronization applies the databases."
  else
    rm -f "$storage/config/mirror-of"
    write_plist
    log "Mirror application installed as the agent $AGENT; it starts when the first synchronization applies the databases."
  fi
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
  if [ "$MIRROR_RUNNER" = "launcher" ]; then
    if launcher_running; then echo "Launcher: running ($MIRROR_LAUNCHER)"; else echo "Launcher: not running ($MIRROR_LAUNCHER)"; fi
  elif agent_loaded; then echo "Agent $AGENT: loaded"; else echo "Agent $AGENT: not loaded"; fi
  echo "Application: $(curl -s -m 5 "http://127.0.0.1:$MIRROR_PORT/healthz" || echo 'not answering')"
  echo "Storage: $(du -sh "$MIRROR_STORAGE" 2>/dev/null | cut -f1) in $MIRROR_STORAGE"
  echo "Checkout: $(cd "$REPO" && git rev-parse --abbrev-ref HEAD 2>/dev/null) $(cd "$REPO" && git rev-parse --short HEAD 2>/dev/null)"
}

# The mirror application stops being one: the agent goes, or the launcher keeps running an ordinary server.
uninstall_app() {
  load_config
  if [ "$MIRROR_RUNNER" = "launcher" ]; then
    rm -f "$MIRROR_STORAGE/config/mirror-of"
    rm -f "$CONFIG_FILE"
    log "The mirror-of file is removed: the launcher serves $MIRROR_STORAGE as an ordinary server from its next start."
  else
    stop_app
    rm -f "$PLIST" "$CONFIG_FILE"
    log "The agent of the mirror application is removed; the checkout and $MIRROR_STORAGE stay."
  fi
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
  *) echo "Usage: mirror-remote.sh install <storage> <port> <label> [--runner launcher|agent] [--replace-data] | deps | apply | restart | stop | start | status | uninstall" >&2; exit 1 ;;
esac
