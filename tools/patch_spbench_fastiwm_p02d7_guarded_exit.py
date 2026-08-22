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
        description=(
            'Restore all IIgs IWM routing registers after every successful '
            'provider batch so every failure/quit path is GS/OS-safe.'
        )
    )
    parser.add_argument('--project-root', default='.')
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    base = root / 'tools' / 'patch_spbench_fastiwm_p02d6_direct_ring.py'
    src = root / 'iigs' / 'spbench' / 'src' / 'SPBench.s'
    if not base.is_file() or not src.is_file():
        raise SystemExit('Missing P0.2D6 transform or SPBENCH source.')

    text = src.read_text(encoding='utf-8')
    if 'FASTPROBE P0.2D7' in text:
        print('FASTPROBE P0.2D7 guarded-exit overlay already applied.')
        return
    if 'FASTPROBE P0.2D6' not in text:
        subprocess.run(
            [sys.executable, str(base), '--project-root', str(root)],
            check=True,
        )
        text = src.read_text(encoding='utf-8')
    if 'FASTPROBE P0.2D6' not in text:
        raise SystemExit('P0.2D6 host transform did not apply.')

    text = replace_once(
        text,
        "         asc   'FASTPROBE P0.2D6 - direct ring decode'0d\n",
        "         asc   'FASTPROBE P0.2D7 - guarded SPI/GSOS exit'0d\n",
        'D6 banner',
    )

    text = replace_once(
        text,
        '''* Successful D2 batch return. PH3..PH0 is already the normal upstream
* SmartPort enable state 1010 after the final READY-low edge. Do not touch the
* phase lines here: 0101 would reset FujiNet and force complete re-enumeration.
* M=8 on entry/return.
LeaveFastBusD2
         lda   >IWM_DRIVE_OFF
         lda   FastModeSaved
         jsr   SetIWMModeC
         lda   FastSpeedSaved
         sta   >IIGS_SPEED
         rts
''',
        '''* Successful D7 batch return. PH3..PH0 is already the normal upstream
* SmartPort enable state 1010 after the final READY-low edge. Do not pulse the
* 0101 reset signature, but restore every IIgs mapping/control register now.
* Leaving internal Slot 6 or the 3.5-inch route selected loses the original
* values on the next packet and makes a later GS/OS quit enter the wrong $C600
* slot ROM. M=8 on entry/return.
LeaveFastBusD2
         lda   >IWM_DRIVE_OFF
         lda   FastModeSaved
         jsr   SetIWMModeC
         lda   FastDiskRegSaved
         sta   >IIGS_DISKREG
         lda   FastSlotRegSaved
         sta   >IIGS_SLTROMSEL
         lda   FastSpeedSaved
         sta   >IIGS_SPEED
         rts
''',
        'D6 successful batch cleanup',
    )

    required = (
        'FASTPROBE P0.2D7 - guarded SPI/GSOS exit',
        'Leaving internal Slot 6 or the 3.5-inch route selected',
        'lda   FastDiskRegSaved\n         sta   >IIGS_DISKREG',
        'lda   FastSlotRegSaved\n         sta   >IIGS_SLTROMSEL',
        'P0.2D6 patches two long stores',
        'P0.2D5: remain M=0/X=0',
    )
    for marker in required:
        if marker not in text:
            raise SystemExit(f'Missing P0.2D7 host marker: {marker}')

    success = text[
        text.index('\nLeaveFastBusD2\n'):
        text.index('\nResetFastBusC\n')
    ]
    for marker in (
        'sta   >IIGS_DISKREG',
        'sta   >IIGS_SLTROMSEL',
        'sta   >IIGS_SPEED',
    ):
        if marker not in success:
            raise SystemExit(
                f'P0.2D7 successful cleanup does not restore {marker}.'
            )
    if 'jsr   ResetFastBusC' in success:
        raise SystemExit('P0.2D7 successful batch unexpectedly resets FujiNet.')

    src.write_text(text, encoding='utf-8', newline='\n')
    print('Applied FASTPROBE P0.2D7 full-route guarded-exit overlay.')


if __name__ == '__main__':
    main()
