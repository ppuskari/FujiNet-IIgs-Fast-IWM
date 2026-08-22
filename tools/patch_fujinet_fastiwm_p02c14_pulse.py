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
            'Apply P0.2C12, restore the private 2-MHz RDDATA pulse to the '
            'encoder-native 0.5 us, and report the live 3.5-inch route pins.'
        )
    )
    parser.add_argument('--project-root', default='.')
    parser.add_argument('--firmware-root', required=True)
    args = parser.parse_args()

    project = Path(args.project_root).resolve()
    root = Path(args.firmware_root).resolve()
    base = project / 'tools' / 'patch_fujinet_fastiwm_p02c12_pulse.py'
    llcpp = root / 'lib' / 'bus' / 'iwm' / 'iwm_ll.cpp'
    buscpp = root / 'lib' / 'bus' / 'iwm' / 'iwm.cpp'
    if not base.is_file() or not llcpp.is_file() or not buscpp.is_file():
        raise SystemExit('Missing P0.2C12 firmware transform or IWM sources.')

    ltext = llcpp.read_text(encoding='utf-8')
    btext = buscpp.read_text(encoding='utf-8')
    if 'FASTIWM C14 TX SHAPE' in ltext:
        print('FujiNet P0.2C14 0.5-us-pulse overlay already applied.')
        return
    if 'FASTIWM C12 TX SHAPE' not in ltext:
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
    if 'FASTIWM C12 TX SHAPE' not in ltext:
        raise SystemExit('P0.2C12 firmware transform did not apply.')

    method_start = ltext.index('iwm_send_fast_probe_spi()')
    method_end = ltext.index('#define IWM_NEXT_BIT()', method_start)
    method = ltext[method_start:method_end]
    method = replace_once(
        method,
        '''  // The normal 1-MHz encoder emits one high SPI sample per four-sample
  // IWM cell: a 1-us pulse in a 4-us cell. At 2 MHz the unmodified shape
  // shrinks to 0.5 us. Duplicate each asserted sample so falling edges
  // remain 2 us apart while physical RDDATA pulses remain 1 us wide.
  for (int i = 0; i < spi_len; i++)
    spi_buffer[i] |= (spi_buffer[i] >> 1);

  Debug_printf("\\r\\nFASTIWM C12 TX SHAPE len=%d cell=2us pulse=1us", spi_len);
''',
        '''  // C14 controlled A/B: retain the encoder-native one-sample pulse.
  // At the private 2-MHz SPI clock this is a 0.5-us pulse while falling
  // transitions remain separated by the required 2-us IWM bit cell.
  Debug_printf("\\r\\nFASTIWM C14 TX SHAPE len=%d cell=2us pulse=0.5us", spi_len);
  Debug_printf(
      "\\r\\nFASTIWM C14 TX ROUTE phase=%02x en35=%u d1=%u d2=%u hdsel=%u",
      (unsigned int)_phases,
      IWM_BIT(SP_EN35) ? 1U : 0U,
      IWM_BIT(SP_DRIVE1) ? 1U : 0U,
      IWM_BIT(SP_DRIVE2) ? 1U : 0U,
      IWM_BIT(SP_HDSEL) ? 1U : 0U);
''',
        'P0.2C12 pulse widening block',
    )
    if 'spi_buffer[i] |= (spi_buffer[i] >> 1)' in method:
        raise SystemExit('P0.2C12 pulse widening remains in the C14 send method.')
    ltext = ltext[:method_start] + method + ltext[method_end:]

    btext = btext.replace('FASTIWM C12 ', 'FASTIWM C14 ')

    required = (
        'FASTIWM C14 TX SHAPE',
        'cell=2us pulse=0.5us',
        'FASTIWM C14 TX ROUTE',
        'IWM_BIT(SP_EN35)',
        'IWM_BIT(SP_DRIVE1)',
        'IWM_BIT(SP_DRIVE2)',
        'IWM_BIT(SP_HDSEL)',
        'FASTIWM C14 READY ARMED',
        'FASTIWM C14 READY TRIGGER',
        'FASTIWM C14 READY FALLBACK',
        'iwm_send_fast_probe_spi()',
        'fastcfg.clock_speed_hz = 2 * MHZ',
    )
    joined = ltext + '\n' + btext
    for marker in required:
        if marker not in joined:
            raise SystemExit(f'Missing P0.2C14 firmware marker: {marker}')

    llcpp.write_text(ltext, encoding='utf-8', newline='\n')
    buscpp.write_text(btext, encoding='utf-8', newline='\n')
    print('Applied FujiNet P0.2C14 native 0.5-us-pulse overlay.')


if __name__ == '__main__':
    main()
