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
            'Guard the D4 fast-SPI transmitter from duplicate 1011 GPIO '
            'interrupts and defer all IWM ISR diagnostics to service context.'
        )
    )
    parser.add_argument('--project-root', default='.')
    parser.add_argument('--firmware-root', required=True)
    args = parser.parse_args()

    project = Path(args.project_root).resolve()
    root = Path(args.firmware_root).resolve()
    base = project / 'tools' / 'patch_fujinet_fastiwm_p02d4_spi_wait.py'
    llcpp = root / 'lib' / 'bus' / 'iwm' / 'iwm_ll.cpp'
    buscpp = root / 'lib' / 'bus' / 'iwm' / 'iwm.cpp'
    if not base.is_file() or not llcpp.is_file() or not buscpp.is_file():
        raise SystemExit('Missing P0.2D4 transform or IWM sources.')

    ltext = llcpp.read_text(encoding='utf-8')
    btext = buscpp.read_text(encoding='utf-8')
    if 'FASTIWM D7 ENDPOINT SET' in btext:
        print('FujiNet P0.2D7 ISR/SPI guard overlay already applied.')
        return
    if 'FASTIWM D4 ENDPOINT SET' not in btext:
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
    if 'FASTIWM D4 ENDPOINT SET' not in btext:
        raise SystemExit('P0.2D4 firmware transform did not apply.')

    ltext = replace_once(
        ltext,
        '''volatile uint8_t fast_iwm_probe_burst_index = 0;
volatile uint8_t fast_iwm_probe_burst_remaining = 0;
volatile bool fast_iwm_probe_waiting_for_ready_low = false;
volatile bool fast_iwm_probe_burst_started = false;
''',
        '''volatile uint8_t fast_iwm_probe_burst_index = 0;
volatile uint8_t fast_iwm_probe_burst_remaining = 0;
volatile bool fast_iwm_probe_waiting_for_ready_low = false;
volatile bool fast_iwm_probe_burst_started = false;
volatile uint32_t fast_iwm_probe_duplicate_ready_count = 0;
volatile uint32_t fast_iwm_probe_isr_deferred_events = 0;
''',
        'C19 low-level burst state',
    )

    ltext = replace_once(
        ltext,
        '''  if (fast_iwm_probe_armed && (_phases == 0b1011))
  {
    fast_iwm_probe_armed = false;
    fast_iwm_probe_reset_grace = 0;
    fast_iwm_probe_request = true;
    fast_iwm_probe_burst_started = true;
    fast_iwm_probe_req_count++;
    return;
  }

  // ROM cleanup resets after the original 4-us arm must be preserved.
''',
        '''  if (fast_iwm_probe_armed && (_phases == 0b1011))
  {
    fast_iwm_probe_armed = false;
    fast_iwm_probe_reset_grace = 0;
    fast_iwm_probe_request = true;
    fast_iwm_probe_burst_started = true;
    fast_iwm_probe_req_count++;
    return;
  }

  // P0.2D7: once a private burst has begun, any additional interrupt that
  // still samples 1011 belongs to the private READY/TX handshake. Never let
  // it fall through to normal SmartPort receive: that path waits on the same
  // SPI bus currently owned by the fast transmitter and can deadlock in ISR.
  if (fast_iwm_probe_burst_started && (_phases == 0b1011))
  {
    fast_iwm_probe_duplicate_ready_count++;
    return;
  }

  // ROM cleanup resets after the original 4-us arm must be preserved.
''',
        'C19 private READY ISR branch',
    )

    # phi_isr_handler is interrupt context. Serial diagnostics can take a
    # FreeRTOS UART semaphore and are therefore deferred to systemBus::service.
    isr_replacements = (
        (
            '                Debug_printf("\\nWRITE/CTRL received\\nREQ timeout in ISR");',
            '''#ifdef IIGS_FAST_IWM_PROBE
                fast_iwm_probe_isr_deferred_events++;
#endif''',
            'WRITE/CTRL ISR timeout diagnostic',
        ),
        (
            '        Debug_printf("\\r\\nISR Cmd Chksum error, calc %02x, pkt %02x", smartport.calc_checksum, smartport.pkt_checksum);',
            '''#ifdef IIGS_FAST_IWM_PROBE
        fast_iwm_probe_isr_deferred_events++;
#endif''',
            'command checksum ISR diagnostic',
        ),
        (
            '        Debug_printf("\\r\\nISR Data Packet Chksum error, calc %02x, pkt %02x command = %02x", smartport.calc_checksum, smartport.pkt_checksum,SYSTEM_BUS.command_packet.command & 0x0f);',
            '''#ifdef IIGS_FAST_IWM_PROBE
        fast_iwm_probe_isr_deferred_events++;
#endif''',
            'data checksum ISR diagnostic',
        ),
        (
            '          Debug_printf("\\r\\nIgnoring bad data packet");',
            '''#ifdef IIGS_FAST_IWM_PROBE
          fast_iwm_probe_isr_deferred_events++;
#endif''',
            'ignored-packet ISR diagnostic',
        ),
    )
    for old, new, label in isr_replacements:
        ltext = replace_once(ltext, old, new, label)

    ltext = replace_once(
        ltext,
        '''#ifdef VERBOSE_IWM
    // timeout
    Debug_print("t");
#endif
''',
        '''#ifdef IIGS_FAST_IWM_PROBE
    fast_iwm_probe_isr_deferred_events++;
#endif
''',
        'SPI receive timeout ISR diagnostic',
    )

    btext = replace_once(
        btext,
        '#include "fnTcpClient.h"\n',
        '#include "fnTcpClient.h"\n#include <esp_heap_caps.h>\n',
        'provider TCP include',
    )
    btext = replace_once(
        btext,
        '''extern volatile bool fast_iwm_probe_waiting_for_ready_low;
extern volatile bool fast_iwm_probe_burst_started;
''',
        '''extern volatile bool fast_iwm_probe_waiting_for_ready_low;
extern volatile bool fast_iwm_probe_burst_started;
extern volatile uint32_t fast_iwm_probe_duplicate_ready_count;
extern volatile uint32_t fast_iwm_probe_isr_deferred_events;
static uint32_t fast_iwm_probe_isr_reported_events = 0;
''',
        'service burst externs',
    )

    btext = replace_once(
        btext,
        '''#ifdef IIGS_FAST_IWM_PROBE
  fast_iwm_provider_service();

  if (fast_iwm_probe_burst_started &&
''',
        '''#ifdef IIGS_FAST_IWM_PROBE
  fast_iwm_provider_service();

  const uint32_t d7_isr_events = fast_iwm_probe_isr_deferred_events;
  if (d7_isr_events != fast_iwm_probe_isr_reported_events)
  {
    fast_iwm_probe_isr_reported_events = d7_isr_events;
    Debug_printf("\\r\\nFASTIWM D7 ISR DEFERRED events=%lu duplicate_ready=%lu",
                 (unsigned long)d7_isr_events,
                 (unsigned long)fast_iwm_probe_duplicate_ready_count);
  }

  if (fast_iwm_probe_burst_started &&
''',
        'provider service entry',
    )

    btext = replace_once(
        btext,
        '''      Debug_printf("\\r\\nFASTIWM D4 PROVIDER BATCH DONE batch=%lu packets=%lu fifo=%u err=0",
                   (unsigned long)fast_iwm_provider_batches_sent,
                   (unsigned long)fast_iwm_provider_packets_sent,
                   (unsigned int)fast_iwm_provider_count);
      return;
''',
        '''      Debug_printf("\\r\\nFASTIWM D7 PROVIDER BATCH DONE batch=%lu packets=%lu fifo=%u err=0",
                   (unsigned long)fast_iwm_provider_batches_sent,
                   (unsigned long)fast_iwm_provider_packets_sent,
                   (unsigned int)fast_iwm_provider_count);
      if ((fast_iwm_provider_batches_sent & 0xffU) == 0)
      {
        Debug_printf("\\r\\nFASTIWM D7 HEAP batch=%lu free=%u min=%u largest=%u duplicate_ready=%lu isr_deferred=%lu",
                     (unsigned long)fast_iwm_provider_batches_sent,
                     (unsigned int)heap_caps_get_free_size(MALLOC_CAP_8BIT),
                     (unsigned int)heap_caps_get_minimum_free_size(MALLOC_CAP_8BIT),
                     (unsigned int)heap_caps_get_largest_free_block(MALLOC_CAP_8BIT),
                     (unsigned long)fast_iwm_probe_duplicate_ready_count,
                     (unsigned long)fast_iwm_probe_isr_deferred_events);
      }
      return;
''',
        'D4 completed-batch diagnostic',
    )

    btext = btext.replace('FASTIWM D4 ', 'FASTIWM D7 ')

    isr_start = ltext.index('void IRAM_ATTR phi_isr_handler')
    isr_end = ltext.index('inline void iwm_ll::iwm_extra_set', isr_start)
    isr_text = ltext[isr_start:isr_end]
    active_debug = [
        line for line in isr_text.splitlines()
        if line.lstrip().startswith(('Debug_print(', 'Debug_printf('))
    ]
    if active_debug:
        raise SystemExit(
            'P0.2D7 leaves active serial diagnostics in phi ISR: ' +
            '; '.join(active_debug)
        )

    required = (
        'fast_iwm_probe_duplicate_ready_count',
        'fast_iwm_probe_isr_deferred_events',
        'fast_iwm_probe_burst_started && (_phases == 0b1011)',
        'FASTIWM D7 ISR DEFERRED',
        'FASTIWM D7 HEAP',
        'heap_caps_get_minimum_free_size',
        'spi_device_acquire_bus(spifast, portMAX_DELAY)',
        'FASTIWM D7 ENDPOINT SET',
        'FASTIWM D7 PROVIDER BATCH ARMED',
        'FASTIWM D7 PROVIDER BATCH DONE',
    )
    joined = ltext + '\n' + btext
    for marker in required:
        if marker not in joined:
            raise SystemExit(f'Missing P0.2D7 firmware marker: {marker}')
    if 'FASTIWM D4 ' in btext:
        raise SystemExit('Obsolete D4 firmware diagnostic remains.')

    llcpp.write_text(ltext, encoding='utf-8', newline='\n')
    buscpp.write_text(btext, encoding='utf-8', newline='\n')
    print('Applied FujiNet P0.2D7 duplicate-READY/ISR guard overlay.')


if __name__ == '__main__':
    main()
