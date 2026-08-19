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
        description='Patch FASTPROBE through P0.2B3 then add explicit drive-1 select for P0.2B4.'
    )
    parser.add_argument('--project-root', default='.')
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    b3_patch = root / 'tools' / 'patch_fastprobe_p02b3.py'
    src = root / 'iigs' / 'fastprobe' / 'src' / 'FastProbe.s'

    if not b3_patch.is_file():
        raise SystemExit(f'P0.2B3 patch not found: {b3_patch}')
    if not src.is_file():
        raise SystemExit(f'FASTPROBE source not found: {src}')

    subprocess.run(
        [sys.executable, str(b3_patch), '--project-root', str(root)],
        check=True,
    )

    text = src.read_text(encoding='utf-8')
    if 'FASTPROBE P0.2B4' in text:
        print('FASTPROBE P0.2B4 patch already applied.')
        return

    text = replace_once(
        text,
        '* FASTPROBE P0.2B3\n',
        '* FASTPROBE P0.2B4\n',
        'source version header',
    )

    text = replace_once(
        text,
        "         asc   'FASTPROBE P0.2B3 - motor-on Fast-IWM read test'0d\n",
        "         asc   'FASTPROBE P0.2B4 - drive-select Fast-IWM read'0d\n",
        'screen banner',
    )

    text = replace_once(
        text,
        'IWM_MOTOR_ON    equ   $00C0E9\n',
        'IWM_MOTOR_ON    equ   $00C0E9\n'
        'IWM_DRIVE_1     equ   $00C0EA\n',
        'IWM motor-on constant',
    )

    old = '''StartReadDataMode
         php
         sei
         sep   #$20

         lda   >IWM_MOTOR_ON

* Read Status immediately while motor/drive enable is active.
         lda   >IWM_Q6_ON
         lda   >IWM_Q7_OFF
         sta   MotorOnStatus

* Select Read-Data register: Q6=0, Q7=0, motor/drive enable ON.
         lda   >IWM_Q7_OFF
         lda   >IWM_Q6_OFF
         lda   >IWM_Q6_OFF

         rep   #$20
         plp
         rts
'''

    new = '''StartReadDataMode
         php
         sei
         sep   #$20

* Apple documents the drive-enable and drive-select soft switches as
* working together.  P0.2B3 asserted only $C0E9 and status bit 5 stayed
* clear.  Explicitly select drive 1, then assert the motor/drive enable.
         lda   >IWM_DRIVE_1
         lda   >IWM_MOTOR_ON

* Read Status immediately while drive 1 + motor/enable are active.
         lda   >IWM_Q6_ON
         lda   >IWM_Q7_OFF
         sta   MotorOnStatus

* Select Read-Data register: Q6=0, Q7=0, selected drive + motor ON.
         lda   >IWM_Q7_OFF
         lda   >IWM_Q6_OFF
         lda   >IWM_Q6_OFF

         rep   #$20
         plp
         rts
'''
    text = replace_once(text, old, new, 'StartReadDataMode block')

    text = replace_once(
        text,
        "MotorStatusMsg\n         asc   'IWM status captured with motor ON=$'00\n",
        "MotorStatusMsg\n         asc   'IWM status with drive1+motor ON=$'00\n",
        'motor status message',
    )

    src.write_text(text, encoding='utf-8', newline='\n')
    print('Applied FASTPROBE P0.2B4 explicit drive-1 select + motor-on patch.')


if __name__ == '__main__':
    main()
