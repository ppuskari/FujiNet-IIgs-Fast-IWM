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
        description='Apply P0.2B responder then P0.2B2 direct-request overlay.'
    )
    parser.add_argument(
        '--project-root',
        default='.',
        help='FujiNet-IIgs-Fast-IWM project checkout.'
    )
    parser.add_argument(
        '--firmware-root',
        required=True,
        help='Pinned fujinet-firmware checkout to patch.'
    )
    args = parser.parse_args()

    project = Path(args.project_root).resolve()
    firmware = Path(args.firmware_root).resolve()
    base_patch = project / 'tools' / 'patch_fujinet_fastiwm_p02b.py'
    llcpp = firmware / 'lib' / 'bus' / 'iwm' / 'iwm_ll.cpp'

    if not base_patch.is_file():
        raise SystemExit(f'Base P0.2B patch script not found: {base_patch}')
    if not llcpp.is_file():
        raise SystemExit(f'FujiNet IWM source not found: {llcpp}')

    subprocess.run(
        [sys.executable, str(base_patch), '--firmware-root', str(firmware)],
        check=True,
    )

    text = llcpp.read_text(encoding='utf-8')
    if 'P0.2B2 direct request' in text:
        print('FujiNet P0.2B2 direct-request overlay already applied.')
        return

    old = '''  if (fast_iwm_probe_armed && (_phases == 0b1111))
  {
    fast_iwm_probe_armed = false;
    fast_iwm_probe_request = true;
    return;
  }
'''
    new = '''  // P0.2B2 direct request: PH3..PH0 = 1111 is sufficient to
  // queue the private transmit even if the host cannot observe ACK
  // through the IWM SENSE path.  1110 still asserts ACK as a useful
  // electrical diagnostic, but it is no longer required for progress.
  if (_phases == 0b1111) // P0.2B2 direct request
  {
    fast_iwm_probe_armed = false;
    fast_iwm_probe_request = true;
    return;
  }
'''
    text = replace_once(text, old, new, 'private 1111 request handler')
    llcpp.write_text(text, encoding='utf-8', newline='\n')

    print('Applied FujiNet Fast-IWM P0.2B2 direct-request overlay.')


if __name__ == '__main__':
    main()
