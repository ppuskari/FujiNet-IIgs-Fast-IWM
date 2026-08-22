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
            'Apply P0.2C11 and widen only the private 2-MHz RDDATA pulses '
            'from 0.5 us to 1 us without changing 2-us falling-edge spacing.'
        )
    )
    parser.add_argument('--project-root', default='.')
    parser.add_argument('--firmware-root', required=True)
    args = parser.parse_args()

    project = Path(args.project_root).resolve()
    root = Path(args.firmware_root).resolve()
    base = project / 'tools' / 'patch_fujinet_fastiwm_p02c11_route.py'
    llcpp = root / 'lib' / 'bus' / 'iwm' / 'iwm_ll.cpp'
    buscpp = root / 'lib' / 'bus' / 'iwm' / 'iwm.cpp'
    if not base.is_file() or not llcpp.is_file() or not buscpp.is_file():
        raise SystemExit('Missing P0.2C11 firmware transform or IWM sources.')

    ltext = llcpp.read_text(encoding='utf-8')
    btext = buscpp.read_text(encoding='utf-8')
    if 'FASTIWM C12 TX SHAPE' in ltext:
        print('FujiNet P0.2C12 pulse-width overlay already applied.')
        return
    if 'FASTIWM C11 READY ARMED' not in btext:
        subprocess.run(
            [
                sys.executable,
                str(base),
                '--project-root',
                str(project),
                '--firmware-root',
                str(root),
            ],
            check=True,
        )
        ltext = llcpp.read_text(encoding='utf-8')
        btext = buscpp.read_text(encoding='utf-8')
    if 'FASTIWM C11 READY ARMED' not in btext:
        raise SystemExit('P0.2C11 firmware transform did not apply.')

    method_start = ltext.index('iwm_send_fast_probe_spi()')
    method_end = ltext.index('#define IWM_NEXT_BIT()', method_start)
    method = ltext[method_start:method_end]
    method = replace_once(
        method,
        '''  set_output_to_spi();
  int spi_len = encode_spi_packet();

  spi_transaction_t trans;
''',
        '''  set_output_to_spi();
  int spi_len = encode_spi_packet();

  // The normal 1-MHz encoder emits one high SPI sample per four-sample
  // IWM cell: a 1-us pulse in a 4-us cell. At 2 MHz the unmodified shape
  // shrinks to 0.5 us. Duplicate each asserted sample so falling edges
  // remain 2 us apart while physical RDDATA pulses remain 1 us wide.
  for (int i = 0; i < spi_len; i++)
    spi_buffer[i] |= (spi_buffer[i] >> 1);

  Debug_printf("\\r\\nFASTIWM C12 TX SHAPE len=%d cell=2us pulse=1us", spi_len);

  spi_transaction_t trans;
''',
        'P0.2C11 private SPI encoding',
    )
    ltext = ltext[:method_start] + method + ltext[method_end:]

    btext = btext.replace('FASTIWM C11 ', 'FASTIWM C12 ')

    required = (
        'FASTIWM C12 TX SHAPE',
        'spi_buffer[i] |= (spi_buffer[i] >> 1)',
        'cell=2us pulse=1us',
        'FASTIWM C12 READY ARMED',
        'FASTIWM C12 READY TRIGGER',
        'FASTIWM C12 READY FALLBACK',
        'iwm_send_fast_probe_spi()',
        'fastcfg.clock_speed_hz = 2 * MHZ',
    )
    joined = ltext + '\n' + btext
    for marker in required:
        if marker not in joined:
            raise SystemExit(f'Missing P0.2C12 firmware marker: {marker}')

    llcpp.write_text(ltext, encoding='utf-8', newline='\n')
    buscpp.write_text(btext, encoding='utf-8', newline='\n')
    print('Applied FujiNet P0.2C12 1-us-pulse/2-us-cell overlay.')


if __name__ == '__main__':
    main()
