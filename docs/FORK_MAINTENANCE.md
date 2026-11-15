# Independent AshLooper fork maintenance

Repository: `Mikeyphw/AshLooper` (independent; GitHub `fork=false`).
Based on the AshReXcue project by AshBorn / RipperHybrid.

## Safety measures in RF02

1. The inherited `.github/workflows/sync.yml` originally contained
   `git push ... --all --force` to RipperHybrid's GitLab namespace and release
   publishing. This fork must **never run that workflow**. RF02 replaces it with
   a GitHub Actions *artifact-only*, manual build with `contents: read`.
2. The original fork release recipe omitted `recovery-notify.sh`. RF02's manual
   candidate build explicitly includes it and checks the ZIP inventory.
3. `module.prop` originally pointed to the upstream updater, which could
   replace this fork with an incompatible upstream ZIP. RF02 removes the
   `updateJson` property until this fork publishes its own compatible release.
4. The core recovery engine is unchanged. Only a late-boot notification
   handoff is added, gated by installed/enabled companion.
5. `companion/` packages independently and is **not included in the core ZIP**.
6. The historical `.ashrexcue-notify-backup/` directory is already tracked in
   `Master`; RF02 intentionally does not delete it automatically. To remove it
   from Git after verifying the source baseline, use `git rm -r
   .ashrexcue-notify-backup` in a separate reviewed commit.

## Independent credits

The fork preserves upstream license, Git commit history, and author credit.
The companion enhancement and new CI are separate maintenance work.

## Release rule

Do not auto-merge or publish a release until physical Android 16 acceptance
confirms normal boot, companion notification delivery and module restore UI.
Run GitHub Actions only for build qualification; no local Gradle or Android SDK
bootstrap is needed.
