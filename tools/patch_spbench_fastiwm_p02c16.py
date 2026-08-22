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
            'Apply the corrected P0.2C15 byte trace and identify it as the '
            'width-safe P0.2C16 host experiment.'
        )
    )
    parser.add_argument('--project-root', default='.')
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    base = root / 'tools' / 'patch_spbench_fastiwm_p02c15.py'
    src = root / 'iigs' / 'spbench' / 'src' / 'SPBench.s'
    if not base.is_file() or not src.is_file():
        raise SystemExit('Missing corrected P0.2C15 transform or SPBENCH source.')

    text = src.read_text(encoding='utf-8')
    if 'FASTPROBE P0.2C16' in text:
        print('FASTPROBE P0.2C16 host overlay already applied.')
        return
    if 'FASTPROBE P0.2C15' not in text:
        subprocess.run(
            [sys.executable, str(base), '--project-root', str(root)],
            check=True,
        )
        text = src.read_text(encoding='utf-8')
    if 'FASTPROBE P0.2C15' not in text:
        raise SystemExit('Corrected P0.2C15 host transform did not apply.')

    text = replace_once(
        text,
        "         asc   'FASTPROBE P0.2C15 - IWM byte observability'0d\n",
        "         asc   'FASTPROBE P0.2C16 - width-safe byte trace'0d\n",
        'P0.2C15 banner',
    )
    text = replace_once(
        text,
        "         asc   'FAST FAILED: C15 IWM byte trace timed out.'0d00\n",
        "         asc   'FAST FAILED: C16 IWM byte trace timed out.'0d00\n",
        'P0.2C15 timeout message',
    )

    required = (
        'FASTPROBE P0.2C16',
        'FAST FAILED: C16 IWM byte trace timed out.',
        'IWM ready samples=$',
        'settle.\n         mx    %10\n         pha',
        'rep   #$20\n         mx    %00',
        'and   #$00FF\n         tay',
        'sep   #$20\n         mx    %10',
        'sta   FastReadySamples,y',
        'cmp   #IWMFastMode',
        'P0.2C13: DISKREG bit 6 selects the IIgs 3.5-inch path',
    )
    for marker in required:
        if marker not in text:
            raise SystemExit(f'Missing P0.2C16 host marker: {marker}')

    trace = text[text.index('\nFastByteReadyC\n'):text.index('\nResetFastBusC\n')]
    order = (
        trace.index('rep   #$20'),
        trace.index('mx    %00'),
        trace.index('and   #$00FF'),
        trace.index('tay'),
        trace.index('sep   #$20'),
        trace.rindex('mx    %10'),
        trace.index('sta   FastReadySamples,y'),
    )
    if tuple(sorted(order)) != order:
        raise SystemExit('Unsafe P0.2C16 accumulator/index-width ordering.')

    src.write_text(text, encoding='utf-8', newline='\n')
    print('Applied FASTPROBE P0.2C16 width-safe IWM byte trace overlay.')


if __name__ == '__main__':
    main()
