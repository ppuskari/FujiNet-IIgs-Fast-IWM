# IWMPROBE P0.2A4

P0.2A3 still read back `$0C` after requesting `$04`. P0.2A4 removes the two-GetTick observation gap: the mode write and status readback occur inside one `SEI` critical section, with no toolbox or timer activity in between. This distinguishes a rejected IWM mode write from a mode value that is immediately normalized by System 6/firmware after interrupts resume.

No disk I/O occurs while the alternate mode is selected. The original mode is restored and verified before exit.
