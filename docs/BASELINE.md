# Baseline

Recorded: 2026-08-19

## FujiNet upstream

Repository: `FujiNetWIFI/fujinet-firmware`

Pinned commit:

`b0a9483463c93ab61279d265467159c0d27c9f82`

Relevant current source areas:

- `lib/bus/iwm/iwm.cpp`
- `lib/bus/iwm/iwm.h`
- `lib/bus/iwm/iwm_ll.cpp`
- `lib/bus/iwm/iwm_ll.h`
- `lib/device/iwm/`

The pinned implementation is the control case.  Do not silently advance the
upstream commit during a benchmark series.

## Existing IIgs streamer reference

The Uthernet/Marinetti streamer golden baseline remains in its own repository.
This project may copy measurements and interface contracts, but it must not
rewrite or retag that baseline.

Initial reusable consumer-side assumptions:

- 22.05 kHz mono target
- 512 KiB system-memory ring
- exact 16 KiB producer quantum
- 48 KiB protection gate
- existing Tool225 / DOC oscillator timing kept frozen during transport tests
