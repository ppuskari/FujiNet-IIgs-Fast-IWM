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
        description='Apply P0.2C host transform then enable the IWM Read-Data state correctly.'
    )
    parser.add_argument('--project-root', default='.')
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    base = root / 'tools' / 'run_spbench_fastiwm_p02c.py'
    src = root / 'iigs' / 'spbench' / 'src' / 'SPBench.s'

    if not base.is_file():
        raise SystemExit(f'Missing P0.2C host transform: {base}')
    if not src.is_file():
        raise SystemExit(f'Missing SPBENCH source: {src}')

    subprocess.run(
        [sys.executable, str(base), '--project-root', str(root)],
        check=True,
    )

    text = src.read_text(encoding='utf-8')
    if 'FASTPROBE P0.2C5' in text:
        print('FASTPROBE P0.2C5 host overlay already applied.')
        return
    if 'FASTPROBE P0.2C' not in text:
        raise SystemExit('P0.2C host transform did not apply.')

    # Apple IIgs Technical Note #30 corrects the Hardware Reference table:
    # Read Data requires Q7=0, Q6=0, and DRIVE ENABLED.  P0.2C selected
    # Q7/Q6 but never asserted $C0E9, so it was not actually reading the
    # IWM Data register when the proven P0.2C4 packet arrived.
    #
    # $C0E9 can also trigger the Slot-6 Disk II automatic slowdown when
    # Speed register bit 2 is set.  Preserve the exact Speed register, clear
    # only detector bit 2 for this probe, and restore it after the packet so
    # the 65816 remains at the user's current CPU speed while receiving.

    const_old = '''IWM_PH3_OFF     equ   $00C0E6
IWM_PH3_ON      equ   $00C0E7
IWM_Q6_OFF      equ   $00C0EC
IWM_Q7_OFF      equ   $00C0EE
'''
    const_new = '''IWM_PH3_OFF     equ   $00C0E6
IWM_PH3_ON      equ   $00C0E7
IWM_DRIVE_OFF   equ   $00C0E8
IWM_DRIVE_ON    equ   $00C0E9
IWM_Q6_OFF      equ   $00C0EC
IWM_Q7_OFF      equ   $00C0EE
IIGS_SPEED      equ   $00C036
Slot6DetectMask equ   $04
'''
    text = replace_once(text, const_old, const_new, 'P0.2C IWM constants')

    text = replace_once(
        text,
        "         asc   'FASTPROBE P0.2C - SmartPort-armed Fast-IWM'0d\n",
        "         asc   'FASTPROBE P0.2C5 - drive-enabled Fast-IWM read'0d\n",
        'P0.2C banner',
    )

    read_old = '''ReadFastPacketC
         php
         sei
         sep   #$20

* PH3..PH0 = 1010.
'''
    read_new = '''ReadFastPacketC
         php
         sei
         sep   #$20

* Preserve the IIgs Speed register and temporarily disable only the
* Slot-6 Disk II motor-on detector.  This prevents the required $C0E9
* drive-enable access from forcing the CPU down to 1.024 MHz.
         lda   >IIGS_SPEED
         sta   FastSpeedSaved
         and   #$FB
         sta   >IIGS_SPEED

* Technical Note #30: Read Data requires DRIVE ENABLED plus Q7=0/Q6=0.
         lda   >IWM_DRIVE_ON

* PH3..PH0 = 1010.
'''
    text = replace_once(text, read_old, read_new, 'ReadFastPacketC entry')

    reset_old = '''         lda   >IWM_PH0_OFF
         lda   >IWM_PH2_OFF
         rts
'''
    reset_new = '''         lda   >IWM_PH0_OFF
         lda   >IWM_PH2_OFF

* Leave the disk interface and machine speed exactly as we found them.
         lda   >IWM_DRIVE_OFF
         lda   FastSpeedSaved
         sta   >IIGS_SPEED
         rts
'''
    text = replace_once(text, reset_old, reset_new, 'ResetFastBusC exit')

    state_old = '''FastPatternFail ds   2
FastBufferC     ds    512

RawHandle      ds    4
'''
    state_new = '''FastPatternFail ds   2
FastSpeedSaved ds    2
FastBufferC     ds    512

RawHandle      ds    4
'''
    text = replace_once(text, state_old, state_new, 'P0.2C state block')

    timeout_old = "         asc   'FAST FAILED: timeout waiting for 2us IWM stream.'0d00\n"
    timeout_new = "         asc   'FAST FAILED: drive-enabled IWM read timed out.'0d00\n"
    text = replace_once(text, timeout_old, timeout_new, 'timeout message')

    required = (
        'FASTPROBE P0.2C5',
        'IWM_DRIVE_ON',
        'IWM_DRIVE_OFF',
        'IIGS_SPEED',
        'FastSpeedSaved',
        'and   #$FB',
        'lda   >IWM_DRIVE_ON',
        'lda   >IWM_DRIVE_OFF',
    )
    for marker in required:
        if marker not in text:
            raise SystemExit(f'Missing P0.2C5 marker: {marker}')

    src.write_text(text, encoding='utf-8', newline='\n')
    print('Applied FASTPROBE P0.2C5 drive-enabled IWM Read-Data overlay.')
    print('FujiNet firmware remains P0.2C4; host only changed.')


if __name__ == '__main__':
    main()
