# SPBENCH P0.1B3

Hardware isolation step after P0.1B2.

P0.1B2 confirmed on the stock ROM 3 Apple IIgs:

- FujiNet block device in slot 5, unit 1
- C5FF = $0A
- direct SmartPort dispatcher = $C50D
- bank-zero firmware thunk executes and returns cleanly
- extended READBLOCK $41 still returns SmartPort error $01 before block 0

P0.1B3 removes the extended-call form entirely.  It uses standard SmartPort
READBLOCK $01 with the documented 3-parameter list: unit byte, 16-bit buffer
pointer, and 24-bit block number.  The parameter list and throwaway 512-byte
staging buffer live in the same fixed/locked bank-zero allocation as the
firmware thunk.

The workload remains unchanged from P0.1A/P0.1B:

- 256 blocks / 128 KiB warm-up
- 2048 blocks / 1 MiB timed test
- 8192 blocks / 4 MiB timed test
- Misc Tool GetTick at 60 Hz

The purpose of B3 is to establish the simplest possible direct standard
SmartPort baseline before any Fast-IWM timing changes.
