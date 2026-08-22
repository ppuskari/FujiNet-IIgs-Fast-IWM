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
            'Label the D3 app-configured provider client for the D4 firmware '
            'that restores the ESP-IDF-supported blocking SPI bus wait.'
        )
    )
    parser.add_argument('--project-root', default='.')
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    base = root / 'tools' / 'patch_spbench_fastiwm_p02d3_endpoint.py'
    src = root / 'iigs' / 'spbench' / 'src' / 'SPBench.s'
    if not base.is_file() or not src.is_file():
        raise SystemExit('Missing P0.2D3 transform or SPBENCH source.')

    text = src.read_text(encoding='utf-8')
    if 'FASTPROBE P0.2D4' in text:
        print('FASTPROBE P0.2D4 SPI-wait overlay already applied.')
        return
    if 'FASTPROBE P0.2D3' not in text:
        subprocess.run(
            [sys.executable, str(base), '--project-root', str(root)],
            check=True,
        )
        text = src.read_text(encoding='utf-8')
    if 'FASTPROBE P0.2D3' not in text:
        raise SystemExit('P0.2D3 host transform did not apply.')

    text = replace_once(
        text,
        "         asc   'FASTPROBE P0.2D3 - app-configured provider'0d\n",
        "         asc   'FASTPROBE P0.2D4 - corrected SPI provider'0d\n",
        'D3 banner',
    )

    required = (
        'FASTPROBE P0.2D4 - corrected SPI provider',
        'D3ProviderConfigBlockLo equ $A556',
        "asc   'D3EP'",
        'LeaveFastBusD2',
        'Server IP or DNS name [192.168.5.235]:',
        'TCP port [22510]:',
    )
    for marker in required:
        if marker not in text:
            raise SystemExit(f'Missing P0.2D4 host marker: {marker}')

    src.write_text(text, encoding='utf-8', newline='\n')
    print('Applied FASTPROBE P0.2D4 corrected SPI-provider label overlay.')


if __name__ == '__main__':
    main()
