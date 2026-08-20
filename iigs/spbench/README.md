# SPBENCH

Apple IIgs benchmark client for FujiNet SmartPort / Fast-IWM experiments.

## P0.1A: GS/OS DRead baseline

P0.1A is the first executable transport benchmark. It deliberately starts one
layer above raw SmartPort: GS/OS Device Manager `DRead`, with exactly one
512-byte block requested per call.

Hardware baseline on the stock 2.8 MHz ROM 3 IIgs:

- 1 MiB: 16,530 bytes/sec, 132 kbit/sec
- 4 MiB: 16,421 bytes/sec, 131 kbit/sec

The long run is therefore approximately 31.2 ms per 512-byte payload block.

## P0.1B: direct SmartPort baseline

P0.1B keeps the P0.1A transfer sizes and reporting contract unchanged but moves
below GS/OS Device Manager for the timed transfers.

Discovery still uses GS/OS to identify the block device that owns prefix 1 and
to obtain its slot, unit, and size. The timed loop then calls the slot SmartPort
firmware dispatcher directly with extended READBLOCK command `$41`, one
512-byte block per transaction.

A small fixed/locked bank-zero thunk establishes the firmware-compatible IIgs
execution environment and calls the dispatcher. The extended command list and
512-byte destination buffer remain in the normal S16 application bank.

P0.1B runs:

1. 256 sequential blocks / 128 KiB warm-up
2. 2048 sequential blocks / 1 MiB timed run
3. 8192 sequential blocks / 4 MiB timed run
4. Misc Tool `_GetTick` timing at 60 Hz
5. no screen output in the timed loop
6. transfer-count verification after every successful READBLOCK

The P0.1A/P0.1B comparison isolates the overhead removed by bypassing GS/OS
`DRead` before any Fast-IWM timing changes are made.

## Deployment

The deployment image is a 32 MB ProDOS volume named `SPBENCH`. Mount it on
FujiNet and launch `SPBENCH` from that volume so prefix-to-device discovery
selects the FujiNet block device automatically.

Test the stock 2.8 MHz ROM 3 IIgs first. The accelerated IIgs is the second
comparison point after the stock result is captured.

## Build P0.1B

From Windows PowerShell 5.1 on branch `exp/spbench-p0.1b`:

```powershell
cd C:\AppleIIgsDev_02\FujiNet-IIgs-Fast-IWM

powershell -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\Build-SPBench-P01B.ps1
```

The builder uses:

- `C:\AppleIIgsDev_02\tools\Merlin32_v1.2_b2\Windows\Merlin32.exe`
- `C:\AppleIIgsDev_02\tools\Merlin32_v1.2_b2\Library`
- `C:\AppleIIgsDev_02\tools\cp2\cp2.exe`

It assembles the S16 application, creates a fresh 32 MB ProDOS image, adds the
NAPS-typed binary, catalogs the image, runs `cp2 test`, writes hashes/build
metadata, and creates `build\spbench-p0.1b\SPBENCH-P0.1B.zip`.

CI separately verifies Merlin32 assembly, parses the build script with actual
Windows PowerShell 5.1, builds CiderPress II, creates the deployment image, and
runs `cp2 test` before producing the deployable artifact.

## After P0.1B

After the standard-timing baselines are locked, P1 adds negotiated Fast-IWM
2 us timing and repeats the same tests unchanged. P2 then attacks per-block
overhead with multi-block bursts, especially 32 blocks = 16 KiB for direct
alignment with the existing DOC producer quantum.
