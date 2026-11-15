# AshReXcue Companion RF03 — independent original-module integration

**Optional standalone root module.** It is installed next to, and **does not replace**, the original [AshReXcue / AshLooper](https://github.com/RipperHybrid/AshLooper). Its module ID is `ashrexcue_companion`, not `AshLooper`.

## What it does

- Reads `/cache/looper/AshReXcueSession-*.log`, the **stock AshReXcue** recovery logs.
- Attributes only module and `service.d` disable events within explicit recovery stages (targeted, lockdown, nuclear).
- Verifies that disabled module markers or script backups still exist before notifying.
- Posts a notification **after AshReXcue confirms a stable boot** using Android's shell notification service.
- Keeps private event history and notification acknowledgements under `/data/adb/ashrexcue-companion`.
- Ignores historical events when first installed by recording initial log offsets.
- Never changes AshReXcue's settings, boot scripts, installed modules, disabled flags, WebUI, updater, or `/cache/looper` logs.

## Install on KernelSU / Magisk / APatch

1. **Keep the original AshReXcue module installed and enabled.** Do **not** install `AshReXcue-Fork-candidate.zip`. That is a core replacement build.
2. Back up the module and configuration before experimenting with boot protection.
3. Install **only** `AshReXcue-Companion-v0.3.0-RF03.zip` from your root manager and reboot normally.
4. Run the status and test notification commands:

```sh
su -c 'sh /data/adb/modules/ashrexcue_companion/bin/companion.sh status'
su -c 'sh /data/adb/modules/ashrexcue_companion/bin/companion.sh test-notification'
```

`test-notification` posts a test alert. It does not disable any modules, alter logs, or reboot.

To manually retry an undelivered **real** recovery report after a stable boot:

```sh
su -c 'sh /data/adb/modules/ashrexcue_companion/bin/companion.sh notify-pending'
```

**Whitelist the ID `ashrexcue_companion` in AshReXcue** to reduce the chance of ordinary lockdown disabling the notifier. Nuclear lockdown overrides whitelists, so the companion cannot guarantee a notification if it is itself disabled.

## Evidence and limitations

- A successful test notification proves only Android notification transport, **not real bootloop handling**.
- The companion depends on retained readable original AshReXcue logs in `/cache/looper`. If the `/cache` partition is absent or logs are not retained, it cannot reconstruct events.
- An event is reported only if the associated original log still exists and the module remains disabled. Restored modules and ambiguous IDs are recorded as unverified, not notified as disabled.
- If the first boot after installation contains a recovery event but the installer could not initialize the log baseline, that event may be skipped rather than risk showing an old incident.
- Long names are truncated to 90 characters in notifications, while logged event identifiers are preserved in history.
- An accepted `cmd notification post` call can still be suppressed by Android's notification settings.
- This is an **offline-tested candidate**, not physical Android 16 acceptance. Do **not** trigger a real bootloop to test it.
- This module does **not** alter existing root-manager module enable/disable states. It only reads them.

## Source layout

- `bin/companion.sh`: observer, state verification, notification and history
- `bin/parse-recovery.awk`: stock AshReXcue log parser
- `tests/test_stock_integration.py`: offline simulated root environment
- `tools/build_zip.py`: reproducible candidate build
- `.github/workflows/companion-ci.yml`: host-only regression and ZIP checks

## Local tests

```sh
python3 -m unittest discover -s tests -v
python3 tools/build_zip.py --out dist/AshReXcue-Companion-v0.3.0-RF03.zip
```

Built from original AshReXcue v10.1 log conventions, with attribution to original AshBorn / RipperHybrid. The companion source is independently maintained.
