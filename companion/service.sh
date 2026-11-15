#!/system/bin/sh
# Dedicated late-start notification worker; never blocks the boot process.
MODDIR="${0%/*}"
umask 077
( /system/bin/sh "$MODDIR/bin/companion.sh" run ) >/dev/null 2>&1 &
exit 0
