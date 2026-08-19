# IWMPROBE P0.2A5

Final register-only probe before paired Fast-IWM transport work.

P0.2A5 tests whether selecting the Apple IIgs 3.5-inch disk path through Disk Interface register `$C031` bit 6 changes IWM Mode-register write behavior.

Sequence:

1. Capture the original `$C031` value and IWM status/mode.
2. Disable the spindle motor and wait for the mode-write timer.
3. Set `$C031` bit 6 using read-modify-write, preserving bit 7.
4. Verify the selected `$C031` value by readback.
5. Attempt the same IWM bit-3 toggle used by P0.2A4.
6. Capture immediate IWM status/mode while interrupts remain disabled.
7. Capture status/mode again after two ticks.
8. Restore the original IWM mode.
9. Restore the exact original `$C031` value and verify it by readback.
10. Only then return to GS/OS.

No disk I/O is issued while the 3.5-inch/35DISK selection is active.
