#!/system/bin/sh
# AshReXcue Companion RF02 -- consumes the source-pinned AshLooper recovery journal.
# No module state writes. No reboot. No recovery-engine changes at runtime.
umask 077

STATE="${ARC_STATE:-/data/adb/ashrexcue-companion}"
SOURCE="${ARC_SOURCE:-/data/adb/ashlooper}"
MODULES="${ARC_MODULES:-/data/adb/modules}"
ASH_SETTINGS="${ARC_SETTINGS:-/data/adb/modules/AshLooper/settings.prop}"
PENDING="$SOURCE/disabled-report.pending"
LAST="$SOURCE/disabled-report.last"
HISTORY="$STATE/history"
SVC_VAULT="$SOURCE"
LOCK="$STATE/.notify-lock"
WORK=""

say() { printf '%s\n' "AshReXcue Companion: $*"; }
cleanup() {
    [ -z "$WORK" ] || rm -rf "$WORK"
    if [ -f "$LOCK/pid" ] && [ "$(cat "$LOCK/pid" 2>/dev/null)" = "$$" ]; then
        rm -f "$LOCK/pid"
        rmdir "$LOCK" 2>/dev/null || :
    fi
}
trap cleanup EXIT HUP INT TERM

boot_id() {
    if [ -n "${ARC_TEST_BOOT_ID:-}" ]; then
        printf '%s' "$ARC_TEST_BOOT_ID"
    else
        cat /proc/sys/kernel/random/boot_id 2>/dev/null | tr -d '\r\n'
    fi
}

initialize() {
    mkdir -p "$HISTORY" "$STATE/delivered" || return 1
    chmod 700 "$STATE" "$HISTORY" "$STATE/delivered" 2>/dev/null || return 1
}

lock_notification() {
    if mkdir "$LOCK" 2>/dev/null; then
        printf '%s\n' "$$" > "$LOCK/pid"
        return 0
    fi
    oldpid=$(cat "$LOCK/pid" 2>/dev/null || :)
    case "$oldpid" in ''|*[!0-9]*) oldpid=0 ;; esac
    if [ "$oldpid" -gt 0 ] && kill -0 "$oldpid" 2>/dev/null; then
        say 'Another notification worker is active.'
        return 1
    fi
    rm -f "$LOCK/pid" 2>/dev/null || :
    rmdir "$LOCK" 2>/dev/null || return 1
    mkdir "$LOCK" 2>/dev/null || return 1
    printf '%s\n' "$$" > "$LOCK/pid"
}

stable_boot() {
    [ "${ARC_TEST_STABLE:-}" = "yes" ] && return 0
    [ "$(getprop sys.boot_completed 2>/dev/null)" = "1" ] || return 1
    current=$(boot_id)
    [ -n "$current" ] || return 1
    [ "$(sed -n '/^boot=/{s/^boot=//;p;q;}' "$ASH_SETTINGS" 2>/dev/null)" = 'booted' ] || return 1
    [ "$(sed -n '/^boot_id=/{s/^boot_id=//;p;q;}' "$ASH_SETTINGS" 2>/dev/null)" = "$current" ]
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

# True only when the recorded action is still reflected in the root module state.
# Module IDs are matched to either folder names or module.prop IDs, never paths.
verify_disabled() {
    kind=$1
    identifier=$2
    case "$identifier" in ''|.|..|*/*|*[!a-zA-Z0-9_.@+:-]*) return 1 ;; esac
    case "$kind" in
        module)
            # Duplicate IDs are ambiguous and cannot be attributed safely.
            matches=0
            enabled_markers=0
            for mod in "$MODULES"/*; do
                [ -d "$mod" ] || continue
                folder=${mod##*/}
                prop_id=$(sed -n '/^id=/{s/^id=//;p;q;}' "$mod/module.prop" 2>/dev/null | tr -d '\r')
                if [ "$identifier" = "$folder" ] || [ "$identifier" = "$prop_id" ]; then
                    matches=$((matches + 1))
                    [ -f "$mod/disable" ] && enabled_markers=$((enabled_markers + 1))
                fi
            done
            [ "$matches" -eq 1 ] && [ "$enabled_markers" -eq 1 ] && return 0
            ;;
        script)
            case "$identifier" in svc:*.sh) ;; *) return 1 ;; esac
            fname=${identifier#svc:}
            for backup in "$SVC_VAULT/$fname".svc.*; do
                [ -f "$backup" ] && return 0
            done
            ;;
    esac
    return 1
}

make_report() {
    # Consume only complete journal lines and verify present state.
    # Ignore malformed or untrusted entries rather than guessing attribution.
    : > "$WORK/verified.tsv"
    : > "$WORK/events.tsv"
    tab=$(printf '\t')
    while IFS="$tab" read -r kind identifier name; do
        case "$kind" in module|script) ;; *) continue ;; esac
        [ -n "$identifier" ] || continue
        [ -n "$name" ] || name=$identifier
        name=$(printf '%s' "$name" | tr '\t\r\n' '   ' | cut -c 1-90)
        if verify_disabled "$kind" "$identifier"; then
            printf '%s\t%s\t%s\tconfirmed\n' "$kind" "$identifier" "$name" >> "$WORK/events.tsv"
            printf '%s\t%s\t%s\n' "$kind" "$identifier" "$name" >> "$WORK/verified.tsv"
        else
            printf '%s\t%s\t%s\tunverified-or-restored\n' "$kind" "$identifier" "$name" >> "$WORK/events.tsv"
        fi
    done < "$PENDING"
    # Deduplicate based on kind and ID, retaining first verified name.
    awk -F '\t' '!seen[$1 SUBSEP $2]++' "$WORK/verified.tsv" > "$WORK/unique.tsv" || return 1
    count=$(wc -l < "$WORK/unique.tsv" | tr -d ' ')
    title="AshReXcue: $count item(s) disabled"
    body='Bootloop recovery completed. Still disabled:'
    shown=0
    while IFS="$tab" read -r kind identifier name; do
        [ "$shown" -lt 12 ] || break
        if [ "$kind" = 'script' ]; then label="Script: $name"; else label=$name; fi
        body="$body
• $label ($identifier)"
        shown=$((shown + 1))
    done < "$WORK/unique.tsv"
    if [ "$count" -gt "$shown" ]; then
        body="$body
...and $((count - shown)) more. Review companion history."
    fi
    body="$body
Review/restore manually in your root manager."
}

archive_report() {
    # We only move the report once notification delivery is accepted (or there
    # are no confirmed disabled modules). Never discard a failed delivery.
    mv -f "$PENDING" "$LAST"
}

send_pending() {
    stable_boot || { say 'Not a verified stable boot; leaving journal unchanged.'; return 2; }
    [ -s "$PENDING" ] || { say 'No pending recovery report.'; return 0; }
    initialize || return 1
    lock_notification || return 1
    WORK="$STATE/.work.$$"
    mkdir -m 700 "$WORK" || return 1
    cp "$PENDING" "$WORK/source.tsv" || return 1
    make_report || return 1
    bid=$(boot_id)
    case "$bid" in ''|*[!a-zA-Z0-9-]*) say 'Invalid boot ID'; return 1 ;; esac
    sum=$(sha256sum "$WORK/source.tsv" 2>/dev/null | cut -d' ' -f1)
    case "$sum" in ''|*[!0-9a-f]*) say 'Cannot hash report'; return 1 ;; esac
    key="$bid-$sum"
    archive="$HISTORY/$key.tsv"
    if [ ! -f "$archive" ]; then
        cp "$WORK/events.tsv" "$WORK/archived.tsv" || return 1
        mv -f "$WORK/archived.tsv" "$archive" || return 1
    fi
    if [ "$count" -eq 0 ]; then
        say 'Recovery recorded, but no items are still disabled; not notifying.'
        archive_report
        return $?
    fi
    if [ -f "$STATE/delivered/$key" ]; then
        say 'Delivery already acknowledged; archiving report without posting again.'
        archive_report
        return $?
    fi
    attempts=1
    while [ "$attempts" -le 4 ]; do
        if post_notification "$title" "$body"; then
            # Persist the ACK first so interrupted archival does not repost.
            printf '%s\n' "$key" > "$WORK/ack" || return 1
            mv -f "$WORK/ack" "$STATE/delivered/$key" || return 1
            archive_report || return 1
            say "Notification accepted for $count verified disabled item(s)."
            return 0
        fi
        say "Notification rejected ($attempts/4); journal preserved."
        [ "$attempts" -ge 4 ] || sleep "${ARC_RETRY_SECONDS:-5}"
        attempts=$((attempts + 1))
    done
    return 1
}

status() {
    initialize || return 1
    say "Source: $SOURCE"
    say "Current boot: $(boot_id)"
    if stable_boot; then say 'Boot state: verified stable'; else say 'Boot state: not verified stable'; fi
    if [ -s "$PENDING" ]; then say 'Pending source report: yes'; else say 'Pending source report: no'; fi
    say 'Historical reports:'
    for report in "$HISTORY"/*.tsv; do
        [ -f "$report" ] || continue
        printf '  %s\n' "${report##*/}"
    done
    if [ -f "$MODULES/ashrexcue_companion/disable" ]; then
        say 'WARNING: Companion is disabled by root manager.'
    fi
}

case "${1:-run}" in
    run)
        attempts=0
        while [ "$attempts" -lt 180 ]; do
            if stable_boot; then
                if [ -s "$PENDING" ]; then
                    send_pending
                    exit $?
                fi
                exit 0
            fi
            sleep 3
            attempts=$((attempts + 1))
        done
        say 'Stable boot not confirmed; no notification attempted.'
        exit 0
        ;;
    notify-pending) send_pending ;;
    test-notification) post_notification 'AshReXcue Companion test' 'Test only. No recovery state changed.' ;;
    status) status ;;
    *) say 'Usage: companion.sh {run|status|notify-pending|test-notification}'; exit 2 ;;
esac
