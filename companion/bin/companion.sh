#!/system/bin/sh
# AshReXcue Companion RF03 — read-only integration with ORIGINAL AshReXcue.
# NEVER writes to the original module, scripts, system module states or logs.
umask 077

STATE="${ARC_STATE:-/data/adb/ashrexcue-companion}"
LOGS="${ARC_LOGS:-/cache/looper}"
MODULES="${ARC_MODULES:-/data/adb/modules}"
VAULT="${ARC_VAULT:-/data/adb/ashlooper}"
SETTINGS="${ARC_SETTINGS:-/data/adb/modules/AshLooper/settings.prop}"
SCRIPTS="${ARC_SCRIPTS:-/data/adb/service.d}"
PARSER="${ARC_PARSER:-${0%/*}/parse-recovery.awk}"
CURSORS="$STATE/cursors"
QUEUE="$STATE/pending.tsv"
HISTORY="$STATE/history"
LOCK="$STATE/.monitor-lock"
WORK=""
LOCKED=0

say() { printf '%s\n' "AshReXcue Companion: $*"; }
cleanup() {
    [ -z "$WORK" ] || rm -rf "$WORK"
    if [ "$LOCKED" = 1 ]; then
        rm -f "$LOCK/pid"
        rmdir "$LOCK" 2>/dev/null || :
    fi
}
trap cleanup EXIT
trap 'exit 130' INT TERM HUP

boot_id() {
    if [ -n "${ARC_TEST_BOOT_ID:-}" ]; then
        printf '%s' "$ARC_TEST_BOOT_ID"
    else
        cat /proc/sys/kernel/random/boot_id 2>/dev/null | tr -d '\r\n'
    fi
}

stable_boot() {
    [ "${ARC_TEST_STABLE:-}" = yes ] && return 0
    [ "$(getprop sys.boot_completed 2>/dev/null)" = 1 ] || return 1
    [ ! -f "$MODULES/AshLooper/disable" ] || return 1
    [ "$(sed -n '/^boot=/{s/^boot=//;p;q;}' "$SETTINGS" 2>/dev/null)" = booted ] || return 1
    bid=$(boot_id)
    [ -n "$bid" ] || return 1
    [ "$(sed -n '/^boot_id=/{s/^boot_id=//;p;q;}' "$SETTINGS" 2>/dev/null)" = "$bid" ]
}

initialize() {
    mkdir -p "$CURSORS" "$HISTORY" "$STATE/delivered" || return 1
    chmod 700 "$STATE" "$CURSORS" "$HISTORY" "$STATE/delivered" 2>/dev/null || return 1
}

lock_monitor() {
    if mkdir "$LOCK" 2>/dev/null; then
        printf '%s\n' "$$" > "$LOCK/pid" || return 1
        LOCKED=1
        return 0
    fi
    old=$(cat "$LOCK/pid" 2>/dev/null || :)
    case "$old" in ''|*[!0-9]*) old=0 ;; esac
    if [ "$old" -gt 0 ] && kill -0 "$old" 2>/dev/null; then
        say 'Another companion worker is already active.'
        return 1
    fi
    # Only attempt stale-lock recovery; never remove a live lock.
    rm -f "$LOCK/pid" 2>/dev/null || :
    rmdir "$LOCK" 2>/dev/null || return 1
    mkdir "$LOCK" 2>/dev/null || return 1
    printf '%s\n' "$$" > "$LOCK/pid" || return 1
    LOCKED=1
}

# A stable first-line signature detects log truncation/rotation despite reuse
# of the same filename. The size offset avoids reporting historical events.
log_signature() {
    head -n 1 "$1" 2>/dev/null | sha256sum | cut -d ' ' -f 1
}
log_size() {
    wc -c < "$1" 2>/dev/null | tr -d ' '
}
valid_size() {
    case "$1" in ''|*[!0-9]*) return 1 ;; esac
}

baseline() {
    initialize || return 1
    [ -f "$STATE/.seeded" ] && { say 'Log baseline already exists; unchanged.'; return 0; }
    for f in "$LOGS"/AshReXcueSession-*.log; do
        [ -f "$f" ] || continue
        base=${f##*/}
        sig=$(log_signature "$f")
        size=$(log_size "$f")
        valid_size "$size" || return 1
        printf '%s %s\n' "$sig" "$size" > "$CURSORS/$base" || return 1
    done
    # Never emit a historical recovery notification on initial installation.
    : > "$STATE/.seeded" || return 1
    say 'Initial log baseline created (previous incidents ignored).'
}

# Read only NEW log bytes. Commit queued events before cursor updates so
# interruption cannot silently discard an incident. A duplicate scan is safe.
scan_logs() {
    [ -f "$STATE/.seeded" ] || { baseline; return $?; }
    WORK="$STATE/.work.$$"
    mkdir -m 700 "$WORK" "$WORK/cursors" || return 1
    if [ -f "$QUEUE" ]; then
        cp "$QUEUE" "$WORK/queue.tsv" || return 1
    else
        : > "$WORK/queue.tsv" || return 1
    fi
    for f in "$LOGS"/AshReXcueSession-*.log; do
        [ -f "$f" ] || continue
        base=${f##*/}
        sig=$(log_signature "$f")
        size=$(log_size "$f")
        valid_size "$size" || return 1
        prev_sig=''; prev_size=0
        if [ -f "$CURSORS/$base" ]; then
            read -r prev_sig prev_size < "$CURSORS/$base"
            valid_size "$prev_size" || prev_size=0
        fi
        if [ "$sig" != "$prev_sig" ] || [ "$size" -lt "$prev_size" ]; then
            prev_size=0
        fi
        if [ "$size" -gt "$prev_size" ]; then
            tail -c "+$((prev_size + 1))" "$f" | awk -f "$PARSER" >> "$WORK/queue.tsv" || return 1
        fi
        printf '%s %s\n' "$sig" "$size" > "$WORK/cursors/$base" || return 1
    done
    # Deduplicate by type+ID within one pending incident.
    awk -F '\t' 'NF >= 3 && !seen[$1 SUBSEP $2]++ {print}' "$WORK/queue.tsv" > "$WORK/unique.tsv" || return 1
    mv -f "$WORK/unique.tsv" "$QUEUE" || return 1
    for f in "$WORK/cursors"/*; do
        [ -f "$f" ] || continue
        mv -f "$f" "$CURSORS/${f##*/}" || return 1
    done
    rm -rf "$WORK"
    WORK=''
}

# Return a friendly label only when an ORIGINAL module is currently disabled.
# Reject duplicate IDs, traversal, malformed identifiers and unrelated modules.
verify_item() {
    kind=$1
    identifier=$2
    case "$identifier" in ''|.|..|*/*|*[!a-zA-Z0-9_.@+:-]*) return 1 ;; esac
    if [ "$kind" = module ]; then
        found=0
        disabled=0
        label=$identifier
        for mod in "$MODULES"/*; do
            [ -d "$mod" ] || continue
            folder=${mod##*/}
            declared_id=$(sed -n '/^id=/{s/^id=//;p;q;}' "$mod/module.prop" 2>/dev/null | tr -d '\r')
            if [ "$identifier" = "$folder" ] || [ "$identifier" = "$declared_id" ]; then
                found=$((found + 1))
                if [ -f "$mod/disable" ]; then
                    disabled=$((disabled + 1))
                    label=$(sed -n '/^name=/{s/^name=//;p;q;}' "$mod/module.prop" 2>/dev/null)
                    [ -n "$label" ] || label=$identifier
                fi
            fi
        done
        [ "$found" -eq 1 ] && [ "$disabled" -eq 1 ] || return 1
    elif [ "$kind" = script ]; then
        case "$identifier" in svc:*.sh) ;; *) return 1 ;; esac
        fname=${identifier#svc:}
        [ -f "$SCRIPTS/$fname" ] && [ ! -s "$SCRIPTS/$fname" ] && [ ! -x "$SCRIPTS/$fname" ] || return 1
        vault_found=0
        for bak in "$VAULT/$fname.svc."*; do
            [ -f "$bak" ] && vault_found=1
        done
        [ "$vault_found" -eq 1 ] || return 1
        label=$fname
    else
        return 1
    fi
    # Drop control characters and cap the system notification label.
    label=$(printf '%s' "$label" | tr '\t\r\n' '   ' | cut -c 1-90)
    [ -n "$label" ] || label=$identifier
    return 0
}

shell_quote() {
    # The Android shell UID receives an opaque command string: quote EVERYTHING.
    printf "'"
    printf '%s' "$1" | sed "s/'/'\\\\''/g"
    printf "'"
}

post_notification() {
    if [ -n "${ARC_TEST_NOTIFY:-}" ]; then
        "$ARC_TEST_NOTIFY" "$1" "$2"
        return $?
    fi
    title=$(shell_quote "$1")
    body=$(shell_quote "$2")
    command="/system/bin/cmd notification post -S bigtext -t $title 'ashrexcue_companion_recovery' $body"
    su 2000 -c "$command" >/dev/null 2>&1
}

make_report() {
    : > "$WORK/report.tsv" || return 1
    : > "$WORK/verified.tsv" || return 1
    tab=$(printf '\t')
    while IFS="$tab" read -r kind identifier stage; do
        case "$kind" in module|script) ;; *) continue ;; esac
        if verify_item "$kind" "$identifier"; then
            printf '%s\t%s\t%s\t%s\tconfirmed\n' "$kind" "$identifier" "$label" "$stage" >> "$WORK/report.tsv"
            printf '%s\t%s\t%s\t%s\n' "$kind" "$identifier" "$label" "$stage" >> "$WORK/verified.tsv"
        else
            printf '%s\t%s\t%s\t%s\tunverified-or-restored\n' "$kind" "$identifier" "$identifier" "$stage" >> "$WORK/report.tsv"
        fi
    done < "$QUEUE"
    count=$(wc -l < "$WORK/verified.tsv" | tr -d ' ')
    valid_size "$count" || return 1
    title="AshReXcue: $count item(s) disabled"
    body='Bootloop recovery completed. Still disabled:'
    shown=0
    while IFS="$tab" read -r kind identifier name stage; do
        [ "$shown" -lt 12 ] || break
        if [ "$kind" = script ]; then label="Script: $name"; else label=$name; fi
        body="$body
• $label ($identifier)"
        shown=$((shown + 1))
    done < "$WORK/verified.tsv"
    if [ "$count" -gt "$shown" ]; then
        body="$body
...and $((count - shown)) more; see companion history."
    fi
    body="$body
Review/restore manually in your root manager."
}

save_history() {
    checksum=$(sha256sum "$QUEUE" | cut -d ' ' -f 1)
    case "$checksum" in ''|*[!0-9a-f]*) return 1 ;; esac
    bid=$(boot_id)
    case "$bid" in ''|*[!a-zA-Z0-9-]*) return 1 ;; esac
    key="$bid-$checksum"
    archive="$HISTORY/$key.tsv"
    if [ ! -f "$archive" ]; then
        cp "$WORK/report.tsv" "$WORK/history.tsv" || return 1
        mv -f "$WORK/history.tsv" "$archive" || return 1
    fi
}

process_queue() {
    [ -s "$QUEUE" ] || { say 'No newly attributed module disables.'; return 0; }
    WORK="$STATE/.work.$$"
    mkdir -m 700 "$WORK" || return 1
    make_report || return 1
    save_history || return 1
    if [ "$count" -eq 0 ]; then
        say 'Incident recorded, but no affected items remain disabled.'
        rm -f "$QUEUE"
        return 0
    fi
    if [ -f "$STATE/delivered/$key" ]; then
        say 'Previously acknowledged incident; not reposting.'
        rm -f "$QUEUE"
        return 0
    fi
    attempt=1
    while [ "$attempt" -le 4 ]; do
        if post_notification "$title" "$body"; then
            printf '%s\n' "$key" > "$WORK/ack" || return 1
            mv -f "$WORK/ack" "$STATE/delivered/$key" || return 1
            rm -f "$QUEUE" || return 1
            say "Notification accepted for $count confirmed disabled item(s)."
            return 0
        fi
        say "Notification attempt $attempt/4 rejected; incident retained."
        [ "$attempt" -eq 4 ] || sleep "${ARC_RETRY_SECONDS:-5}"
        attempt=$((attempt + 1))
    done
    return 1
}

notify_pending() {
    stable_boot || { say 'AshReXcue has not confirmed a stable boot.'; return 2; }
    initialize || return 1
    lock_monitor || return 1
    # Standalone integration: NEVER read or write core notification journals.
    scan_logs || return 1
    process_queue
}

status() {
    initialize || return 1
    say "Original AshReXcue module: $MODULES/AshLooper"
    say "Log source: $LOGS"
    say "Current boot: $(boot_id)"
    if stable_boot; then say 'Boot: stable'; else say 'Boot: not yet confirmed stable'; fi
    if [ -f "$STATE/.seeded" ]; then say 'Log baseline: initialized'; else say 'Log baseline: not initialized'; fi
    if [ -s "$QUEUE" ]; then
        say "Pending attributed items: $(wc -l < "$QUEUE" | tr -d ' ')"
    else
        say 'Pending attributed items: none'
    fi
    say "History entries: $(find "$HISTORY" -maxdepth 1 -type f -name '*.tsv' 2>/dev/null | wc -l | tr -d ' ')"
}

case "${1:-run}" in
    seed) baseline ;;
    scan) stable_boot || { say 'Not stable; scan refused.'; exit 2; }; initialize && lock_monitor && scan_logs ;;
    run)
        iteration=0
        while [ "$iteration" -lt 180 ]; do
            if stable_boot; then
                notify_pending
                exit $?
            fi
            sleep 3
            iteration=$((iteration + 1))
        done
        say 'No stable boot observed; no notification attempted.'
        ;;
    notify-pending) notify_pending ;;
    test-notification) post_notification 'AshReXcue Companion test' 'Test only. No recovery state changed.' ;;
    status) status ;;
    *) say 'Usage: companion.sh {seed|scan|run|status|notify-pending|test-notification}'; exit 2 ;;
esac
