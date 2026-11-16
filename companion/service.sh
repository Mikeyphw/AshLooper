#!/system/bin/sh
MODDIR="${0%/*}"
( /system/bin/sh "$MODDIR/bin/companion.sh" run ) >/dev/null 2>&1 &
exit 0
