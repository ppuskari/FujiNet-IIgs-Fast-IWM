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
            'Make the bank-zero SmartPort thunk safe when its caller has '
            '8-bit accumulator/index flags.'
        )
    )
    parser.add_argument('--project-root', default='.')
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    base = root / 'tools' / 'patch_spbench_fastiwm_p02d4_spi_wait.py'
    src = root / 'iigs' / 'spbench' / 'src' / 'SPBench.s'
    if not base.is_file() or not src.is_file():
        raise SystemExit('Missing P0.2D4 transform or SPBENCH source.')

    text = src.read_text(encoding='utf-8')
    if 'FASTPROBE P0.2D5' in text:
        print('FASTPROBE P0.2D5 thunk-flags overlay already applied.')
        return
    if 'FASTPROBE P0.2D4' not in text:
        subprocess.run(
            [sys.executable, str(base), '--project-root', str(root)],
            check=True,
        )
        text = src.read_text(encoding='utf-8')
    if 'FASTPROBE P0.2D4' not in text:
        raise SystemExit('P0.2D4 host transform did not apply.')

    text = replace_once(
        text,
        "         asc   'FASTPROBE P0.2D4 - corrected SPI provider'0d\n",
        "         asc   'FASTPROBE P0.2D5 - safe SmartPort return'0d\n",
        'D4 banner',
    )

    text = replace_once(
        text,
        '''         plb
         pld
         plp

* Return A=0/C=0 for success or A=SmartPort error/C=1.

         tya
         and   #$00FF
         beq   ThunkReturnOK

         sec
         rtl

ThunkReturnOK
         clc
         rtl
''',
        '''         plb
         pld

* P0.2D5: remain M=0/X=0 while consuming the assembled 16-bit immediate.
* Restoring a caller's M=1 before AND #$00FF made the CPU consume only $FF;
* the leftover high byte $00 was then executed as BRK. Restore caller P only
* after the 16-bit result has been formed, and set carry after that restore.

         tya
         and   #$00FF
         beq   ThunkReturnOK

         plp
         sec
         rtl

ThunkReturnOK
         plp
         clc
         rtl
''',
        'SmartPort thunk return sequence',
    )

    required = (
        'FASTPROBE P0.2D5 - safe SmartPort return',
        'P0.2D5: remain M=0/X=0',
        '''ThunkReturnOK
         plp
         clc
         rtl''',
        'D3ProviderConfigBlockLo equ $A556',
        'LeaveFastBusD2',
    )
    for marker in required:
        if marker not in text:
            raise SystemExit(f'Missing P0.2D5 host marker: {marker}')

    src.write_text(text, encoding='utf-8', newline='\n')
    print('Applied FASTPROBE P0.2D5 SmartPort thunk-flags fix.')


if __name__ == '__main__':
    main()
