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
        description='Apply proven P0.2C4 delayed autosend then change only the delay from 50 ms to 100 ms.'
    )
    parser.add_argument('--project-root', default='.')
    parser.add_argument('--firmware-root', required=True)
    args = parser.parse_args()

    project = Path(args.project_root).resolve()
    firmware = Path(args.firmware_root).resolve()
    base_patch = project / 'tools' / 'patch_fujinet_fastiwm_p02c4.py'
    buscpp = firmware / 'lib' / 'bus' / 'iwm' / 'iwm.cpp'

    if not base_patch.is_file():
        raise SystemExit(f'Missing P0.2C4 patch: {base_patch}')
    if not buscpp.is_file():
        raise SystemExit(f'Missing FujiNet IWM bus source: {buscpp}')

    subprocess.run(
        [sys.executable, str(base_patch),
         '--project-root', str(project),
         '--firmware-root', str(firmware)],
        check=True,
    )

    text = buscpp.read_text(encoding='utf-8')
    if 'FASTIWM C4T100 AUTOSEND scheduled' in text:
        print('FujiNet P0.2C4T100 overlay already applied.')
        return

    text = replace_once(
        text,
        'fast_iwm_probe_autosend_due = fnSystem.millis() + 50UL;',
        'fast_iwm_probe_autosend_due = fnSystem.millis() + 100UL;',
        'C4 autosend delay',
    )
    text = replace_once(
        text,
        'FASTIWM C4 AUTOSEND scheduled due=%lu now=%lu',
        'FASTIWM C4T100 AUTOSEND scheduled due=%lu now=%lu',
        'schedule diagnostic',
    )
    text = replace_once(
        text,
        'FASTIWM C4 AUTO TX START count=%lu now=%lu',
        'FASTIWM C4T100 AUTO TX START count=%lu now=%lu',
        'TX START diagnostic',
    )
    text = replace_once(
        text,
        'FASTIWM C4 AUTO TX DONE count=%lu err=%d now=%lu',
        'FASTIWM C4T100 AUTO TX DONE count=%lu err=%d now=%lu',
        'TX DONE diagnostic',
    )

    required = (
        'fnSystem.millis() + 100UL',
        'FASTIWM C4T100 AUTOSEND scheduled',
        'FASTIWM C4T100 AUTO TX START',
        'FASTIWM C4T100 AUTO TX DONE',
        'iwm_send_fast_probe_spi',
    )
    for marker in required:
        if marker not in text:
            raise SystemExit(f'Missing P0.2C4T100 marker: {marker}')

    buscpp.write_text(text, encoding='utf-8', newline='\n')
    print('Applied FujiNet P0.2C4T100 overlay.')
    print('Only functional change from proven C4: delayed autosend 50 ms -> 100 ms.')
    print('Use the existing FASTPROBE-P0.2C5.po host image.')


if __name__ == '__main__':
    main()
