from pathlib import Path

path = Path('iigs/iwmprobe/src/IWMProbe.s')
text = path.read_text(encoding='utf-8')

# First normalize to the P0.2A2 toggle experiment if the checkout
# still contains the P0.2A base source.
if 'IWMPROBE P0.2A2' not in text and 'IWMPROBE P0.2A3' not in text:
    required = [
        'IWMPROBE P0.2A',
        "         lda   InitialMode\n         ora   #IWM_FAST_BIT\n         and   #IWM_MODE_MASK\n         sta   DesiredMode",
        "         lda   CurrentMode\n         and   #IWM_FAST_BIT\n         beq   FastBitRejected",
    ]
    for needle in required:
        if needle not in text:
            raise SystemExit('Expected P0.2A source pattern not found: ' + repr(needle))

    text = text.replace('IWMPROBE P0.2A', 'IWMPROBE P0.2A2')
    text = text.replace(
        "         lda   InitialMode\n         ora   #IWM_FAST_BIT\n         and   #IWM_MODE_MASK\n         sta   DesiredMode",
        "         lda   InitialMode\n         eor   #IWM_FAST_BIT\n         and   #IWM_MODE_MASK\n         sta   DesiredMode"
    )
    text = text.replace(
        "         lda   CurrentMode\n         and   #IWM_FAST_BIT\n         beq   FastBitRejected\n\n         PushLong #FastOKMsg\n         _WriteCString\n         bra   BeginRestore\n\nFastBitRejected\n         PushLong #FastFailMsg\n         _WriteCString",
        "         lda   CurrentMode\n         cmp   DesiredMode\n         bne   FastBitRejected\n\n         PushLong #FastOKMsg\n         _WriteCString\n         bra   BeginRestore\n\nFastBitRejected\n         PushLong #FastFailMsg\n         _WriteCString"
    )
    text = text.replace('Probe only: no disk I/O while FAST is active',
                        'Probe only: no disk I/O while alternate mode is active')
    text = text.replace('IWM bit 3: 0=4us  1=2us',
                        'IWM bit 3 toggle/restore test')
    text = text.replace('FAST request mode=$', 'Toggle request mode=$')
    text = text.replace('After FAST: status=$', 'After toggle: status=$')
    text = text.replace('FAST BIT SET - host can select 2us cells.',
                        'BIT 3 TOGGLED - mode write/readback works.')
    text = text.replace('FAST BIT DID NOT SET.',
                        'BIT 3 TOGGLE FAILED.')

if 'IWMPROBE P0.2A3' in text:
    print('IWMPROBE P0.2A3 patch already applied.')
    raise SystemExit(0)

if 'IWMPROBE P0.2A2' not in text:
    raise SystemExit('Source is not in expected P0.2A2 state.')

old_write = """         lda   >IWM_MOTOR_OFF
         lda   >IWM_Q6_ON
         lda   DesiredMode
         sta   >IWM_Q7_ON
"""
new_write = """         lda   >IWM_MOTOR_OFF
         lda   >IWM_Q6_ON

* Preselect Q7=1 with a separate access before the
* data write.  The prior probe attempted to make the
* same STA cycle both select Q7 and write the Mode
* register; real hardware left the mode unchanged.
         lda   >IWM_Q7_ON
         lda   DesiredMode
         sta   >IWM_Q7_ON
"""

if old_write not in text:
    raise SystemExit('Expected WriteIWMMode pattern not found.')

text = text.replace('IWMPROBE P0.2A2', 'IWMPROBE P0.2A3')
text = text.replace(old_write, new_write)
text = text.replace('BIT 3 TOGGLED - mode write/readback works.',
                    'BIT 3 TOGGLED - preselected Q7 write works.')
text = text.replace('IWM bit 3 toggle/restore test',
                    'IWM bit 3 toggle/restore, preselected Q7')

path.write_text(text, encoding='utf-8', newline='\n')
print('Applied IWMPROBE P0.2A3 preselected-Q7 mode-write patch.')
