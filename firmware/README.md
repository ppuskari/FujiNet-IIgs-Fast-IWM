# FujiNet firmware experiments

Do not vendor the entire upstream firmware repository here.

Run:

```powershell
.\scripts\Setup-FujiNet-Worktree.ps1
```

That creates `work\fujinet-firmware`, checks out the exact pinned upstream
commit, and creates the local experiment branch:

`petar/iigs-fast-iwm-p0`

Keep firmware changes atomic.  The expected first touched files are in
`lib/bus/iwm/`; adding a dedicated streaming virtual device comes later.

Patch snapshots that are worth preserving independently can be stored under
`firmware/patches/`.
