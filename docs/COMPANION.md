# AshReXcue Companion RF02

This is an **optional separately installable root module**, source-controlled in
`companion/`. AshLooper's core module does not install the companion by default.

## Why a companion?

The `Mikeyphw/AshLooper` fork already writes `disabled-report.pending` when
it disables modules or service scripts. The companion consumes this **explicit
journal** after AshLooper marks the current boot as stable, rechecks that
items are actually disabled, posts one Android notification, saves an incident
history, and archives the source journal to `disabled-report.last`.

It never enables/disables modules, restores scripts, edits protection settings,
or reboots the device. Journal archival is the only write to AshLooper state.

## Notification ownership and fallback

- When the companion module `ashrexcue_companion` is installed and enabled,
  AshLooper's `service.sh` **defers** its built-in `recovery-notify.sh` delivery.
- When the companion is not installed, is disabled, or lacks its service script,
  the **existing built-in notifier remains active**.
- During nuclear/full lockdown, the companion itself may be disabled. The
  notification cannot be guaranteed. Whitelist `ashrexcue_companion` in
  AshLooper to protect it in ordinary lockdown; nuclear lockdown bypasses it.
- If the companion fails to notify, it **retains the pending journal** for
  manual retry or the next stable boot. It does not interfere with boot recovery.
- Android may suppress notifications even when `cmd notification post` exits 0.
  Physical Android 16 validation is still required.

## Install (separately from AshLooper)

After building the ZIP with `python3 companion/tools/build_zip.py --out
AshReXcue-Companion-v0.2.0.zip`, install it in KernelSU, Magisk or APatch.
Use the root manager's Action button or run:

```sh
su -c 'sh /data/adb/modules/ashrexcue_companion/bin/companion.sh status'
su -c 'sh /data/adb/modules/ashrexcue_companion/bin/companion.sh test-notification'
su -c 'sh /data/adb/modules/ashrexcue_companion/bin/companion.sh notify-pending'
```

`notify-pending` requires a stable completed boot. A test notification does not
change recovery state. No service requires Python, jq or Gradle on Android.

## Storage

- Input: `/data/adb/ashlooper/disabled-report.pending` (written by AshLooper)
- Archived input: `/data/adb/ashlooper/disabled-report.last`
- History: `/data/adb/ashrexcue-companion/history/*.tsv`
- Idempotency ACKs: `/data/adb/ashrexcue-companion/delivered/`

Module ID: `ashrexcue_companion`; all history/ACK directories use root-only
permissions. Uninstall intentionally preserves history for manual inspection.

## Validation

```sh
sh -n companion/*.sh companion/bin/*.sh service.sh
python3 -m unittest discover -s tests -p 'test_companion_rf02.py' -v
python3 companion/tools/build_zip.py --out dist/companion.zip
```

Offline tests are not a substitute for hardware acceptance. Do not test a
bootloop by deliberately bricking your daily-use phone. Check the test
notification and read-only status first.

## Provenance

This independent companion functionality is an enhancement maintained in
`Mikeyphw/AshLooper`; original AshReXcue by AshBorn / RipperHybrid.
This source repository retains upstream attribution and license.
