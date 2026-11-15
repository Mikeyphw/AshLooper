#!/system/bin/sh
MODDIR="${0%/*}"
/system/bin/sh "$MODDIR/bin/companion.sh" status
printf '\nPosting test Android notification (without changing module states)...\n'
/system/bin/sh "$MODDIR/bin/companion.sh" test-notification
