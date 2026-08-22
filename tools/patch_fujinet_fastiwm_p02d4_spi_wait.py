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
            'Restore the only ESP-IDF-supported SPI bus acquisition wait '
            'for the D3 app-configured provider stream.'
        )
    )
    parser.add_argument('--project-root', default='.')
    parser.add_argument('--firmware-root', required=True)
    args = parser.parse_args()

    project = Path(args.project_root).resolve()
    root = Path(args.firmware_root).resolve()
    base = project / 'tools' / 'patch_fujinet_fastiwm_p02d3_endpoint.py'
    llcpp = root / 'lib' / 'bus' / 'iwm' / 'iwm_ll.cpp'
    buscpp = root / 'lib' / 'bus' / 'iwm' / 'iwm.cpp'
    if not base.is_file() or not llcpp.is_file() or not buscpp.is_file():
        raise SystemExit('Missing P0.2D3 transform or IWM sources.')

    ltext = llcpp.read_text(encoding='utf-8')
    btext = buscpp.read_text(encoding='utf-8')
    if 'FASTIWM D4 ENDPOINT SET' in btext:
        print('FujiNet P0.2D4 SPI-wait overlay already applied.')
        return
    if 'FASTIWM D3 ENDPOINT SET' not in btext:
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
    if 'FASTIWM D3 ENDPOINT SET' not in btext:
        raise SystemExit('P0.2D3 firmware transform did not apply.')

    # ESP-IDF's spi_device_acquire_bus currently accepts only portMAX_DELAY.
    # D2's finite timeout is rejected immediately with ESP_ERR_INVALID_ARG,
    # so no waveform reaches the IIgs even when the provider FIFO is full.
    ltext = replace_once(
        ltext,
        'spi_device_acquire_bus(spifast, pdMS_TO_TICKS(100))',
        'spi_device_acquire_bus(spifast, portMAX_DELAY)',
        'unsupported finite SPI acquisition timeout',
    )
    btext = btext.replace('FASTIWM D3 ', 'FASTIWM D4 ')

    required = (
        'spi_device_acquire_bus(spifast, portMAX_DELAY)',
        'FASTIWM D4 ENDPOINT SET',
        'FASTIWM D4 PROVIDER START',
        'FASTIWM D4 PROVIDER CONNECTED',
        'FASTIWM D4 PROVIDER BATCH ARMED',
        'FASTIWM D4 PROVIDER BATCH DONE',
        'fast_iwm_provider_host = "192.168.5.235"',
    )
    joined = ltext + '\n' + btext
    for marker in required:
        if marker not in joined:
            raise SystemExit(f'Missing P0.2D4 firmware marker: {marker}')
    if 'spi_device_acquire_bus(spifast, pdMS_TO_TICKS(100))' in ltext:
        raise SystemExit('Unsupported finite SPI acquisition remains.')
    if 'FASTIWM D3 ' in btext:
        raise SystemExit('Obsolete D3 firmware diagnostic remains.')

    llcpp.write_text(ltext, encoding='utf-8', newline='\n')
    buscpp.write_text(btext, encoding='utf-8', newline='\n')
    print('Applied FujiNet P0.2D4 supported blocking SPI-wait overlay.')


if __name__ == '__main__':
    main()
