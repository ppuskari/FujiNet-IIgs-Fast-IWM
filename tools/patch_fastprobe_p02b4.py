from pathlib import Path
import argparse
import subprocess
import sys


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f'Expected {label} pattern not found.')
    return text.replace(old, new, 1)


def run_patch(script: Path, root: Path, label: str) -> None:
    if not script.is_file():
        raise SystemExit(f'{label} patch not found: {script}')
    subprocess.run(
        [sys.executable, str(script), '--project-root', str(root)],
        check=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            'Apply FASTPROBE B2 -> B3 -> B4 and add explicit drive-1 '
            'select before motor-on.'
        )
    )
    parser.add_argument('--project-root', default='.')
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    src = root / 'iigs' / 'fastprobe' / 'src' / 'FastProbe.s'
    b2_patch = root / 'tools' / 'patch_fastprobe_p02b2.py'
    b3_patch = root / 'tools' / 'patch_fastprobe_p02b3.py'

    if not src.is_file():
        raise SystemExit(f'FASTPROBE source not found: {src}')

    text = src.read_text(encoding='utf-8')
    if 'FASTPROBE P0.2B4' in text:
        print('FASTPROBE P0.2B4 patch already applied.')
        return

    # The repository stores the baseline P0.2B source plus cumulative
    # experiment overlays. Apply the prerequisites explicitly and in order.
    if 'FASTPROBE P0.2B2' not in text and 'FASTPROBE P0.2B3' not in text:
        run_patch(b2_patch, root, 'P0.2B2')

    text = src.read_text(encoding='utf-8')
    if 'FASTPROBE P0.2B3' not in text:
        run_patch(b3_patch, root, 'P0.2B3')

    text = src.read_text(encoding='utf-8')
    if 'FASTPROBE P0.2B3' not in text:
        raise SystemExit('P0.2B3 prerequisite was not established.')

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
        'IWM_MOTOR_ON   equ   $00C0E9\n',
        'IWM_MOTOR_ON   equ   $00C0E9\n'
        'IWM_DRIVE_1    equ   $00C0EA\n',
        'IWM motor-on constant',
    )

    # B3 modifies EnterFastPhase directly. Insert drive-1 selection into
    # that real block immediately before B3 asserts motor/drive enable.
    enter_old = '''* P0.2B3: Q6=0/Q7=0 addresses the IWM Read-Data register only
* while the spindle/drive-enable state is ON.  B2 omitted this.
         lda   >IWM_MOTOR_ON

* Capture status for post-transfer diagnostics.  Q6=1/Q7=0 selects
* Status; bit 5 indicates that a drive is selected and enabled.
'''
    enter_new = '''* P0.2B4: select drive 1 before asserting motor/drive enable.
* B3 asserted only MOTOR_ON and status bit 5 remained clear ($CC).
         lda   >IWM_DRIVE_1
         lda   >IWM_MOTOR_ON

* Capture status for post-transfer diagnostics.  Q6=1/Q7=0 selects
* Status; bit 5 indicates that a drive is selected and enabled.
'''
    text = replace_once(text, enter_old, enter_new, 'B3 EnterFastPhase motor block')

    text = replace_once(
        text,
        "MotorStatusMsg\n         asc   'IWM status captured with motor ON=$'00\n",
        "MotorStatusMsg\n         asc   'IWM status with drive1+motor ON=$'00\n",
        'motor status message',
    )

    src.write_text(text, encoding='utf-8', newline='\n')
    print('Applied FASTPROBE P0.2B4 drive-1 select + motor-on patch.')


if __name__ == '__main__':
    main()
