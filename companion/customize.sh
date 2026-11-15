#!/system/bin/sh
# Executed by KernelSU/Magisk/APatch during companion installation.
# Do not change original AshReXcue, boot scripts, or module settings.
ui_print '- AshReXcue Companion RF03: independent read-only integration'
ui_print '- Original AshLooper module remains untouched'
if [ ! -d /data/adb/modules/AshLooper ] && [ ! -d /data/adb/modules_update/AshLooper ]; then
  ui_print '! Original AshReXcue not found; notifications will remain inactive'
fi
# Initialize source-log offsets BEFORE any reboot to suppress old incidents.
/system/bin/sh "$MODPATH/bin/companion.sh" seed || ui_print '! Could not initialize log baseline; old events will be ignored at first boot'
set_perm_recursive "$MODPATH" 0 0 0755 0644
set_perm "$MODPATH/service.sh" 0 0 0755
set_perm "$MODPATH/action.sh" 0 0 0755
set_perm "$MODPATH/bin/companion.sh" 0 0 0755
