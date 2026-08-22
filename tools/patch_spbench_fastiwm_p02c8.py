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
        description='Apply P0.2C7 then enforce 8-bit IWM mode-register assembly.'
    )
    parser.add_argument('--project-root', default='.')
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    base = root / 'tools' / 'patch_spbench_fastiwm_p02c7.py'
    src = root / 'iigs' / 'spbench' / 'src' / 'SPBench.s'

    if not base.is_file():
        raise SystemExit(f'Missing P0.2C7 host transform: {base}')
    if not src.is_file():
        raise SystemExit(f'Missing SPBENCH source: {src}')

    subprocess.run(
        [sys.executable, str(base), '--project-root', str(root)],
        check=True,
    )

    text = src.read_text(encoding='utf-8')
    if 'FASTPROBE P0.2C8' in text:
        print('FASTPROBE P0.2C8 host overlay already applied.')
        return
    if 'FASTPROBE P0.2C7' not in text:
        raise SystemExit('P0.2C7 host transform did not apply.')

    text = replace_once(
        text,
        "         asc   'FASTPROBE P0.2C7 - IIgs IWM 2us receive mode'0d\n",
        "         asc   'FASTPROBE P0.2C8 - 8-bit-safe IWM 2us mode'0d\n",
        'P0.2C7 banner',
    )

    old_routine = '''* M=8 on entry/return. Desired mode is passed in A.
SetIWMModeC
         sta   FastModeDesired
'''
    new_routine = '''* P0.2C8: enforce M=8 in both the CPU and Merlin assembler state.
* C7 assembled AND #IWMModeMask as 29 1F 00 while the CPU had M=1;
* the leftover 00 at $0A/0640 executed as BRK before the receive loop.
* Desired mode is passed in A; M=8 on return.
SetIWMModeC
         sep   #$20
         sta   FastModeDesired
'''
    text = replace_once(
        text,
        old_routine,
        new_routine,
        'P0.2C7 SetIWMModeC entry',
    )

    required = (
        'FASTPROBE P0.2C8',
        'P0.2C8: enforce M=8',
        'SetIWMModeC\n         sep   #$20',
        'and   #IWMModeMask',
        'sta   >IWM_Q7_ON',
        'eor   >IWM_Q7_OFF',
    )
    for marker in required:
        if marker not in text:
            raise SystemExit(f'Missing P0.2C8 marker: {marker}')

    routine_start = text.index('\nSetIWMModeC\n') + 1
    loop_end = text.index('         rts\n', routine_start)
    routine = text[routine_start:loop_end]
    if routine.index('sep   #$20') > routine.index('and   #IWMModeMask'):
        raise SystemExit('M=8 must be established before the mode-mask immediate.')

    src.write_text(text, encoding='utf-8', newline='\n')
    print('Applied FASTPROBE P0.2C8 8-bit-safe IWM mode-programming overlay.')
    print('FujiNet firmware remains P0.2C4 delayed-autosend.')


if __name__ == '__main__':
    main()
