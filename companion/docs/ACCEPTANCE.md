# Android 16 / KernelSU acceptance — non-destructive

1. Confirm original AshLooper `module.prop` still reports `id=AshLooper`; note its version and hash without modifying it.
2. Install *only* the RF03 companion ZIP; confirm the root manager displays **two distinct modules**.
3. Reboot normally and verify `status` reports a stable boot.
4. Use `test-notification`; confirm a visible notification named **AshReXcue Companion test**.
5. Confirm the original AshReXcue WebUI and recovery configuration have not changed.
6. Check the new state in `/data/adb/ashrexcue-companion` and original log/state paths remain unchanged.
7. Test actual recovery-event detection only after a **naturally occurring** bootloop; don't cause one deliberately.

No Gradle, SDK setup, device writes other than companion installation, or root-manager automation is part of CI.
