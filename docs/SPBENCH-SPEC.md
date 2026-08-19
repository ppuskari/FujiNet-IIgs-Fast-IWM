# SPBENCH experiment specification

## Purpose

Measure the actual FujiNet <-> Apple IIgs SmartPort transport before altering
firmware, then repeat the same tests after Fast-IWM support is introduced.

## P0: current firmware baseline

Use unmodified FujiNet firmware pinned by `docs/BASELINE.md`.

Measure sequential 512-byte READBLOCK behavior with enough iterations to make
60 Hz `_GetTick` timing error negligible.

Record:

- IIgs model / ROM revision
- CPU / accelerator state
- FujiNet hardware revision
- FujiNet firmware commit
- SmartPort slot/device number
- number of blocks
- bytes transferred
- elapsed ticks
- bytes/sec and bits/sec payload
- successful blocks
- errors/retries
- integrity failures
- min/mean/max transfer time when finer instrumentation is added

Recommended initial runs:

- 256 blocks (128 KiB warm-up)
- 2048 blocks (1 MiB)
- 8192 blocks (4 MiB)

Avoid filesystem traversal during the timed region.  The eventual low-level
benchmark should invoke the SmartPort device path directly.

## P1: Fast-IWM proof

Change only the IWM timing/negotiation path.

Requirements:

- boot/reset always begins in standard mode
- host queries Fast-IWM capability in standard mode
- host explicitly enters Fast-IWM mode
- 2 us transfer is used only after both sides agree
- bus reset, timeout, checksum failure, or explicit exit returns to standard
  mode
- old Apple II hosts remain unaffected

Repeat P0 unchanged.

## P2: streaming primitive

After ordinary READBLOCK works reliably at Fast-IWM speed, measure reduced
command/handshake overhead.

Candidate burst sizes:

- 1 block = 512 bytes
- 2 blocks = 1 KiB
- 4 blocks = 2 KiB
- 8 blocks = 4 KiB
- 16 blocks = 8 KiB
- 32 blocks = 16 KiB
- 64 blocks = 32 KiB

The 32-block / 16 KiB case is particularly important because it matches the
existing DOC producer quantum.

## Pass criteria for moving to audio

For 22.05 kHz mono PCM, sustained payload must exceed 22,050 bytes/sec by a
comfortable margin under stock 2.8 MHz conditions.  The project should prefer
measured margin, not theoretical signaling rate.

22.05 kHz stereo (44,100 bytes/sec) is an accelerated-machine stretch target
until measurements prove otherwise.
