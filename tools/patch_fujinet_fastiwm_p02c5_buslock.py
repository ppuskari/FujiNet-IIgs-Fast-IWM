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
        description='Apply P0.2C4, then acquire the Fast-IWM SPI device bus before disabling interrupts.'
    )
    parser.add_argument('--project-root', default='.')
    parser.add_argument('--firmware-root', required=True)
    args = parser.parse_args()

    project = Path(args.project_root).resolve()
    root = Path(args.firmware_root).resolve()
    base_patch = project / 'tools' / 'patch_fujinet_fastiwm_p02c4.py'
    llcpp = root / 'lib' / 'bus' / 'iwm' / 'iwm_ll.cpp'

    subprocess.run(
        [sys.executable, str(base_patch),
         '--project-root', str(project),
         '--firmware-root', str(root)],
        check=True,
    )

    if not llcpp.is_file():
        raise SystemExit(f'Missing FujiNet low-level IWM source: {llcpp}')

    text = llcpp.read_text(encoding='utf-8')

    if 'FASTIWM C5 BUS ACQUIRE START' in text:
        print('FujiNet P0.2C5 bus-lock overlay already applied.')
        return

    old = r'''  // Mirror the timing discipline of the normal SmartPort transmitter:
  // no unrelated interrupt jitter while the physical packet is on wire.
  portDISABLE_INTERRUPTS();
  enable_output();
  esp_err_t ret = spi_device_polling_transmit(spifast, &trans);
  disable_output();
  portENABLE_INTERRUPTS();

  if (ret != ESP_OK)
    RETURN_ERROR_AS_TRUE();
'''

    new = r'''  // P0.2C5: spifast is a second device on the same SPI bus as the
  // proven SmartPort handle. Acquire ownership while interrupts and the
  // scheduler are still available, then preserve the normal no-jitter
  // discipline only for the physical wire transfer itself.
  Debug_printf("\r\nFASTIWM C5 BUS ACQUIRE START");
  esp_err_t acquire_ret = spi_device_acquire_bus(spifast, portMAX_DELAY);
  Debug_printf("\r\nFASTIWM C5 BUS ACQUIRE DONE ret=%d", (int)acquire_ret);

  if (acquire_ret != ESP_OK)
    RETURN_ERROR_AS_TRUE();

  portDISABLE_INTERRUPTS();
  enable_output();
  esp_err_t ret = spi_device_polling_transmit(spifast, &trans);
  disable_output();
  portENABLE_INTERRUPTS();

  spi_device_release_bus(spifast);
  Debug_printf("\r\nFASTIWM C5 BUS RELEASE ret=%d", (int)ret);

  if (ret != ESP_OK)
    RETURN_ERROR_AS_TRUE();
'''

    text = replace_once(text, old, new, 'Fast-IWM polling-transmit block')

    required = (
        'FASTIWM C5 BUS ACQUIRE START',
        'FASTIWM C5 BUS ACQUIRE DONE',
        'spi_device_acquire_bus(spifast, portMAX_DELAY)',
        'spi_device_release_bus(spifast)',
        'FASTIWM C5 BUS RELEASE',
    )
    for marker in required:
        if marker not in text:
            raise SystemExit(f'Missing P0.2C5 marker: {marker}')

    llcpp.write_text(text, encoding='utf-8', newline='\n')

    print('Applied FujiNet P0.2C5 explicit Fast-IWM SPI bus acquisition overlay.')
    print('Host image remains FASTPROBE-P0.2C.po.')


if __name__ == '__main__':
    main()
