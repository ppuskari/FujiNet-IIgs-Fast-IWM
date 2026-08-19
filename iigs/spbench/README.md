# SPBENCH

Apple IIgs benchmark client for FujiNet SmartPort / Fast-IWM experiments.

## Status

The repository currently contains the test contract and build scaffolding.  The
first hardware client should be implemented only after the local Merlin32 macro
library is available to the build environment so the source can be assembled
and packaged here, not merely guessed at.

## Implementation direction

The first revision will:

1. discover the SmartPort interface/device
2. issue direct sequential 512-byte block reads
3. use the IIgs Misc Tool `_GetTick` 60 Hz counter around long transfer runs
4. verify deterministic block contents
5. report bytes, ticks, payload throughput, errors, and integrity failures

Later revisions add Fast-IWM negotiation and 16 KiB burst tests.
