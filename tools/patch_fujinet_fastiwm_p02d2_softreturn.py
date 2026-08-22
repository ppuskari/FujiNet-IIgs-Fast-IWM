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
            'Harden the D1 provider bridge for reset-free host batch returns '
            'and bounded fast-SPI bus acquisition.'
        )
    )
    parser.add_argument('--project-root', default='.')
    parser.add_argument('--firmware-root', required=True)
    args = parser.parse_args()

    project = Path(args.project_root).resolve()
    root = Path(args.firmware_root).resolve()
    base = project / 'tools' / 'patch_fujinet_fastiwm_p02d1_provider.py'
    llcpp = root / 'lib' / 'bus' / 'iwm' / 'iwm_ll.cpp'
    buscpp = root / 'lib' / 'bus' / 'iwm' / 'iwm.cpp'
    if not base.is_file() or not llcpp.is_file() or not buscpp.is_file():
        raise SystemExit('Missing P0.2D1 transform or IWM sources.')

    ltext = llcpp.read_text(encoding='utf-8')
    btext = buscpp.read_text(encoding='utf-8')
    if 'FASTIWM D2 PROVIDER START' in btext:
        print('FujiNet P0.2D2 soft-return overlay already applied.')
        return
    if 'FASTIWM D1 PROVIDER START' not in btext:
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
    if 'FASTIWM D1 PROVIDER START' not in btext:
        raise SystemExit('P0.2D1 firmware transform did not apply.')

    ltext = replace_once(
        ltext,
        'spi_device_acquire_bus(spifast, portMAX_DELAY)',
        'spi_device_acquire_bus(spifast, pdMS_TO_TICKS(100))',
        'unbounded fast-SPI bus acquisition',
    )

    btext = replace_once(
        btext,
        '''        fast_iwm_provider_close(false);
        if (fast_iwm_provider_fifo == nullptr)
''',
        '''        fast_iwm_provider_close(false);
        // A new session must not inherit an armed request or cumulative D1
        // diagnostics from a prior stop/failure.
        fast_iwm_probe_armed = false;
        fast_iwm_probe_request = false;
        fast_iwm_probe_burst_index = 0;
        fast_iwm_probe_burst_remaining = 0;
        fast_iwm_probe_waiting_for_ready_low = false;
        fast_iwm_probe_burst_started = false;
        fast_iwm_probe_arm_deadline = 0;
        fast_iwm_probe_arm_count = 0;
        fast_iwm_probe_req_count = 0;
        fast_iwm_probe_tx_count = 0;
        fast_iwm_provider_bytes_received = 0;
        fast_iwm_provider_packets_sent = 0;
        fast_iwm_provider_batches_sent = 0;
        if (fast_iwm_provider_fifo == nullptr)
''',
        'provider session reset',
    )

    # Keep the D1FS status signature as protocol version 1; only diagnostics
    # and matched build identity advance to D2.
    btext = btext.replace('FASTIWM D1 ', 'FASTIWM D2 ')

    required = (
        'FASTIWM D2 PROVIDER START',
        'FASTIWM D2 PROVIDER CONNECTED',
        'FASTIWM D2 PROVIDER BATCH ARMED packets=32 pcm=16384',
        'FASTIWM D2 PROVIDER BATCH DONE',
        'fast_iwm_probe_arm_count = 0',
        'fast_iwm_provider_batches_sent = 0',
        'pdMS_TO_TICKS(100)',
        "reply[0] = 'D'",
        "reply[1] = '1'",
    )
    joined = ltext + '\n' + btext
    for marker in required:
        if marker not in joined:
            raise SystemExit(f'Missing P0.2D2 firmware marker: {marker}')
    if 'FASTIWM D1 ' in btext:
        raise SystemExit('Obsolete D1 firmware diagnostic remains.')
    if 'spi_device_acquire_bus(spifast, portMAX_DELAY)' in ltext:
        raise SystemExit('Unbounded P0.2D1 fast-SPI acquisition remains.')

    llcpp.write_text(ltext, encoding='utf-8', newline='\n')
    buscpp.write_text(btext, encoding='utf-8', newline='\n')
    print('Applied FujiNet P0.2D2 reset-free provider hardening overlay.')


if __name__ == '__main__':
    main()
