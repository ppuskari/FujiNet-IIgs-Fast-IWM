from pathlib import Path
import subprocess
import sys

repo = Path('.')
subprocess.run([sys.executable, str(repo / 'tools' / 'patch_iwmprobe_p02a3.py')], check=True)

path = repo / 'iigs' / 'iwmprobe' / 'src' / 'IWMProbe.s'
text = path.read_text(encoding='utf-8')

if 'IWMPROBE P0.2A4' in text:
    print('IWMPROBE P0.2A4 patch already applied.')
    raise SystemExit(0)
if 'IWMPROBE P0.2A3' not in text:
    raise SystemExit('Source is not in expected P0.2A3 state.')

old_call = """         jsr   WriteIWMMode
         lda   #SettleTicks
         jsr   WaitTicks16
         jsr   ReadIWMMode
"""
if text.count(old_call) < 2:
    raise SystemExit('Expected write/wait/read sequences not found.')
text = text.replace(old_call, "         jsr   WriteAndReadIWMMode\n")

old_retry = """         jsr   WriteIWMMode
         lda   #SettleTicks
         jsr   WaitTicks16
         jsr   ReadIWMMode
"""
text = text.replace(old_retry, "         jsr   WriteAndReadIWMMode\n")

insert_before = """*-------------------------------------------------
* 60 Hz timing helper
*-------------------------------------------------
"""
routine = """*-------------------------------------------------
* Atomic mode write + immediate status readback.
*
* Keep interrupts disabled from the Q6/Q7 mode write
* through the status-register read so System 6 cannot
* normalize the shared IWM mode before we observe it.
*-------------------------------------------------

WriteAndReadIWMMode
         php
         sei
         sep   #$20

         lda   >IWM_MOTOR_OFF
         lda   >IWM_Q6_ON
         lda   >IWM_Q7_ON
         lda   DesiredMode
         sta   >IWM_Q7_ON

* Select status register (Q6=1,Q7=0) and capture it
* immediately, still inside the same SEI window.
         lda   >IWM_Q7_OFF
         sta   CurrentStatus
         and   #$1F
         sta   CurrentMode

         rep   #$20
         plp
         rts

"""
if insert_before not in text:
    raise SystemExit('Timing-helper insertion point not found.')
text = text.replace(insert_before, routine + insert_before)

text = text.replace('IWMPROBE P0.2A3', 'IWMPROBE P0.2A4')
text = text.replace('IWM bit 3 toggle/restore, preselected Q7',
                    'IWM bit 3 atomic write/readback test')
text = text.replace('BIT 3 TOGGLED - preselected Q7 write works.',
                    'BIT 3 TOGGLED - atomic write/readback works.')

path.write_text(text, encoding='utf-8', newline='\n')
print('Applied IWMPROBE P0.2A4 atomic write/readback patch.')
