# SPBENCH

Apple IIgs benchmark client for FujiNet SmartPort / Fast-IWM experiments.

## P0.1A: GS/OS DRead baseline

P0.1A is the first executable transport benchmark.  It deliberately starts one
layer above raw SmartPort: GS/OS Device Manager `DRead`, with exactly one
512-byte block requested per call.

This gives us a low-risk baseline that can be compared with both the existing
BenchmarkeD results and the later direct-SmartPort benchmark.

P0.1A:

1. obtains GS/OS prefix 1
2. identifies the block device that owns that volume
3. verifies that it is a readable 512-byte ProDOS block device
4. warms the path with 256 sequential block reads (128 KiB)
5. times 2048 sequential block reads (1 MiB)
6. times 8192 sequential block reads (4 MiB)
7. uses the Misc Tool `_GetTick` 60 Hz counter
8. reports completed blocks, bytes, elapsed ticks, bytes/sec, and kbit/sec
9. performs no screen output inside the timed read loop

The deployment image is itself a 32 MB ProDOS volume named `SPBENCH`.  Mount it
on FujiNet and launch `SPBENCH` from that volume so the prefix-to-device lookup
selects the FujiNet block device automatically.

## Build

From Windows PowerShell 5.1:

```powershell
cd C:\AppleIIgsDev_02\FujiNet-IIgs-Fast-IWM

powershell -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\Build-SPBench-P01A.ps1
```

The builder uses:

- `C:\AppleIIgsDev_02\tools\Merlin32_v1.2_b2\Windows\Merlin32.exe`
- `C:\AppleIIgsDev_02\tools\Merlin32_v1.2_b2\Library`
- `C:\AppleIIgsDev_02\tools\cp2\cp2.exe`

It assembles the S16 application, creates a fresh 32 MB ProDOS image, adds the
NAPS-typed binary, catalogs the image, runs `cp2 test`, writes hashes/build
metadata, and creates `build\spbench-p0.1a\SPBENCH-P0.1A.zip`.

## Next: P0.1B raw SmartPort

P0.1B will keep the same transfer sizes and reporting contract but move below
GS/OS Device Manager to the Apple IIgs SmartPort firmware dispatch path.  That
A/B comparison separates GS/OS/driver overhead from the actual SmartPort bus
and firmware cost before any 2 us Fast-IWM changes are made.

After the standard-timing baselines are locked, P1 adds Fast-IWM negotiation
and repeats the same tests unchanged.  P2 adds reduced-overhead multi-block
bursts, especially 32 blocks = 16 KiB for direct alignment with the existing
DOC producer quantum.
