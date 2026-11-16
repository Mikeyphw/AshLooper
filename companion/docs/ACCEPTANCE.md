# Android 16 / KernelSU acceptance — non-destructive

1. Confirm original AshLooper `module.prop` still reports `id=AshLooper`; note its version and hash without modifying it.
2. Install *only* the RF03 companion ZIP; confirm the root manager displays **two distinct modules**.
3. Reboot normally and verify `status` reports a stable boot.
4. Use `test-notification`; confirm a visible notification named **AshReXcue Companion test**.
5. Confirm the original AshReXcue WebUI and recovery configuration have not changed.
6. Check the new state in `/data/adb/ashrexcue-companion` and original log/state paths remain unchanged.
7. Test actual recovery-event detection only after a **naturally occurring** bootloop; don't cause one deliberately.

No Gradle, SDK setup, device writes other than companion installation, or root-manager automation is part of CI.

## RF04 synthetic recovery acceptance (safe device exercise)

Run **after a normal stable boot**, with the standalone companion v0.4.0 installed:

```sh
su -c 'sh /data/adb/modules/ashrexcue_companion/bin/companion.sh synthetic-test'
```

The command runs the real scanner, original-log parser, disabled-state verifier,
notification sender, incident history/ACK, and duplicate-prevention logic **against
private fake logs and fake module markers under `/data/local/tmp`**. It creates
no real disabled flags and never writes to `/data/adb/modules/AshLooper`,
`/data/adb/ashlooper`, `/data/adb/service.d` or `/cache/looper`.

The notification is visibly labeled **[SYNTHETIC TEST]**, and says no real
modules or scripts were disabled. The temporary sandbox is removed on exit,
including failure. A success marker `RF04_SYNTHETIC_PASS` proves the simulated
recovery flow and one accepted notification. It does *not* prove that a future
real bootloop will produce the expected stock logs or that Android displayed
the notification; check the actual notification shade as well.

Refusal before stable boot is expected. Do not trigger a real bootloop.
