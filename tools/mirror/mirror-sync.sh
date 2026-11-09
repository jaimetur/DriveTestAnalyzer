#!/bin/bash
# Keep a mirror of this development environment on another Mac of the network (read tools/mirror/README.md):
# the checkout as soon as a file changes, the configuration and data folders every few minutes (the SQLite
# databases as consistent online backups). Every connection goes from this Mac to the mirror over SSH; nothing
# has to reach this Mac, so it works from a computer whose network closes every incoming connection.
set -u

TOOL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCAL_REPO="$(cd "$TOOL_DIR/../.." && pwd)"
CONFIG_FILE="${DTA_MIRROR_CONFIG:-$HOME/.config/drivetest-analyzer/mirror.conf}"
STATE_DIR="${DTA_MIRROR_STATE:-$HOME/.local/state/drivetest-analyzer-mirror}"
LOG_FILE="${DTA_MIRROR_LOG:-$HOME/Library/Logs/drivetest-analyzer-mirror.log}"
KEY_FILE="$HOME/.ssh/drivetest-analyzer-mirror"
AGENTS_DIR="$HOME/Library/LaunchAgents"
AGENT_WATCH="com.drivetestanalyzer.mirror-watch"
AGENT_DATA="com.drivetestanalyzer.mirror-data"

# What the checkout synchronization leaves out: the Python environments and caches of each Mac, the runtime files
# of the macOS launcher, the settings its editor and its assistant keep for one Mac (the tracked launch.json
# travels), the storage folders a checkout without storage-paths.conf would hold, and Git lock files.
CODE_EXCLUDES=(
  --exclude='/.venv*/' --exclude='/.drivetest-analyzer-venv/' --exclude='/.drivetest-analyzer-runtime/'
  --exclude='/.idea/' --include='/.claude/launch.json' --exclude='/.claude/*'
  --exclude='/config/' --exclude='/data/' --exclude='/env/'
  --exclude='__pycache__/' --exclude='.pytest_cache/' --exclude='.ruff_cache/' --exclude='.mypy_cache/'
  --exclude='*.pyc' --exclude='.DS_Store' --exclude='node_modules/' --exclude='/.git/*.lock' --exclude='/.git/index.lock'
)
# The databases travel as snapshots (see snapshot_databases), never as the files the application writes.
DATABASE_EXCLUDES=(--exclude='*.db' --exclude='*.db-wal' --exclude='*.db-shm' --exclude='*.db-journal' --exclude='.DS_Store')
# The configuration folder: the AI tools installed for this Mac and the AI credentials of its users stay here, and
# the mirror-of file that puts the mirror application in mirror mode stays there.
CONFIG_EXCLUDES=(--exclude='/tools/' --exclude='/ai-credentials.json' --exclude='/mirror-of')
# The data folder: the scheduled backups, the transfer packages, the trash and the caches each Mac makes itself.
DATA_EXCLUDES=(
  --exclude='/scheduled-backups/' --exclude='/transfer-packages/' --exclude='/.workspace-trash/' --exclude='/.map-tiles-cache/'
  --exclude='.background-stop-requests/' --exclude='.upload-sessions/' --exclude='.cache/'
)
DATABASE_PRUNE=(
  -not -path '*/scheduled-backups/*' -not -path '*/.workspace-trash/*' -not -path '*/transfer-packages/*' -not -path '*/.cache/*'
)

usage() {
  cat <<'EOF'
Usage: tools/mirror/mirror-sync.sh <command> [options]

  install --host user@host --repo /checkout/on/the/mirror --storage /storage/on/the/mirror
          [--code-only] [--follow saves|commits] [--label "the development Mac"] [--port 7278]
          [--interval 600] [--runner launcher|agent] [--replace-mirror-checkout] [--replace-mirror-data]
          [--address https://the.mirror.example]
                 Set the mirror up: the SSH key of this Mac, rsync 3 and Python 3.15 on the mirror, its checkout,
                 its Python environment, what runs its application (the macOS launcher when the mirror has it,
                 else a launchd agent), the first synchronization, and the agents of this Mac that keep it
                 synchronized. --code-only: the mirror is a server of its own that always runs the code of this
                 checkout; its data is its own and the data of this Mac is never sent to it.
                 --follow commits: the mirror runs the commit this checkout is on, and what is saved here
                 without a commit stays here; --follow saves (the default): it runs every saved change.
                 --address, for a code-only mirror: the address it is reached at; the application of this Mac
                 then says on every page that it is a development copy and links to that address.
                 --replace-mirror-checkout overwrites changes of its own the checkout of the mirror holds;
                 --replace-mirror-data sets the data the mirror already holds aside (kept beside it, renamed) and
                 takes the data of this Mac.
  key            Show the public key the mirror must authorize (install creates it).
  code           Synchronize the checkout now: its saved changes, or its commit for a mirror that follows the
                 commits (the mirror application restarts when Python sources changed).
  data           Synchronize the configuration and data folders now (the mirror application restarts for a few
                 seconds when a database changed). Refused for a code-only mirror.
  all            code, then data (code alone for a code-only mirror).
  watch          Synchronize the checkout whenever a file changes, or whenever its commit does (what the watch
                 agent runs).
  address [url]  Set, change or (without a url) remove the address of a code-only mirror that the application of
                 this Mac names on every page.
  status         The last synchronizations, the agents of this Mac and the mirror application.
  restart-mirror Restart the mirror application.
  uninstall [--mirror]
                 Remove the agents of this Mac; with --mirror, also the agent of the mirror application (the
                 checkout and the data of the mirror stay).
EOF
}

log() {
  local line
  line="[$(date '+%Y-%m-%d %H:%M:%S')] $*"
  mkdir -p "$(dirname "$LOG_FILE")"
  printf '%s\n' "$line" >> "$LOG_FILE"
  printf '%s\n' "$line" >&2
}

die() {
  log "$*"
  exit 1
}

find_tool() {
  local name="$1" candidate
  shift
  for candidate in "$@"; do
    [ -x "$candidate/$name" ] && { echo "$candidate/$name"; return 0; }
  done
  command -v "$name"
}

load_config() {
  [ -f "$CONFIG_FILE" ] || die "No mirror is configured: run 'tools/mirror/mirror-sync.sh install …' first ($CONFIG_FILE is missing)."
  # shellcheck disable=SC1090
  . "$CONFIG_FILE"
  : "${MIRROR_SSH:?MIRROR_SSH is missing in $CONFIG_FILE}" "${MIRROR_REPO:?MIRROR_REPO is missing in $CONFIG_FILE}" \
    "${MIRROR_STORAGE:?MIRROR_STORAGE is missing in $CONFIG_FILE}"
  LOCAL_STORAGE="${LOCAL_STORAGE:-$HOME/DriveTestAnalyzer}"
  MIRROR_PORT="${MIRROR_PORT:-7278}"
  MIRROR_LABEL="${MIRROR_LABEL:-the development Mac}"
  DATA_INTERVAL_SECONDS="${DATA_INTERVAL_SECONDS:-600}"
  MIRROR_DATA="${MIRROR_DATA:-on}"
  MIRROR_FOLLOW="${MIRROR_FOLLOW:-saves}"
  MIRROR_ADDRESS="${MIRROR_ADDRESS:-}"
  RESTART_SETTLE_SECONDS="${RESTART_SETTLE_SECONDS:-5}"
  REMOTE_RSYNC="${REMOTE_RSYNC:-}"
  SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=15 -o ServerAliveInterval=30 -o IdentitiesOnly=yes -i "$KEY_FILE")
  RSYNC="$(find_tool rsync /opt/homebrew/bin /usr/local/bin)" || die "rsync is not installed."
  case "$("$RSYNC" --version 2>/dev/null)" in
    *"version 3."*) ;;
    *) die "rsync 3 is needed on this Mac (brew install rsync); $RSYNC is older." ;;
  esac
  mkdir -p "$STATE_DIR"
}

remote() {
  ssh "${SSH_OPTS[@]}" "$MIRROR_SSH" "$@"
}

# Run a command of tools/mirror/mirror-remote.sh on the mirror, each argument quoted for its shell.
remote_tool() {
  local quoted="" argument
  for argument in "$@"; do
    quoted="$quoted $(printf '%q' "$argument")"
  done
  remote "/bin/bash $(printf '%q' "$MIRROR_REPO/tools/mirror/mirror-remote.sh")$quoted"
}

rsync_run() {
  local rsync_path=()
  [ -n "$REMOTE_RSYNC" ] && rsync_path=(--rsync-path="$REMOTE_RSYNC")
  # ${array[@]+…}: bash 3.2 of macOS takes an empty array as an unset variable under set -u.
  RSYNC_RSH="ssh ${SSH_OPTS[*]}" "$RSYNC" -az --delete --itemize-changes --out-format='%i %n' ${rsync_path[@]+"${rsync_path[@]}"} "$@"
}

# One synchronization at a time: the watch agent and the data agent may want to run together.
with_lock() {
  local lock="$STATE_DIR/lock" waited=0 result
  until mkdir "$lock" 2>/dev/null; do
    if [ -f "$lock/pid" ] && ! kill -0 "$(cat "$lock/pid" 2>/dev/null)" 2>/dev/null; then
      rm -rf "$lock"
      continue
    fi
    [ "$waited" -ge 3600 ] && die "Another synchronization has held $lock for an hour."
    sleep 2
    waited=$((waited + 2))
  done
  echo $$ > "$lock/pid"
  trap 'rm -rf "$STATE_DIR/lock"' EXIT
  "$@"
  result=$?
  rm -rf "$lock"
  trap - EXIT
  return $result
}

count_lines() {
  printf '%s' "$1" | grep -c . || true
}

# The mirror application keeps the Python sources it had loaded until it restarts; the mirror only restarts it
# when the synchronized code imports, so a save that leaves the code broken does not take the server down.
restart_mirror_app() {
  log "Restarting the mirror application with the new Python sources"
  remote_tool restart || { log "The mirror application was not restarted: the synchronized code does not import, or the mirror did not answer."; return 1; }
}

# The watch agent restarts the mirror application once the Python changes settle, so a burst of saves restarts
# it once: a newer change takes the token, and the restart of the older one gives up.
schedule_restart() {
  local token="$$-$(date +%s)-$RANDOM"
  echo "$token" > "$STATE_DIR/restart-token"
  (
    sleep "$RESTART_SETTLE_SECONDS"
    [ "$(cat "$STATE_DIR/restart-token" 2>/dev/null)" = "$token" ] || exit 0
    with_lock restart_mirror_app
  ) &
}

# The checkout, Git history included: the mirror holds the same branch, commits and uncommitted changes.
# $1: restart (at once, the default), defer (once the changes settle) or no-restart (install).
sync_code() {
  local restart="${1:-restart}" changes
  log "Synchronizing the checkout with $MIRROR_SSH:$MIRROR_REPO"
  changes="$(rsync_run "${CODE_EXCLUDES[@]}" "$LOCAL_REPO/" "$MIRROR_SSH:$MIRROR_REPO/")" || { log "The checkout synchronization failed."; return 1; }
  date '+%Y-%m-%d %H:%M:%S' > "$STATE_DIR/last-code-sync"
  # (Not at install, which makes the environment of the mirror after its first synchronization.)
  if [ "$restart" != "no-restart" ] && grep -q -E '^[^ ]+ requirements\.txt$' <<< "$changes"; then
    log "requirements.txt changed: installing the dependencies on the mirror"
    remote_tool deps || log "The dependencies could not be installed on the mirror."
  fi
  if [ "$restart" != "no-restart" ] && grep -q -E '^[^ ]+ (src/.*\.py|requirements\.txt|storage-paths\.conf)$|^\*deleting +src/.*\.py$' <<< "$changes"; then
    if [ "$restart" = "defer" ]; then
      log "Python sources changed: the mirror application restarts once the changes settle (${RESTART_SETTLE_SECONDS} s)"
      schedule_restart
    else
      restart_mirror_app || return 1
    fi
  fi
  log "Checkout synchronized ($(count_lines "$changes") changes)."
}

# What the mirror runs to put its working tree at a commit, on its standard shell whatever its login shell is: it
# prints the files that differ from the commit it was at (or what makes it restart, when it has no record).
checkout_script() {
  local commit="$1"
  cat <<EOF
cd $(printf '%q' "$MIRROR_REPO") || exit 1
previous="\$(cat .git/mirror-deployed-commit 2>/dev/null || true)"
git cat-file -e "$commit^{commit}" || exit 1
git reset -q --hard "$commit" || exit 1
if [ -n "\$previous" ] && git cat-file -e "\$previous^{commit}" 2>/dev/null; then
  git diff --name-only "\$previous" "$commit"
else
  echo requirements.txt
  echo src/main.py
fi
echo "$commit" > .git/mirror-deployed-commit
EOF
}

# For a mirror that follows the commits: the Git history, then the working tree of the mirror put at the commit
# this checkout is on, so what is saved here without a commit stays here. Nothing is sent while the commit is the
# same. The index stays the one of each Mac, and the record of the commit the mirror runs is its own.
# $1: restart (at once, the default), defer (once the changes settle) or no-restart (install).
sync_commits() {
  local restart="${1:-restart}" head previous changes
  head="$(git -C "$LOCAL_REPO" rev-parse --verify -q HEAD)" || { log "This checkout has no commit to follow."; return 1; }
  previous="$(cat "$STATE_DIR/deployed-commit" 2>/dev/null || true)"
  if [ "$head" = "$previous" ]; then
    [ "$restart" != "restart" ] || log "The mirror already runs commit ${head:0:9}."
    return 0
  fi
  log "Sending commit ${head:0:9} to $MIRROR_SSH:$MIRROR_REPO"
  rsync_run --exclude='/index' --exclude='*.lock' --exclude='/mirror-deployed-commit' "$LOCAL_REPO/.git/" "$MIRROR_SSH:$MIRROR_REPO/.git/" > /dev/null \
    || { log "The Git history could not be sent."; return 1; }
  changes="$(remote "/bin/sh -c $(printf '%q' "$(checkout_script "$head")")")" || { log "The mirror could not be put at commit ${head:0:9}."; return 1; }
  echo "$head" > "$STATE_DIR/deployed-commit"
  date '+%Y-%m-%d %H:%M:%S' > "$STATE_DIR/last-code-sync"
  if [ "$restart" != "no-restart" ] && grep -q -x 'requirements\.txt' <<< "$changes"; then
    log "requirements.txt changed: installing the dependencies on the mirror"
    remote_tool deps || log "The dependencies could not be installed on the mirror."
  fi
  if [ "$restart" != "no-restart" ] && grep -q -x -E 'src/.*\.py|requirements\.txt|storage-paths\.conf' <<< "$changes"; then
    if [ "$restart" = "defer" ]; then
      log "Python sources changed: the mirror application restarts once the changes settle (${RESTART_SETTLE_SECONDS} s)"
      schedule_restart
    else
      restart_mirror_app || return 1
    fi
  fi
  log "The mirror runs commit ${head:0:9} ($(count_lines "$changes") files changed)."
}

# The saved changes of the checkout, or its commit, as the mirror follows them.
sync_checkout() {
  if [ "$MIRROR_FOLLOW" = "commits" ]; then
    sync_commits "$1"
  else
    sync_code "$1"
  fi
}

sync_checkout_now() {
  sync_checkout restart
}

sync_checkout_deferred() {
  sync_checkout defer
}

sync_checkout_without_restart() {
  sync_checkout no-restart
}

list_databases() {
  find "$LOCAL_STORAGE/config" "$LOCAL_STORAGE/data" -type f -name '*.db' "${DATABASE_PRUNE[@]}" 2>/dev/null | sort
}

# A consistent copy of every database that changed since the last one (SQLite online backup: the application
# keeps writing meanwhile), kept under $STATE_DIR/snapshots with the same relative paths. Returns 0 when a
# snapshot was made or removed, 1 when nothing changed.
snapshot_databases() {
  local snapshots="$STATE_DIR/snapshots" manifest="$STATE_DIR/db-manifest" next_manifest="$STATE_DIR/db-manifest.next"
  local changed=1 database relative fingerprint wal_state fresh snapshot
  mkdir -p "$snapshots"
  touch "$manifest"
  : > "$next_manifest"
  while IFS= read -r database; do
    [ -n "$database" ] || continue
    relative="${database#"$LOCAL_STORAGE"/}"
    # The main file keeps its time until a WAL checkpoint, so a write-ahead log with pages counts too; an empty
    # one, which a connection that only reads leaves while it is open, does not.
    wal_state="$(stat -f '%z %m' "$database-wal" 2>/dev/null || echo none)"
    case "$wal_state" in "0 "*) wal_state=none ;; esac
    fingerprint="$(stat -f '%z %m' "$database") $wal_state"
    if grep -qxF "$relative|$fingerprint" "$manifest" && [ -f "$snapshots/$relative" ]; then
      printf '%s|%s\n' "$relative" "$fingerprint" >> "$next_manifest"
      continue
    fi
    mkdir -p "$(dirname "$snapshots/$relative")"
    fresh="$snapshots/$relative.new"
    rm -f "$fresh" "$fresh-wal" "$fresh-shm" "$fresh-journal"
    if sqlite3 "$database" ".backup '$fresh'"; then
      printf '%s|%s\n' "$relative" "$fingerprint" >> "$next_manifest"
      if [ -f "$snapshots/$relative" ] && cmp -s "$fresh" "$snapshots/$relative"; then
        # Only the files of the database moved (a checkpoint): its content is the one the mirror already has.
        rm -f "$fresh"
      else
        mv -f "$fresh" "$snapshots/$relative"
        changed=0
        log "Snapshot of $relative"
      fi
    else
      rm -f "$fresh"
      log "The snapshot of $relative failed; it is tried again at the next synchronization."
    fi
  done <<< "$(list_databases)"
  # The snapshots of databases deleted here (a deleted workspace) go, so the mirror removes them too.
  while IFS= read -r snapshot; do
    [ -n "$snapshot" ] || continue
    relative="${snapshot#"$snapshots"/}"
    if [ ! -f "$LOCAL_STORAGE/$relative" ]; then
      rm -f "$snapshot"
      changed=0
      log "Removed the snapshot of $relative, deleted here"
    fi
  done <<< "$(find "$snapshots" -type f -name '*.db' 2>/dev/null)"
  mv "$next_manifest" "$manifest"
  return $changed
}

# The configuration and data folders: files straight into the folders of the mirror (its application keeps
# running), the databases as snapshots applied by the mirror while its application is stopped for a moment.
sync_data() {
  local changes files=0
  [ "$MIRROR_DATA" = "on" ] || die "This mirror follows the checkout only: its data is its own, and the data of this Mac is never sent to it (install without --code-only mirrors the data too)."
  [ -d "$LOCAL_STORAGE/config" ] && [ -d "$LOCAL_STORAGE/data" ] || die "$LOCAL_STORAGE has no config and data folders."
  log "Synchronizing the configuration and data folders with $MIRROR_SSH:$MIRROR_STORAGE"
  changes="$(rsync_run "${DATABASE_EXCLUDES[@]}" "${CONFIG_EXCLUDES[@]}" "$LOCAL_STORAGE/config/" "$MIRROR_SSH:$MIRROR_STORAGE/config/")" \
    || { log "The configuration folder synchronization failed."; return 1; }
  files=$((files + $(count_lines "$changes")))
  changes="$(rsync_run "${DATABASE_EXCLUDES[@]}" "${DATA_EXCLUDES[@]}" "$LOCAL_STORAGE/data/" "$MIRROR_SSH:$MIRROR_STORAGE/data/")" \
    || { log "The data folder synchronization failed."; return 1; }
  files=$((files + $(count_lines "$changes")))
  if snapshot_databases; then
    log "Sending the database snapshots"
    rsync_run --inplace --partial "$STATE_DIR/snapshots/" "$MIRROR_SSH:$MIRROR_STORAGE/.mirror-incoming/" > /dev/null \
      || { log "The database snapshots could not be sent."; return 1; }
    log "Applying the databases on the mirror (its application restarts)"
    remote_tool apply || { log "The databases could not be applied on the mirror."; return 1; }
  fi
  date '+%Y-%m-%d %H:%M:%S' > "$STATE_DIR/last-data-sync"
  log "Data synchronized ($files file changes)."
}

# What the watch agent runs: a synchronization at start, then one each time files of the checkout change.
watch_code() {
  local fswatch
  fswatch="$(find_tool fswatch /opt/homebrew/bin /usr/local/bin)" || die "fswatch is not installed (brew install fswatch)."
  local watched="$LOCAL_REPO"
  # A commit, a branch change or a merge moves the files of the Git folder; saved changes do not.
  [ "$MIRROR_FOLLOW" = "commits" ] && watched="$LOCAL_REPO/.git"
  with_lock sync_checkout_deferred || log "The checkout synchronization failed; it is tried again at the next change."
  "$fswatch" -o -l 1 \
    -e '/\.venv/' -e '/\.drivetest-analyzer-venv/' -e '/\.drivetest-analyzer-runtime/' -e '__pycache__' -e '/\.pytest_cache/' \
    -e '/\.ruff_cache/' -e '/\.mypy_cache/' -e '\.DS_Store$' -e '/node_modules/' -e '/\.git/objects/' -e '/\.git/.*\.lock$' -e '\.pyc$' \
    "$watched" | while read -r _events; do
    with_lock sync_checkout_deferred || log "The checkout synchronization failed; it is tried again at the next change."
  done
}

# A code-only mirror is the server with the data in use, and this Mac a development copy: given the address the
# mirror is reached at, the application of this Mac says so on every page, with a link (the development-copy-of
# file of its configuration folder, which it reads without a restart).
mark_development_copy() {
  local address="$1" marker="$LOCAL_STORAGE/config/development-copy-of"
  if [ -n "$address" ] && [ "$MIRROR_DATA" = "off" ]; then
    mkdir -p "$LOCAL_STORAGE/config"
    printf '%s\n' "$address" > "$marker"
    log "The application of this Mac says it is a development copy of $address."
  elif [ -f "$marker" ]; then
    rm -f "$marker"
    log "The application of this Mac no longer says it is a development copy."
  fi
}

set_address() {
  local address="${1:-}"
  [ "$MIRROR_DATA" = "off" ] || die "Only a code-only mirror is the server with the data in use: this Mac is no development copy of a data mirror."
  grep -v '^MIRROR_ADDRESS=' "$CONFIG_FILE" > "$CONFIG_FILE.new"
  printf 'MIRROR_ADDRESS="%s"\n' "$address" >> "$CONFIG_FILE.new"
  mv "$CONFIG_FILE.new" "$CONFIG_FILE"
  MIRROR_ADDRESS="$address"
  mark_development_copy "$address"
}

ensure_key() {
  if [ ! -f "$KEY_FILE" ]; then
    ssh-keygen -q -t ed25519 -N '' -C "drivetest-analyzer-mirror@$(hostname -s)" -f "$KEY_FILE" || die "The SSH key could not be created."
    log "Created the SSH key of the mirror: $KEY_FILE"
  fi
}

show_key() {
  ensure_key
  cat "$KEY_FILE.pub"
}

write_agent() {
  local label="$1" command="$2" interval="$3" plist="$AGENTS_DIR/$1.plist" schedule
  if [ -n "$interval" ]; then
    schedule="  <key>StartInterval</key><integer>$interval</integer>"
  else
    schedule="  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>15</integer>"
  fi
  launchctl bootout "gui/$(id -u)/$label" 2>/dev/null || true
  cat > "$plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$label</string>
  <key>ProgramArguments</key>
  <array><string>/bin/bash</string><string>$TOOL_DIR/mirror-sync.sh</string><string>$command</string></array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    <key>HOME</key><string>$HOME</string>
  </dict>
  <key>RunAtLoad</key><true/>
$schedule
  <key>StandardOutPath</key><string>$HOME/Library/Logs/$label.log</string>
  <key>StandardErrorPath</key><string>$HOME/Library/Logs/$label.log</string>
</dict>
</plist>
EOF
  launchctl bootstrap "gui/$(id -u)" "$plist" || die "launchd refused the agent $label ($plist)."
  log "Agent $label installed."
}

install_agents() {
  mkdir -p "$AGENTS_DIR" "$HOME/Library/Logs"
  write_agent "$AGENT_WATCH" watch ""
  if [ "$MIRROR_DATA" = "on" ]; then
    write_agent "$AGENT_DATA" data "$DATA_INTERVAL_SECONDS"
  else
    # A code-only mirror has no data agent, and keeps none of the database snapshots of an earlier data mirror.
    launchctl bootout "gui/$(id -u)/$AGENT_DATA" 2>/dev/null || true
    rm -f "$AGENTS_DIR/$AGENT_DATA.plist" "$STATE_DIR/db-manifest" "$STATE_DIR/last-data-sync"
    rm -rf "${STATE_DIR:?}/snapshots"
  fi
}

remote_rsync_path() {
  remote 'for candidate in /opt/homebrew/bin/rsync /usr/local/bin/rsync; do [ -x "$candidate" ] && { echo "$candidate"; break; }; done'
}

install_mirror() {
  local host="" repo="" storage="" label="the development Mac" port=7278 interval=600 runner="" replace_checkout=0 replace_data=0 data=on follow=saves address=""
  while [ $# -gt 0 ]; do
    case "$1" in
      --host) host="$2"; shift 2 ;;
      --repo) repo="$2"; shift 2 ;;
      --storage) storage="$2"; shift 2 ;;
      --label) label="$2"; shift 2 ;;
      --port) port="$2"; shift 2 ;;
      --interval) interval="$2"; shift 2 ;;
      --runner) runner="$2"; shift 2 ;;
      --code-only) data=off; shift ;;
      --follow) follow="$2"; shift 2 ;;
      --address) address="$2"; shift 2 ;;
      --replace-mirror-checkout) replace_checkout=1; shift ;;
      --replace-mirror-data) replace_data=1; shift ;;
      *) die "Unknown option $1 (see 'tools/mirror/mirror-sync.sh' without arguments)." ;;
    esac
  done
  case "$runner" in ""|launcher|agent) ;; *) die "--runner takes launcher or agent." ;; esac
  case "$follow" in saves|commits) ;; *) die "--follow takes saves or commits." ;; esac
  [ -n "$host" ] && [ -n "$repo" ] && [ -n "$storage" ] || die "install needs --host, --repo and --storage."
  [ "$data" = "on" ] || [ "$replace_data" -eq 0 ] || die "--code-only leaves the data of the mirror alone: it cannot go with --replace-mirror-data."
  [ "$data" = "off" ] || [ -z "$address" ] || die "--address is for a code-only mirror, the server with the data in use."
  ensure_key
  mkdir -p "$(dirname "$CONFIG_FILE")" "$STATE_DIR"
  cat > "$CONFIG_FILE" <<EOF
# Mirror of this DriveTest Analyzer development environment (tools/mirror/mirror-sync.sh).
MIRROR_SSH="$host"
MIRROR_REPO="$repo"
MIRROR_STORAGE="$storage"
LOCAL_STORAGE="$HOME/DriveTestAnalyzer"
MIRROR_PORT=$port
MIRROR_LABEL="$label"
DATA_INTERVAL_SECONDS=$interval
MIRROR_DATA="$data"
MIRROR_FOLLOW="$follow"
MIRROR_ADDRESS="$address"
EOF
  load_config
  remote true 2>/dev/null || die "The mirror does not accept the key of this Mac yet. Add this public key to ~/.ssh/authorized_keys of $host (Remote Login on), then run install again:
$(cat "$KEY_FILE.pub")"
  local remote_rsync
  remote_rsync="$(remote_rsync_path)"
  if [ -z "$remote_rsync" ]; then
    log "Installing rsync 3 on the mirror with Homebrew"
    remote 'PATH=/opt/homebrew/bin:/usr/local/bin:$PATH brew install rsync' > /dev/null 2>&1 || die "rsync 3 is needed on the mirror (brew install rsync there)."
    remote_rsync="$(remote_rsync_path)"
  fi
  [ -n "$remote_rsync" ] || die "rsync 3 was not found on the mirror after installing it."
  printf 'REMOTE_RSYNC="%s"\n' "$remote_rsync" >> "$CONFIG_FILE"
  REMOTE_RSYNC="$remote_rsync"
  # A checkout this tool already mirrors holds the uncommitted changes of this Mac, not changes of its own.
  if remote '[ -f "$HOME/.config/drivetest-analyzer/mirror-app.conf" ]'; then
    :
  elif remote "[ -d $(printf '%q' "$repo")/.git ]"; then
    local own_changes
    own_changes="$(remote "cd $(printf '%q' "$repo") && git status --porcelain --untracked-files=no | head -5")"
    if [ -n "$own_changes" ] && [ "$replace_checkout" -eq 0 ]; then
      die "The checkout of the mirror has changes of its own:
$own_changes
Commit or discard them there, or run install with --replace-mirror-checkout to overwrite them."
    fi
  else
    remote "mkdir -p $(printf '%q' "$repo")" || die "The checkout folder could not be created on the mirror."
  fi
  # The mirror is put at the commit, or given the saved changes, again: it may have followed the other until now.
  rm -f "$STATE_DIR/deployed-commit"
  with_lock sync_checkout_without_restart || die "The first synchronization of the checkout failed."
  local install_options=()
  [ -n "$runner" ] && install_options+=(--runner "$runner")
  [ "$replace_data" -eq 1 ] && install_options+=(--replace-data)
  [ "$data" = "off" ] && install_options+=(--code-only)
  remote_tool install "$storage" "$port" "$label" ${install_options[@]+"${install_options[@]}"} || die "The mirror application could not be installed."
  if [ "$data" = "on" ]; then
    with_lock sync_data || die "The first synchronization of the data failed."
  fi
  install_agents
  mark_development_copy "$MIRROR_ADDRESS"
  show_status
}

show_status() {
  local agent host
  echo "Mirror: $MIRROR_SSH, checkout $MIRROR_REPO, storage $MIRROR_STORAGE, port $MIRROR_PORT"
  if [ "$MIRROR_FOLLOW" = "commits" ]; then
    echo "Follows: the commits of this checkout (the mirror runs $(cut -c1-9 "$STATE_DIR/deployed-commit" 2>/dev/null || echo none); this checkout is on $(git -C "$LOCAL_REPO" rev-parse --short=9 HEAD 2>/dev/null))"
  else
    echo "Follows: every saved change of this checkout"
  fi
  echo "Last checkout synchronization: $(cat "$STATE_DIR/last-code-sync" 2>/dev/null || echo never)"
  if [ "$MIRROR_DATA" = "on" ]; then
    echo "Last data synchronization:     $(cat "$STATE_DIR/last-data-sync" 2>/dev/null || echo never)"
  else
    echo "Data: the mirror keeps its own (code-only); the data of this Mac is not sent"
  fi
  for agent in "$AGENT_WATCH" $([ "$MIRROR_DATA" = "on" ] && echo "$AGENT_DATA"); do
    if launchctl print "gui/$(id -u)/$agent" > /dev/null 2>&1; then
      echo "Agent $agent: loaded"
    else
      echo "Agent $agent: not loaded"
    fi
  done
  [ -z "$MIRROR_ADDRESS" ] || echo "This Mac: a development copy, its application names $MIRROR_ADDRESS as the server with the data in use"
  host="${MIRROR_SSH#*@}"
  echo "Mirror application: $(curl -s -m 5 "http://$host:$MIRROR_PORT/healthz" || echo 'not answering')"
}

uninstall_mirror() {
  local agent
  for agent in "$AGENT_WATCH" "$AGENT_DATA"; do
    launchctl bootout "gui/$(id -u)/$agent" 2>/dev/null || true
    rm -f "$AGENTS_DIR/$agent.plist"
  done
  # The application of this Mac stops saying it is a development copy.
  (
    [ -f "$CONFIG_FILE" ] && . "$CONFIG_FILE"
    rm -f "${LOCAL_STORAGE:-$HOME/DriveTestAnalyzer}/config/development-copy-of"
  )
  log "The agents of this Mac are removed."
  if [ "${1:-}" = "--mirror" ]; then
    load_config
    remote_tool uninstall
  fi
}

command="${1:-}"
[ $# -gt 0 ] && shift
case "$command" in
  install) install_mirror "$@" ;;
  key) show_key ;;
  code) load_config; with_lock sync_checkout_now ;;
  data) load_config; with_lock sync_data ;;
  all) load_config; with_lock sync_checkout_now || exit 1; [ "$MIRROR_DATA" = "on" ] || exit 0; with_lock sync_data ;;
  watch) load_config; watch_code ;;
  address) load_config; set_address "$@" ;;
  status) load_config; show_status ;;
  restart-mirror) load_config; remote_tool restart ;;
  uninstall) uninstall_mirror "$@" ;;
  *) usage; exit 1 ;;
esac
