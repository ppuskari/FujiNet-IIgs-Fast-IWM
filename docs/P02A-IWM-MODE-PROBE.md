# P0.2A — Apple IIgs IWM Mode Probe

Purpose: prove on the stock ROM 3 / 2.8 MHz IIgs that application code can safely read, set, verify, and restore IWM mode-register bit 3 before the paired FujiNet 2 us transport experiment.

The Apple IIgs Hardware Reference documents IWM mode bit 3 as the bit-cell selector: 0 = 4 us SmartPort/5.25-inch timing, 1 = 2 us 3.5-inch timing. The mode register is write-only; its low mode bits are reflected by the IWM status register. A mode write is accepted only after the one-second motor-off timer has expired.

P0.2A performs no disk transfer while fast mode is active:

1. Read and print initial IWM status/mode.
2. Access motor-off and wait 70 GetTick ticks (~1.17 s).
3. Write `initial_mode | $08`.
4. Read status and verify bit 3.
5. Restore the exact initial low five mode bits.
6. Read status and verify restore. If the first restore does not stick, wait another 70 ticks and retry once.
7. Return to GS/OS only after restore verification.

This experiment deliberately does not modify FujiNet firmware. It proves only host-side IWM mode control. P0.2B will pair host 2 us mode with FujiNet TX/RX timing changes.
