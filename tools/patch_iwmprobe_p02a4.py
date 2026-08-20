from pathlib import Path

path = Path('iigs/iwmprobe/src/IWMProbe.s')
text = path.read_text(encoding='utf-8')

if 'IWMPROBE P0.2A4' in text:
    print('IWMPROBE P0.2A4 patch already applied.')
    raise SystemExit(0)

if 'IWMPROBE P0.2A3' not in text:
    raise SystemExit('P0.2A4 expects the P0.2A3 patch first.')

old_write = """WriteIWMMode
         php
         sei
         sep   #$20

         lda   >IWM_MOTOR_OFF
         lda   >IWM_Q6_ON

* Preselect Q7=1 with a separate access before the
* data write.  The prior probe attempted to make the
* same STA cycle both select Q7 and write the Mode
* register; real hardware left the mode unchanged.
         lda   >IWM_Q7_ON
         lda   DesiredMode
         sta   >IWM_Q7_ON

* Leave Q7 deasserted after the write.
         lda   >IWM_Q7_OFF

         rep   #$20
         plp
         rts
"""

new_write = """WriteIWMMode
         php
         sei
         sep   #$20

* Follow the proven IWM initialization pattern used by
* NetBSD's mac68k IWM driver: motor off, Q6 high,
* status via Q7 low, confirm drive-enable bit 5 is 0,
* then write the desired mode directly through Q7 high.
*
* Capture status immediately after the write while
* interrupts are still disabled.  This distinguishes a
* rejected IWM write from System 6 restoring the mode
* after we leave this critical section.

         lda   >IWM_MOTOR_OFF
         lda   >IWM_Q6_ON
         lda   >IWM_Q7_OFF
         sta   PreWriteStatus

         and   #$20
         bne   ModeWriteDriveBusy

         lda   DesiredMode
         sta   >IWM_Q7_ON

* Q7 low selects Status again and ends the write state.
         lda   >IWM_Q7_OFF
         sta   ImmediateStatus
         and   #$1F
         sta   ImmediateMode
         bra   ModeWriteDone

ModeWriteDriveBusy
* Record the unchanged status/mode so the screen makes
* the reason for refusal visible rather than hanging.
         lda   PreWriteStatus
         sta   ImmediateStatus
         and   #$1F
         sta   ImmediateMode

ModeWriteDone
         rep   #$20
         plp
         rts
"""

if old_write not in text:
    raise SystemExit('Expected P0.2A3 WriteIWMMode block not found.')

old_after_write = """         jsr   WriteIWMMode
         lda   #SettleTicks
         jsr   WaitTicks16
         jsr   ReadIWMMode

         PushLong #FastResultMsg
"""

new_after_write = """         jsr   WriteIWMMode

         PushLong #ImmediateMsg
         _WriteCString
         lda   PreWriteStatus
         jsr   WriteHexWord
         PushLong #ImmediateStatusMsg
         _WriteCString
         lda   ImmediateStatus
         jsr   WriteHexWord
         PushLong #ModeMsg
         _WriteCString
         lda   ImmediateMode
         jsr   WriteHexWord
         jsr   WriteCRLF

         lda   #SettleTicks
         jsr   WaitTicks16
         jsr   ReadIWMMode

         PushLong #FastResultMsg
"""

if old_after_write not in text:
    raise SystemExit('Expected post-write P0.2A3 block not found.')

old_state = """CurrentStatus  ds    2
CurrentMode    ds    2
DesiredMode    ds    2
"""
new_state = """CurrentStatus  ds    2
CurrentMode    ds    2
DesiredMode    ds    2
PreWriteStatus ds    2
ImmediateStatus ds   2
ImmediateMode  ds    2
"""
if old_state not in text:
    raise SystemExit('Expected state block not found.')

old_msgs = """FastResultMsg
         asc   'After toggle: status=$'00
"""
new_msgs = """ImmediateMsg
         asc   'Immediate: pre=$'00
ImmediateStatusMsg
         asc   ' post=$'00
FastResultMsg
         asc   'After 2 ticks: status=$'00
"""
if old_msgs not in text:
    raise SystemExit('Expected result message block not found.')

text = text.replace('IWMPROBE P0.2A3', 'IWMPROBE P0.2A4')
text = text.replace(
    'IWM bit 3 toggle/restore, preselected Q7',
    'IWM bit 3 toggle/restore, immediate readback'
)
text = text.replace(old_write, new_write)
text = text.replace(old_after_write, new_after_write)
text = text.replace(old_state, new_state)
text = text.replace(old_msgs, new_msgs)
text = text.replace(
    'BIT 3 TOGGLED - preselected Q7 write works.',
    'BIT 3 TOGGLED - immediate IWM write works.'
)

path.write_text(text, encoding='utf-8', newline='\n')
print('Applied IWMPROBE P0.2A4 NetBSD-style immediate-readback patch.')
