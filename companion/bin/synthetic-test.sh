#!/system/bin/sh
# RF04: End-to-end synthetic recovery test using strictly isolated fixtures.
# No real AshLooper logs, settings, module markers or service scripts are changed.
set -eu
umask 077

engine=${1:-}
case "$engine" in
    */companion.sh) ;;
    *) printf '%s\n' 'RF04_SYNTHETIC_REFUSED invalid engine path' >&2; exit 2 ;;
esac
[ -f "$engine" ] || { printf '%s\n' 'RF04_SYNTHETIC_REFUSED missing engine' >&2; exit 2; }

parent=${ARC_SYNTHETIC_TMPDIR:-/data/local/tmp}
[ -d "$parent" ] || { printf '%s\n' 'RF04_SYNTHETIC_REFUSED missing isolated temporary parent' >&2; exit 2; }
root=$(mktemp -d "$parent/ashrexcue-rf04-synthetic.XXXXXXXX") || exit 1
case "$root" in "$parent"/ashrexcue-rf04-synthetic.*) ;; *) printf '%s\n' 'RF04_SYNTHETIC_REFUSED unsafe temporary path' >&2; exit 2 ;; esac
cleanup() {
    case "$root" in "$parent"/ashrexcue-rf04-synthetic.*) rm -rf "$root" ;; esac
}
trap cleanup EXIT
trap 'exit 130' INT TERM HUP

mkdir -p "$root/logs" "$root/modules/AshLooper" "$root/modules/rf04_fixture" \
    "$root/service.d" "$root/vault" "$root/state"

printf 'id=AshLooper\nname=Isolated fake core\n' > "$root/modules/AshLooper/module.prop"
printf 'boot=booted\nboot_id=rf04-isolated-test-boot\n' > "$root/modules/AshLooper/settings.prop"
printf 'id=rf04_fixture\nname=RF04 Synthetic Module (not installed)\n' > "$root/modules/rf04_fixture/module.prop"
# A fake disabled-marker file exists ONLY inside this temporary sandbox.
: > "$root/modules/rf04_fixture/disable"
: > "$root/service.d/rf04_example.sh"
chmod 0644 "$root/service.d/rf04_example.sh"
printf '%s\n' 'FAKE SCRIPT BACKUP: not real code' > "$root/vault/rf04_example.sh.svc.755"
log="$root/logs/AshReXcueSession-synthetic.log"
printf '[00:00:00] >[◆◆◆ NEW BOOT isolated ◆◆◆]<\n' > "$log"

# Every ARC_* production path is replaced with a path INSIDE the sandbox.
# The notifier override is used ONLY for offline tests; the device normally
# uses the actual Android notification service, with an unmistakable test tag.
run_fixture() {
    ARC_STATE="$root/state" \
    ARC_LOGS="$root/logs" \
    ARC_MODULES="$root/modules" \
    ARC_VAULT="$root/vault" \
    ARC_SCRIPTS="$root/service.d" \
    ARC_SETTINGS="$root/modules/AshLooper/settings.prop" \
    ARC_PARSER="${engine%/*}/parse-recovery.awk" \
    ARC_TEST_BOOT_ID=rf04-isolated-test-boot \
    ARC_TEST_STABLE=yes \
    ARC_SYNTHETIC_TEST=yes \
    ARC_TEST_NOTIFY="${ARC_SYNTHETIC_NOTIFIER:-}" \
    ARC_RETRY_SECONDS=0 \
    sh "$engine" "$1"
}

run_fixture seed || exit 1
printf '[00:00:01] >[Lockdown Mode Activated]<\n' >> "$log"
printf '[00:00:02] >[Disabled module: rf04_fixture]<\n' >> "$log"
printf '[00:00:03] >[Disabled script: /data/adb/service.d/rf04_example.sh -> /data/adb/ashlooper/rf04_example.sh.svc.755 (Dummy created)]<\n' >> "$log"

run_fixture notify-pending || { printf '%s\n' 'RF04_SYNTHETIC_FAIL notification pathway rejected' >&2; exit 1; }

set -- "$root/state/history/"*.tsv
[ -f "$1" ] || { printf '%s\n' 'RF04_SYNTHETIC_FAIL history missing' >&2; exit 1; }
report=$1
# Exact kind/ID verification of BOTH fake items, not just successful transport.
awk -F '\t' '
  $1 == "module" && $2 == "rf04_fixture" && $5 == "confirmed" {m++}
  $1 == "script" && $2 == "svc:rf04_example.sh" && $5 == "confirmed" {s++}
  END {exit !(m == 1 && s == 1)}
' "$report" || { printf '%s\n' 'RF04_SYNTHETIC_FAIL fake module or script not attributed' >&2; exit 1; }
[ ! -s "$root/state/pending.tsv" ] || { printf '%s\n' 'RF04_SYNTHETIC_FAIL pending report not cleared' >&2; exit 1; }
set -- "$root/state/delivered/"*
[ -f "$1" ] || { printf '%s\n' 'RF04_SYNTHETIC_FAIL notification ACK missing' >&2; exit 1; }

# A second scan must not send another notification or generate a second ACK.
run_fixture notify-pending || exit 1
[ "$(find "$root/state/delivered" -type f | wc -l | tr -d ' ')" = 1 ] || {
    printf '%s\n' 'RF04_SYNTHETIC_FAIL duplicate notification ACK' >&2; exit 1;
}
printf '%s\n' 'RF04_SYNTHETIC_PASS module=rf04_fixture script=rf04_example.sh notified=1 ack=1 duplicates=0 originals_untouched=yes'
