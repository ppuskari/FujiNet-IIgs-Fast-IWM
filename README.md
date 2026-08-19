# FujiNet-IIgs-Fast-IWM

Experimental Apple IIgs / FujiNet project for evaluating and implementing a
IIgs-specific high-throughput IWM transport, then using it as the producer path
for real-time Ensoniq DOC audio streaming.

## Core idea

Keep standard Apple SmartPort compatibility at its normal timing.  On a IIgs,
explicitly negotiate a private FujiNet extension that moves the IWM transport
from the normal 4 us bit-cell regime to a 2 us bit-cell regime, with an immediate
fallback to standard timing on reset/error/exit.

The first target is **not** Internet radio.  The first target is measurement.

1. Establish the unmodified FujiNet SmartPort baseline.
2. Prove a 2 us Fast-IWM transfer between a IIgs and FujiNet.
3. Measure ordinary 512-byte READBLOCK performance.
4. Measure a low-overhead sequential streaming primitive.
5. Only then connect the transport to the existing 512 KiB / 16 KiB DOC
   streaming pipeline.

## Safety rule

The existing Uthernet II streamer golden baseline is an external reference and
must not be modified by this repository.  This project changes one transport at
a time.

## Pinned FujiNet baseline

Initial upstream firmware baseline:

- repository: `FujiNetWIFI/fujinet-firmware`
- commit: `b0a9483463c93ab61279d265467159c0d27c9f82`
- Apple IWM bus code: `lib/bus/iwm/`
- current low-level SmartPort implementation uses a 4 us cell model

Use `scripts/Setup-FujiNet-Worktree.ps1` to create the local firmware worktree
at that exact commit.

## Repository layout

- `docs/` - architecture, experiment protocol, measurements, handoffs
- `iigs/spbench/` - IIgs SmartPort/Fast-IWM benchmark client
- `firmware/` - FujiNet-side patch notes and eventual source patches
- `tools/` - host-side analysis/model tools
- `scripts/` - Windows PowerShell setup/build/publish helpers
- `results/` - checked-in benchmark result summaries (raw local logs stay ignored)
- `work/` - ignored local upstream checkouts and build trees

## First hardware matrix

Run every transport measurement on at least:

- stock ROM 3 IIgs at 2.8 MHz
- accelerated IIgs at approximately 14 MHz

Test unmodified 4 us SmartPort first, then Fast-IWM.  Do not change the DOC
streamer during the transport-only phase.

## GitHub bootstrap

After extracting this starter repository on the Windows development machine:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\Bootstrap-GitHub.ps1
```

The script initializes Git if required, commits the starter tree, creates
`ppuskari/FujiNet-IIgs-Fast-IWM`, sets `origin`, and pushes `main`.
