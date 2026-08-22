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
            'Apply P0.2C13 and identify the controlled 0.5-us-pulse '
            'experiment while retaining the exact-$0F 3.5-inch route.'
        )
    )
    parser.add_argument('--project-root', default='.')
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    base = root / 'tools' / 'patch_spbench_fastiwm_p02c13.py'
    src = root / 'iigs' / 'spbench' / 'src' / 'SPBench.s'
    if not base.is_file() or not src.is_file():
        raise SystemExit('Missing P0.2C13 host transform or SPBENCH source.')

    text = src.read_text(encoding='utf-8')
    if 'FASTPROBE P0.2C14' in text:
        print('FASTPROBE P0.2C14 host overlay already applied.')
        return
    if 'FASTPROBE P0.2C13' not in text:
        subprocess.run(
            [sys.executable, str(base), '--project-root', str(root)],
            check=True,
        )
        text = src.read_text(encoding='utf-8')
    if 'FASTPROBE P0.2C13' not in text:
        raise SystemExit('P0.2C13 host transform did not apply.')

    text = replace_once(
        text,
        "         asc   'FASTPROBE P0.2C13 - 3.5-routed exact-$0F link'0d\n",
        "         asc   'FASTPROBE P0.2C14 - 0.5us-pulse 3.5 route'0d\n",
        'P0.2C13 banner',
    )
    text = replace_once(
        text,
        "         asc   'FAST FAILED: C13 3.5-route IWM read timed out.'0d00\n",
        "         asc   'FAST FAILED: C14 0.5us-pulse IWM read timed out.'0d00\n",
        'P0.2C13 timeout message',
    )

    required = (
        'FASTPROBE P0.2C14',
        'FAST FAILED: C14 0.5us-pulse IWM read timed out.',
        'P0.2C13: DISKREG bit 6 selects the IIgs 3.5-inch path',
        'ora   #$40',
        'sta   FastDiskRegActive',
        'DISKREG saved/active=$',
        'cmp   #IWMFastMode',
        'IWM_PH0_ON      equ   $E1C0E1',
    )
    for marker in required:
        if marker not in text:
            raise SystemExit(f'Missing P0.2C14 host marker: {marker}')

    receive = text[text.index('\nReadFastPacketC\n'):text.index('\nFastFindD5C\n')]
    slot_route = receive.index('sta   >IIGS_SLTROMSEL')
    disk_route = receive.index('ora   #$40')
    mode = receive.index('jsr   SetIWMModeC')
    ready = receive.index('lda   >IWM_PH0_ON')
    if not (slot_route < disk_route < mode < ready):
        raise SystemExit('Unsafe P0.2C14 Slot/DISKREG/mode/READY ordering.')

    src.write_text(text, encoding='utf-8', newline='\n')
    print('Applied FASTPROBE P0.2C14 0.5-us-pulse experiment overlay.')


if __name__ == '__main__':
    main()
