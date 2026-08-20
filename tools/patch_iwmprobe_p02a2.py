from pathlib import Path

path = Path('iigs/iwmprobe/src/IWMProbe.s')
text = path.read_text(encoding='utf-8')

if 'IWMPROBE P0.2A2' in text:
    print('IWMPROBE P0.2A2 patch already applied.')
    raise SystemExit(0)

required = [
    "IWMPROBE P0.2A",
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

text = text.replace(
    "Probe only: no disk I/O while FAST is active",
    "Probe only: no disk I/O while alternate mode is active"
)
text = text.replace(
    "IWM bit 3: 0=4us  1=2us",
    "IWM bit 3 toggle/restore test"
)
text = text.replace('FAST request mode=$', 'Toggle request mode=$')
text = text.replace('After FAST: status=$', 'After toggle: status=$')
text = text.replace(
    'FAST BIT SET - host can select 2us cells.',
    'BIT 3 TOGGLED - mode write/readback works.'
)
text = text.replace(
    'FAST BIT DID NOT SET.',
    'BIT 3 TOGGLE FAILED.'
)

path.write_text(text, encoding='utf-8', newline='\n')
print('Applied IWMPROBE P0.2A2 bit-toggle/restore patch.')
