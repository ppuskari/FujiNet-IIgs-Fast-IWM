# Experiment plan

## E0 - Environment and provenance

- validate Merlin32, macro library, cp2, Git, GitHub CLI, Python
- clone exact FujiNet upstream baseline
- record hashes/tool versions

## E1 - Standard SmartPort baseline

Build SPBENCH and measure unmodified FujiNet on stock and accelerated IIgs.
No firmware modifications.

## E2 - 2 us transmit proof

Add a FujiNet experimental capability that can be negotiated while still in
standard SmartPort mode.  Enter 2 us mode only for a controlled test response.
Verify repeated known-pattern blocks and automatic fallback.

## E3 - Fast-IWM READBLOCK

Run the same SPBENCH workload using SmartPort-style 512-byte block packets at
2 us timing.  Compare throughput, error rate, and CPU sensitivity with E1.

## E4 - 16 KiB burst

Introduce a private sequential streaming primitive and test 32-block bursts.
Measure both 2.8 MHz and accelerated IIgs behavior.

## E5 - Deterministic audio source

FujiNet presents already-buffered 22.05 kHz mono PCM.  Replace only the current
streamer producer with the Fast-IWM producer; keep Tool225 and DOC timing frozen.

## E6 - Network PCM

Move the existing provider-to-client PCM hop to FujiNet Wi-Fi/TCP, with FujiNet
buffering before SmartPort delivery.

## E7 - Resident service / CDA coexistence

Separate producer servicing from the foreground radio UI.  Verify that DOC
refill continues when entering existing CDAs, then investigate Finder / Manager
background operation.
