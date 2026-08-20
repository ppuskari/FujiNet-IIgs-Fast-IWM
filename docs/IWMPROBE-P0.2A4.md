# IWMPROBE P0.2A4

Hardware P0.2A3 result on the stock ROM 3 / 2.8 MHz Apple IIgs:

- initial status `$CC`, mode `$0C`
- requested toggle mode `$04`
- delayed readback remained `$0C`
- restore remained `$0C`

P0.2A4 follows the established IWM initialization sequence used by the NetBSD mac68k IWM driver more closely. It checks the motor/status state, writes the requested mode through Q7 high, and captures status/mode immediately inside the interrupt-disabled critical section before doing the normal delayed readback.

Diagnostic goal:

- immediate `$04`, delayed `$0C`: the write succeeded and later system activity restored the mode.
- immediate `$0C`: the write itself did not take, so we continue investigating the low-level IWM write qualification.

No disk transfer occurs while the alternate mode is requested.
