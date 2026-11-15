#!/system/bin/sh
# AshReXcue: deliver a one-shot bootloop recovery report after a stable boot.
# This helper never disables modules and never reboots the device.

REPORT_DIR="${ASHLOOPER_DIR:-/data/adb/ashlooper}"
REPORT_PENDING="$REPORT_DIR/disabled-report.pending"
REPORT_LAST="$REPORT_DIR/disabled-report.last"

# Safely quote untrusted names/IDs for the nested `su 2000 -c` shell.
# A module name can contain quotes or shell metacharacters.
shell_quote() {
    printf "'"
    printf '%s' "$1" | sed "s/'/'\\\\''/g"
    printf "'"
}

case "$1" in
    send)
        [ -s "$REPORT_PENDING" ] || exit 0
        ;;
    *)
        echo 'usage: recovery-notify.sh send' >&2
        exit 2
        ;;
esac

# One report covers all bootloop-recovery rounds until a stable boot.
# Deduplicate by (kind,id), and bound the notification text while retaining the
# full report on disk. AWK emits a count on line one and the message after it.
summary=$(awk -F '\t' '
    ($1 == "module" || $1 == "script") && length($2) > 0 {
        k = $1 SUBSEP $2
        if (seen[k]++) next
        count++
        if (count <= 12) {
            label = $3 == "" ? $2 : $3
            label = substr(label, 1, 90)
            id = substr($2, 1, 90)
            prefix = $1 == "script" ? "Script: " : ""
            lines = lines (lines == "" ? "" : "\n") "• " prefix label " (" id ")"
        }
    }
    END {
        print count + 0
        print lines
        if (count > 12) print "...and " count - 12 " more. See disabled-report.last"
        print "Review/restore in your root manager or AshReXcue Action menu."
    }
' "$REPORT_PENDING") || exit 1

count=$(printf '%s\n' "$summary" | sed -n '1p')
case "$count" in
    ''|*[!0-9]*) exit 1 ;;
esac
[ "$count" -gt 0 ] || exit 0

body=$(printf '%s\n' "$summary" | sed '1d')
if [ "$count" -eq 1 ]; then
    title="AshReXcue: 1 item disabled"
else
    title="AshReXcue: $count items disabled"
fi

# This is the same Android shell-UID notification mechanism already used by
# AshReXcue's action.sh and monitor.sh. AOSP supports BigText style.
command="/system/bin/cmd notification post -S bigtext -t $(shell_quote "$title") $(shell_quote 'ashrexcue_bootloop_recovery') $(shell_quote "$body")"

attempt=1
while [ "$attempt" -le 3 ]; do
    if su 2000 -c "$command" >/dev/null 2>&1; then
        # Do not discard the pending record before the system accepts the post.
        # The full, untruncated report remains available for later inspection.
        if mv -f "$REPORT_PENDING" "$REPORT_LAST"; then
            exit 0
        fi
        echo 'AshReXcue: notification posted but could not archive the report' >&2
        exit 1
    fi
    attempt=$((attempt + 1))
    [ "$attempt" -le 3 ] && sleep 2
done

echo 'AshReXcue: notification post failed; retained pending report' >&2
exit 1
