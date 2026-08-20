from pathlib import Path
import argparse
import subprocess
import sys


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f'Expected {label} pattern not found.')
    return text.replace(old, new, 1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Apply P0.2C6 then switch the IIgs IWM itself to 2-us mode for receive.'
    )
    parser.add_argument('--project-root', default='.')
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    base = root / 'tools' / 'patch_spbench_fastiwm_p02c6.py'
    src = root / 'iigs' / 'spbench' / 'src' / 'SPBench.s'

    if not base.is_file():
        raise SystemExit(f'Missing P0.2C6 host transform: {base}')
    if not src.is_file():
        raise SystemExit(f'Missing SPBENCH source: {src}')

    subprocess.run(
        [sys.executable, str(base), '--project-root', str(root)],
        check=True,
    )

    text = src.read_text(encoding='utf-8')
    if 'FASTPROBE P0.2C7' in text:
        print('FASTPROBE P0.2C7 host overlay already applied.')
        return
    if 'FASTPROBE P0.2C6' not in text:
        raise SystemExit('P0.2C6 host transform did not apply.')

    text = replace_once(
        text,
        "IWM_DRIVE_ON    equ   $00C0E9\nIWM_Q6_OFF      equ   $00C0EC\nIWM_Q7_OFF      equ   $00C0EE\n",
        "IWM_DRIVE_ON    equ   $00C0E9\nIWM_Q6_OFF      equ   $00C0EC\nIWM_Q6_ON       equ   $00C0ED\nIWM_Q7_OFF      equ   $00C0EE\nIWM_Q7_ON       equ   $00C0EF\nIWMFastMode     equ   $0F\nIWMModeMask     equ   $1F\n",
        'P0.2C6 IWM register constants',
    )

    text = replace_once(
        text,
        "         asc   'FASTPROBE P0.2C6 - immediate delayed-packet read'0d\n",
        "         asc   'FASTPROBE P0.2C7 - IIgs IWM 2us receive mode'0d\n",
        'P0.2C6 banner',
    )

    old_entry = '''* P0.2C6: C4 delayed-autosend needs no GPIO/phase trigger.
* Preserve the phase state left by the proven ROM SmartPort arm call.
* Select only the IWM Read-Data register: DRIVE ENABLED, Q7=0, Q6=0.
         lda   >IWM_Q7_OFF
         lda   >IWM_Q6_OFF
         lda   >IWM_Q6_OFF

         ldx   #MarkerScan
'''
    new_entry = '''* P0.2C7: the FujiNet side already transmits with 2-us bit cells.
* The IIgs IWM must also have mode bit C set or its receive shifter remains
* in the normal 4-us SmartPort/5.25-inch cell timing.  Save the live mode,
* program the documented 3.5-inch fast mode $0F, then enter Read Data.
         lda   >IWM_DRIVE_OFF
         lda   >IWM_Q6_ON
         lda   >IWM_Q7_OFF
         and   #IWMModeMask
         sta   FastModeSaved

         lda   #IWMFastMode
         jsr   SetIWMModeC

* Technical Note #30: Read Data is DRIVE ENABLED, Q7=0, Q6=0.
         lda   >IWM_DRIVE_ON
         lda   >IWM_Q7_OFF
         lda   >IWM_Q6_OFF
         lda   >IWM_Q6_OFF

         ldx   #MarkerScan
'''
    text = replace_once(text, old_entry, new_entry, 'P0.2C6 receive register selection')

    old_reset_tail = '''* Leave the disk interface and machine speed exactly as we found them.
         lda   >IWM_DRIVE_OFF
         lda   FastSpeedSaved
         sta   >IIGS_SPEED
         rts
'''
    new_reset_tail = '''* Leave the disk interface, IWM mode, and machine speed exactly as found.
         lda   >IWM_DRIVE_OFF
         lda   FastModeSaved
         jsr   SetIWMModeC
         lda   FastSpeedSaved
         sta   >IIGS_SPEED
         rts

* Program the IWM write-only Mode register and verify through Status.
* Apple IIGS 3.5-inch drive documentation requires DRIVE OFF, Q6=1,
* then repeated Q7 write/status compare until mode bits 0..4 match.
* M=8 on entry/return. Desired mode is passed in A.
SetIWMModeC
         sta   FastModeDesired
         lda   >IWM_DRIVE_OFF
         lda   >IWM_Q6_ON
SetIWMModeLoopC
         lda   FastModeDesired
         sta   >IWM_Q7_ON
         lda   FastModeDesired
         eor   >IWM_Q7_OFF
         and   #IWMModeMask
         bne   SetIWMModeLoopC
         rts
'''
    text = replace_once(text, old_reset_tail, new_reset_tail, 'P0.2C6 reset tail')

    text = replace_once(
        text,
        '''FastPatternFail ds   2
FastSpeedSaved ds    2
FastBufferC     ds    512
''',
        '''FastPatternFail ds   2
FastSpeedSaved ds    2
FastModeSaved  ds    2
FastModeDesired ds   2
FastBufferC     ds    512
''',
        'P0.2C6 state block',
    )

    text = replace_once(
        text,
        "         asc   'FAST FAILED: immediate drive-enabled read timed out.'0d00\n",
        "         asc   'FAST FAILED: 2us-mode IWM read timed out.'0d00\n",
        'P0.2C6 timeout message',
    )

    required = (
        'FASTPROBE P0.2C7',
        'IWM_Q6_ON',
        'IWM_Q7_ON',
        'IWMFastMode',
        'FastModeSaved',
        'SetIWMModeC',
        'sta   >IWM_Q7_ON',
        'eor   >IWM_Q7_OFF',
        'jsr   SetIWMModeC',
    )
    for marker in required:
        if marker not in text:
            raise SystemExit(f'Missing P0.2C7 marker: {marker}')

    # The fast receive path must explicitly select $0F before enabling Read Data.
    start = text.index('ReadFastPacketC')
    end = text.index('FastFindD5C', start)
    receive_entry = text[start:end]
    if '#IWMFastMode' not in receive_entry:
        raise SystemExit('P0.2C7 receive entry does not program IWM fast mode.')
    if receive_entry.index('#IWMFastMode') > receive_entry.index('IWM_DRIVE_ON'):
        raise SystemExit('IWM fast mode must be programmed before DRIVE ENABLE.')

    src.write_text(text, encoding='utf-8', newline='\n')
    print('Applied FASTPROBE P0.2C7 IIgs IWM 2-us receive-mode overlay.')
    print('FujiNet firmware remains P0.2C4 delayed-autosend.')


if __name__ == '__main__':
    main()
