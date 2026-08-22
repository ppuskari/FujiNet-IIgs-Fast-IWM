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
            'Apply the fully width-annotated P0.2C16 byte trace and identify '
            'it as the P0.2C17 host experiment.'
        )
    )
    parser.add_argument('--project-root', default='.')
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    base = root / 'tools' / 'patch_spbench_fastiwm_p02c16.py'
    src = root / 'iigs' / 'spbench' / 'src' / 'SPBench.s'
    if not base.is_file() or not src.is_file():
        raise SystemExit('Missing corrected P0.2C16 transform or SPBENCH source.')

    text = src.read_text(encoding='utf-8')
    if 'FASTPROBE P0.2C17' in text:
        print('FASTPROBE P0.2C17 host overlay already applied.')
        return
    if 'FASTPROBE P0.2C16' not in text:
        subprocess.run(
            [sys.executable, str(base), '--project-root', str(root)],
            check=True,
        )
        text = src.read_text(encoding='utf-8')
    if 'FASTPROBE P0.2C16' not in text:
        raise SystemExit('Corrected P0.2C16 host transform did not apply.')

    text = replace_once(
        text,
        "         asc   'FASTPROBE P0.2C16 - width-safe byte trace'0d\n",
        "         asc   'FASTPROBE P0.2C17 - verified byte trace'0d\n",
        'P0.2C16 banner',
    )
    text = replace_once(
        text,
        "         asc   'FAST FAILED: C16 IWM byte trace timed out.'0d00\n",
        "         asc   'FAST FAILED: C17 IWM byte trace timed out.'0d00\n",
        'P0.2C16 timeout message',
    )

    required = (
        'FASTPROBE P0.2C17',
        'FAST FAILED: C17 IWM byte trace timed out.',
        'FastByteReadyC\n* Record at most eight ready bytes.',
        'settle.\n         mx    %10\n         pha',
        'cmp   #FastReadySampleLimit',
        'rep   #$20\n         mx    %00',
        'and   #$00FF\n         tay',
        'sep   #$20\n         mx    %10',
        'sta   FastReadySamples,y',
    )
    for marker in required:
        if marker not in text:
            raise SystemExit(f'Missing P0.2C17 host marker: {marker}')

    trace = text[text.index('\nFastByteReadyC\n'):text.index('\nResetFastBusC\n')]
    order = (
        trace.index('mx    %10'),
        trace.index('cmp   #FastReadySampleLimit'),
        trace.index('rep   #$20'),
        trace.index('mx    %00'),
        trace.index('and   #$00FF'),
        trace.index('tay'),
        trace.index('sep   #$20'),
        trace.rindex('mx    %10'),
        trace.index('sta   FastReadySamples,y'),
    )
    if tuple(sorted(order)) != order:
        raise SystemExit('Unsafe P0.2C17 accumulator/index-width ordering.')

    src.write_text(text, encoding='utf-8', newline='\n')
    print('Applied FASTPROBE P0.2C17 verified IWM byte trace overlay.')


if __name__ == '__main__':
    main()
