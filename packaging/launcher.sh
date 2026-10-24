#!/bin/bash
# ApexCompanion launcher. Normally run by the app's host binary (Contents/MacOS/ApexCompanion);
# can be run directly for tests with APEX_NONINTERACTIVE=1 (dialogs print to stderr instead).
#
# Test env:  APEX_NONINTERACTIVE=1  APEX_PERSONA=closer|whip  APEX_ACTION="Stop"|"Switch persona"|...
#            APEX_BLOCK / APEX_ALLOW (first-run site answers)  APEX_TEST_ARGS="--image F --mute"
#            (test args skip the Screen Recording gate: apex.py doesn't capture with --image).
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"            # Contents/Resources
APP_SRC="$HERE/app"
APP_BIN="${APEX_APP_BIN:-$HERE/../MacOS/ApexCompanion}"
APEX_HOME="${APEX_HOME:-$HOME/Library/Application Support/ApexCompanion}"
NONINT="${APEX_NONINTERACTIVE:-0}"
MODEL_ID="mlx-community/gemma-4-e4b-it-8bit"
MODEL_CACHE_NAME="models--mlx-community--gemma-4-e4b-it-8bit"
VENV="$APEX_HOME/venv"
PY="$VENV/bin/python"
WORK="$APEX_HOME/app"
PIDFILE="$APEX_HOME/coach.pid"
CONFIG="$APEX_HOME/config"
SITES="$APEX_HOME/sites.txt"
LOGDIR="$APEX_HOME/logs"
LOCK="$APEX_HOME/setup.lock"
DEPS_STAMP="mlx-vlm==0.7.10 pillow constraints-v1"
LABEL_CLOSER="The Closer — arrogant dealmaker"
LABEL_WHIP="The Whip — cold Southern operator"

# Finder launches apps with a bare PATH; uv's installer puts uv in ~/.local/bin.
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export UV_PYTHON_INSTALL_DIR="$APEX_HOME/python" UV_PYTHON_PREFERENCE=only-managed UV_CACHE_DIR="$APEX_HOME/uv-cache"

mkdir -p "$APEX_HOME" "$LOGDIR" || exit 1
exec 3>>"$LOGDIR/launcher.log"

log() {
    printf '%s [%s] %s\n' "$(date '+%F %T')" "$$" "$*" >&3
    [ "$NONINT" = 1 ] && printf '[apex] %s\n' "$*" >&2
    return 0
}

# ---- UI helpers. User-visible text goes to osascript as argv, never spliced into script source.
dialog() {  # dialog MESSAGE DEFAULT BUTTON... -> prints the button clicked ("" if cancelled)
    local msg="$1" def="$2"; shift 2
    if [ "$NONINT" = 1 ]; then
        printf '[dialog] %s\n[dialog] buttons: %s -> %s\n' "$msg" "$*" "$def" >&2; echo "$def"; return
    fi
    osascript -e 'on run argv' -e 'set btns to items 3 thru -1 of argv' -e 'try' \
        -e 'activate' \
        -e 'return button returned of (display dialog (item 1 of argv) buttons btns default button (item 2 of argv) with title "ApexCompanion" with icon note)' \
        -e 'on error' -e 'return ""' -e 'end try' -e 'end run' "$msg" "$def" "$@" 2>>"$LOGDIR/launcher.log"
}

ask_text() {  # ask_text PROMPT ENVVAR -> prints the typed text ("" if skipped)
    if [ "$NONINT" = 1 ]; then
        printf '[ask] %s -> %s\n' "$1" "${!2:-}" >&2; echo "${!2:-}"; return
    fi
    osascript -e 'on run argv' -e 'try' -e 'activate' \
        -e 'return text returned of (display dialog (item 1 of argv) default answer "" buttons {"Skip", "OK"} default button "OK" cancel button "Skip" with title "ApexCompanion")' \
        -e 'on error' -e 'return ""' -e 'end try' -e 'end run' "$1" 2>>"$LOGDIR/launcher.log"
}

choose() {  # choose PROMPT DEFAULT ITEM... -> prints the item picked ("" if cancelled)
    local prompt="$1" def="$2"; shift 2
    if [ "$NONINT" = 1 ]; then
        printf '[choose] %s\n[choose] items: %s -> %s\n' "$prompt" "$*" "$def" >&2; echo "$def"; return
    fi
    osascript -e 'on run argv' -e 'activate' \
        -e 'set r to choose from list (items 3 thru -1 of argv) with prompt (item 1 of argv) default items {item 2 of argv} with title "ApexCompanion"' \
        -e 'if r is false then return ""' -e 'return item 1 of r' -e 'end run' "$prompt" "$def" "$@" 2>>"$LOGDIR/launcher.log"
}

notify() {
    log "notify: $1"
    [ "$NONINT" = 1 ] && return
    osascript -e 'on run argv' -e 'display notification (item 1 of argv) with title "ApexCompanion"' -e 'end run' "$1" >/dev/null 2>&1
}

fail() {  # fail MESSAGE  (shows it with the log location, exits)
    log "FAIL: $1"
    dialog "$1

Details are in: $LOGDIR" "OK" "OK" >/dev/null
    exit 1
}

cfg_get() { [ -f "$CONFIG" ] && sed -n "s/^$1=//p" "$CONFIG" | tail -1; }
cfg_set() {
    local tmp="$CONFIG.tmp"
    { [ -f "$CONFIG" ] && grep -v "^$1=" "$CONFIG"; echo "$1=$2"; } > "$tmp" && mv "$tmp" "$CONFIG"
}
persona_name() { [ "$1" = whip ] && echo "The Whip" || echo "The Closer"; }

# ---- running coach
coach_pid() {
    local pid
    pid="$(cat "$PIDFILE" 2>/dev/null)" || return 1
    [[ "$pid" =~ ^[0-9]+$ ]] || return 1
    # pid reuse guard: the live process must actually be our apex.py.
    kill -0 "$pid" 2>/dev/null && ps -p "$pid" -o command= | grep -q "apex.py" && { echo "$pid"; return 0; }
    return 1
}

stop_coach() {
    local pid; pid="$(coach_pid)" || { rm -f "$PIDFILE"; return 0; }
    touch "$APEX_HOME/stop.$pid"   # tells the launcher hosting this coach that we stopped it on purpose
    log "stopping coach pid $pid"
    kill -INT "$pid" 2>/dev/null   # apex.py prints session stats on Ctrl-C
    for _ in $(seq 20); do kill -0 "$pid" 2>/dev/null || break; sleep 0.5; done
    kill -0 "$pid" 2>/dev/null && { log "no exit on INT; TERM"; kill -TERM "$pid" 2>/dev/null; sleep 2; }
    kill -0 "$pid" 2>/dev/null && { log "no exit on TERM; KILL"; kill -KILL "$pid" 2>/dev/null; }
    rm -f "$PIDFILE"
    log "coach stopped"
}

open_sites() {
    [ -f "$SITES" ] || (cd "$WORK" && "$PY" sites_onboard.py "$SITES" "" "") >&3 2>&1
    if [ "$NONINT" = 1 ]; then log "would open $SITES in TextEdit"; else open -e "$SITES"; fi
    notify "Saved changes apply within 10 seconds."
}

control_menu() {
    local pid="$1" p; p="$(cfg_get persona)"
    local pick
    pick="$(choose "ApexCompanion is coaching as $(persona_name "$p")." "${APEX_ACTION:-Keep going}" \
        "Stop" "Switch persona" "Edit my sites" "Keep going")"
    log "control menu: '${pick}' (pid $pid)"
    case "$pick" in
        "Stop") stop_coach; notify "Coach stopped. Open ApexCompanion to start again." ;;
        "Switch persona") stop_coach; start_flow ;;
        "Edit my sites") open_sites ;;
        *) : ;;
    esac
}

# ---- setup steps
check_machine() {
    [ "$(uname -m)" = arm64 ] || fail "Sorry: ApexCompanion needs a Mac with Apple Silicon (M1 or newer). This Mac has an Intel chip."
    local major; major="$(sw_vers -productVersion | cut -d. -f1)"
    [ "${major:-0}" -ge 14 ] 2>/dev/null || fail "Sorry: ApexCompanion needs macOS 14 (Sonoma) or newer. This Mac has macOS $(sw_vers -productVersion). Update in System Settings → General → Software Update."
    local gb=$(( $(sysctl -n hw.memsize) / 1073741824 ))
    log "machine: arm64, macOS $(sw_vers -productVersion), ${gb} GB RAM"
    if [ "$gb" -lt 16 ] && [ "$(cfg_get ram_warned)" != 1 ]; then
        local b; b="$(dialog "Heads up: this Mac has ${gb} GB of memory. The coach's brain uses about 11 GB while it runs, so 16 GB or more is recommended. On this Mac other apps may slow down." "Try anyway" "Quit" "Try anyway")"
        [ "$b" = "Try anyway" ] || exit 0
        cfg_set ram_warned 1
    fi
}

free_gb() { df -Pk "$APEX_HOME" | awk 'NR==2 {print int($4/1048576)}'; }

ensure_uv() {
    UV="$(command -v uv)" && { log "uv: $UV"; return 0; }
    log "uv not found"
    if [ "$NONINT" = 1 ] && [ "${APEX_ALLOW_UV_INSTALL:-0}" != 1 ]; then fail "uv is not installed (set APEX_ALLOW_UV_INSTALL=1 to allow installing it)"; fi
    local b; b="$(dialog "First-time setup: ApexCompanion needs a small free tool called “uv” (by Astral) to set up its Python engine. It installs into your home folder, no password needed. Install it now? (needs internet, about 30 MB)" "Install" "Quit" "Install")"
    [ "$b" = Install ] || exit 0
    notify "Installing setup tool…"
    # UV_NO_MODIFY_PATH: don't edit the user's shell profile files; we call uv by full path.
    curl -LsSf https://astral.sh/uv/install.sh | env UV_NO_MODIFY_PATH=1 sh >&3 2>&1 \
        || fail "Couldn't install the setup tool (uv). Check your internet connection and open ApexCompanion again."
    UV="$(command -v uv)" || fail "The setup tool (uv) installed but can't be found."
}

ensure_venv() {
    if [ -x "$PY" ] && [ "$(cat "$VENV/.apex-ok" 2>/dev/null)" = "$DEPS_STAMP" ]; then log "venv ok"; return 0; fi
    [ "$(free_gb)" -ge 2 ] || fail "Not enough free disk space for setup (need about 2 GB free; you have $(free_gb) GB)."
    notify "Setting up (one time, a few minutes)…"
    log "creating venv at $VENV"
    case "$VENV" in "$APEX_HOME"/venv) rm -rf "$VENV" ;; esac
    "$UV" venv --python 3.12 "$VENV" >&3 2>&1 || fail "Setup failed while creating the Python engine. Check your internet connection and open ApexCompanion again."
    "$UV" pip install --python "$PY" -c "$HERE/constraints.txt" "mlx-vlm==0.7.10" pillow >&3 2>&1 \
        || fail "Setup failed while installing the coach's engine. Check your internet connection and open ApexCompanion again."
    "$PY" -c "import mlx_vlm, PIL, huggingface_hub" >&3 2>&1 || fail "Setup finished but the engine doesn't load."
    echo "$DEPS_STAMP" > "$VENV/.apex-ok"
    "$UV" cache clean >&3 2>&1 || true   # ~850 MB of downloaded wheels; the venv doesn't need them
    log "venv ready: $("$PY" -c 'import mlx_vlm,sys;print("mlx-vlm",mlx_vlm.__version__,"python",sys.version.split()[0])')"
}

sync_app() {
    mkdir -p "$WORK"
    # Run from a copy in APEX_HOME: apex.py writes logs/ next to itself, and the app bundle may be
    # read-only (Gatekeeper App Translocation) or signed (writing inside breaks the signature).
    cp "$APP_SRC"/*.py "$WORK/" || fail "Couldn't copy the app files into $WORK."
}

model_complete() {  # model_complete HUB_DIR -> 0 if every shard in the index is present
    local snap idx shards f n=0 want
    for snap in "$1/$MODEL_CACHE_NAME"/snapshots/*/; do
        idx="$snap/model.safetensors.index.json"
        [ -s "$idx" ] && [ -s "$snap/config.json" ] && [ -s "$snap/tokenizer.json" ] || continue
        shards="$(grep -o 'model-[0-9]*-of-[0-9]*\.safetensors' "$idx" | sort -u)"
        [ -n "$shards" ] || continue
        want="$(echo "$shards" | head -1 | sed 's/.*-of-0*\([0-9]*\)\.safetensors/\1/')"
        n=0
        for f in $shards; do [ -s "$snap/$f" ] && n=$((n + 1)); done   # -s follows the blob symlink
        [ "$n" = "$want" ] && { log "model found: $snap ($n/$want shards)"; return 0; }
    done
    return 1
}

ensure_model() {
    local default_hub="${HF_HOME:-$HOME/.cache/huggingface}/hub"
    if model_complete "$default_hub"; then MODEL_HF_HOME=""; return 0; fi
    if model_complete "$APEX_HOME/huggingface/hub"; then MODEL_HF_HOME="$APEX_HOME/huggingface"; return 0; fi
    log "model not cached"
    if [ "$NONINT" = 1 ] && [ "${APEX_ALLOW_DOWNLOAD:-0}" != 1 ]; then fail "model not cached (set APEX_ALLOW_DOWNLOAD=1 to download ~8.3 GB)"; fi
    [ "$(free_gb)" -ge 10 ] || fail "Not enough free disk space for the coach's brain: it needs about 10 GB free and you have $(free_gb) GB. Free some space and open ApexCompanion again."
    local b; b="$(dialog "One-time download of the coach's brain (about 8.3 GB). It runs entirely on this Mac afterwards; nothing you do is ever uploaded.

This can take 10–40 minutes depending on your internet. Keep the Mac plugged in and awake. You'll get a notification when it's done." "Download" "Quit" "Download")"
    [ "$b" = Download ] || exit 0
    notify "Downloading the coach's brain (8.3 GB)… this takes a while."
    MODEL_HF_HOME="$APEX_HOME/huggingface"
    # The only network use after setup: fetch the weights once. caffeinate keeps the Mac awake.
    HF_HOME="$MODEL_HF_HOME" HF_HUB_OFFLINE=0 caffeinate -i "$PY" -c \
        "from huggingface_hub import snapshot_download; snapshot_download('$MODEL_ID')" >&3 2>&1 \
        || fail "The download didn't finish (internet dropped?). Open ApexCompanion again to resume where it stopped."
    model_complete "$MODEL_HF_HOME/hub" || fail "The download finished but the files look incomplete. Open ApexCompanion again to retry."
    notify "Download complete."
}

pick_persona() {
    local last; last="$(cfg_get persona)"
    local def="$LABEL_CLOSER"; [ "$last" = whip ] && def="$LABEL_WHIP"
    if [ "$NONINT" = 1 ] && [ -n "${APEX_PERSONA:-}" ]; then
        [ "$APEX_PERSONA" = whip ] && def="$LABEL_WHIP" || def="$LABEL_CLOSER"
    fi
    local pick; pick="$(choose "Pick your coach:" "$def" "$LABEL_CLOSER" "$LABEL_WHIP")"
    case "$pick" in
        "$LABEL_CLOSER") PERSONA=closer ;;
        "$LABEL_WHIP") PERSONA=whip ;;
        *) log "persona picker cancelled"; exit 0 ;;
    esac
    cfg_set persona "$PERSONA"
    log "persona: $PERSONA"
}

onboard_sites() {
    [ "$(cfg_get onboarded)" = 1 ] && return 0
    local block allow
    block="$(ask_text "Sites or apps you NEVER want to get lost in (comma-separated, e.g. reddit, instagram, steam)" APEX_BLOCK)"
    allow="$(ask_text "Anything that should ALWAYS count as work? (optional)" APEX_ALLOW)"
    (cd "$WORK" && "$PY" sites_onboard.py "$SITES" "$block" "$allow") >&3 2>&1 || fail "Couldn't save your site list to $SITES."
    log "sites saved: $(grep -v '^#' "$SITES" | grep -v '^$' | tr '\n' ' ')"
    cfg_set onboarded 1
}

screen_permission_ok() {
    if [ -n "${APEX_TEST_ARGS:-}" ]; then log "test args set: skipping Screen Recording gate"; return 0; fi
    local r; r="$("$APP_BIN" --preflight 2>>"$LOGDIR/launcher.log")"
    log "screen recording preflight: '${r}'"
    [ "$r" = true ] && return 0
    # Ask once through the system API so ApexCompanion shows up in the Settings list, then open it.
    "$APP_BIN" --request >/dev/null 2>&1
    [ "$NONINT" = 1 ] || open "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"
    dialog "One last step: let ApexCompanion see your screen. Screenshots stay on this Mac and are deleted after each check.

1. In the System Settings window that just opened, find “ApexCompanion” in the Screen Recording list.
2. Turn its switch ON (your Mac may ask for your password or Touch ID). If macOS offers “Quit & Reopen”, choose it.
3. Then open ApexCompanion again." "OK" "OK" >/dev/null
    log "permission missing: told user how to grant it"
    return 1
}

run_coach() {
    local args=(apex.py --persona "$PERSONA" --sites "$SITES")
    if [ -n "${APEX_TEST_ARGS:-}" ]; then read -r -a extra <<< "$APEX_TEST_ARGS"; args+=("${extra[@]}"); fi
    log "starting coach: ${args[*]} (HF_HOME=${MODEL_HF_HOME:-default})"
    printf '\n===== %s start %s =====\n' "$(date '+%F %T')" "$PERSONA" >> "$LOGDIR/apex.log"
    # The app has no window, so this notification is the only place a new user learns how to stop it.
    notify "Watching as $(persona_name "$PERSONA"). Open ApexCompanion again to stop or edit your sites."
    # Foreground subshell, exec'd into python: the pid is known for the pidfile, Ctrl-C (SIGINT)
    # still reaches python (bash ignores SIGINT only for background jobs), and the app host keeps
    # running as python's parent for as long as the coach runs.
    # (macOS /bin/bash is 3.2: no $BASHPID, so a tiny sh records its own $$ and execs python.)
    (
        cd "$WORK" || exit 1
        umask 077  # apex.log and the session logs are readable by this user only
        [ -n "${MODEL_HF_HOME:-}" ] && export HF_HOME="$MODEL_HF_HOME"
        # APEX_SCREEN_OK: this app already passed the CoreGraphics preflight; skip apex.py's swift check,
        # which would prompt to install developer tools on Macs without them.
        export HF_HUB_OFFLINE=1 PYTHONUNBUFFERED=1 APEX_SCREEN_OK=1
        exec /bin/sh -c 'echo $$ > "$1"; echo $$ > "$2"; shift 2; exec "$@"' sh \
            "$PIDFILE" "$APEX_HOME/run.$$" "$PY" "${args[@]}" >> "$LOGDIR/apex.log" 2>&1
    )
    local rc=$? mypid; mypid="$(cat "$APEX_HOME/run.$$" 2>/dev/null)"; rm -f "$APEX_HOME/run.$$"
    log "coach pid $mypid exited rc=$rc"
    if [ -f "$APEX_HOME/stop.$mypid" ]; then rm -f "$APEX_HOME/stop.$mypid"; return 0; fi   # stopped on purpose
    [ "$(cat "$PIDFILE" 2>/dev/null)" = "$mypid" ] && rm -f "$PIDFILE"
    if [ "$rc" -ne 0 ]; then
        dialog "The coach stopped unexpectedly. Last lines of its log:

$(tail -n 4 "$LOGDIR/apex.log" | cut -c1-200)

Open ApexCompanion to try again. Full log: $LOGDIR/apex.log" "OK" "OK" >/dev/null
    fi
    return "$rc"
}

take_lock() {
    if mkdir "$LOCK" 2>/dev/null; then echo $$ > "$LOCK/pid"; trap 'rm -rf "$LOCK"' EXIT; return 0; fi
    local holder; holder="$(cat "$LOCK/pid" 2>/dev/null)"
    if [ -n "$holder" ] && kill -0 "$holder" 2>/dev/null; then return 1; fi
    rm -rf "$LOCK"; mkdir "$LOCK" 2>/dev/null || return 1
    echo $$ > "$LOCK/pid"; trap 'rm -rf "$LOCK"' EXIT
}

start_flow() {
    take_lock || { notify "Still setting up… hang tight."; exit 0; }
    check_machine
    ensure_uv
    ensure_venv
    sync_app
    ensure_model
    pick_persona
    onboard_sites
    screen_permission_ok || exit 0
    rm -rf "$LOCK"; trap - EXIT
    run_coach
}

log "launcher start (host=${APEX_HOST:-0}, nonint=$NONINT, home=$APEX_HOME)"
if pid="$(coach_pid)"; then control_menu "$pid"; else start_flow; fi
