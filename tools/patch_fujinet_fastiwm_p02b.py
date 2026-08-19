from pathlib import Path
import argparse

MARKER = 'IIGS_FAST_IWM_PROBE'


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f'Expected {label} pattern not found.')
    return text.replace(old, new, 1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Apply FujiNet Fast-IWM P0.2B responder patch.'
    )
    parser.add_argument(
        '--firmware-root',
        default='work/fujinet-firmware',
        help='Path to pinned fujinet-firmware checkout.'
    )
    args = parser.parse_args()

    root = Path(args.firmware_root).resolve()
    hdr = root / 'lib' / 'bus' / 'iwm' / 'iwm_ll.h'
    llcpp = root / 'lib' / 'bus' / 'iwm' / 'iwm_ll.cpp'
    buscpp = root / 'lib' / 'bus' / 'iwm' / 'iwm.cpp'

    if not hdr.is_file() or not llcpp.is_file() or not buscpp.is_file():
        raise SystemExit(f'FujiNet IWM sources not found under {root}')

    htext = hdr.read_text(encoding='utf-8')
    ltext = llcpp.read_text(encoding='utf-8')
    btext = buscpp.read_text(encoding='utf-8')

    if (
        'iwm_send_fast_probe_spi' in htext
        and 'fast_iwm_probe_request' in ltext
        and 'fast_iwm_probe_request' in btext
    ):
        print('FujiNet Fast-IWM P0.2B patch already applied.')
        return

    # --------------------------------------------------------------
    # Header: add a second TX device handle at 2 MHz and one private
    # probe-send entry point. The normal 1 MHz SmartPort handle stays
    # untouched, so ordinary FujiNet remains 4-us compatible.
    # --------------------------------------------------------------
    htext = replace_once(
        htext,
        '  spi_device_handle_t spi;\n',
        '  spi_device_handle_t spi;\n'
        '#ifdef IIGS_FAST_IWM_PROBE\n'
        '  spi_device_handle_t spifast;\n'
        '#endif\n',
        'iwm_sp_ll SPI handle'
    )

    htext = replace_once(
        htext,
        '  error_is_true iwm_send_packet_spi();\n',
        '  error_is_true iwm_send_packet_spi();\n'
        '#ifdef IIGS_FAST_IWM_PROBE\n'
        '  error_is_true iwm_send_fast_probe_spi();\n'
        '#endif\n',
        'iwm_send_packet_spi declaration'
    )

    # --------------------------------------------------------------
    # Low-level state and phase ISR.
    #
    # IMPORTANT: the GPIO ISR only records the private request and
    # manipulates the lightweight ACK GPIO. The blocking ESP-IDF SPI
    # transmit is deliberately deferred to systemBus::service().
    # --------------------------------------------------------------
    ltext = replace_once(
        ltext,
        'volatile int isrctr = 0;\n',
        'volatile int isrctr = 0;\n'
        '#ifdef IIGS_FAST_IWM_PROBE\n'
        'volatile bool fast_iwm_probe_armed = false;\n'
        'volatile bool fast_iwm_probe_request = false;\n'
        '#endif\n',
        'global ISR state'
    )

    isr_anchor = '  _phases = IWM_PHASE_COMBINE();\n\n'
    isr_block = '''  _phases = IWM_PHASE_COMBINE();

#ifdef IIGS_FAST_IWM_PROBE
  // Private IIgs Fast-IWM P0.2B probe.
  //
  // PH3..PH0 = 1110 arms the responder and asserts ACK low.
  // Raising PH0 (REQ) produces 1111 and queues one deterministic
  // 2-us transmit request. The actual SPI transfer is NOT performed
  // inside this GPIO ISR; systemBus::service() performs it.
  if (_phases == 0b1110)
  {
    fast_iwm_probe_armed = true;
    fast_iwm_probe_request = false;
    smartport.iwm_ack_clr();
    return;
  }

  if (fast_iwm_probe_armed && (_phases == 0b1111))
  {
    fast_iwm_probe_armed = false;
    fast_iwm_probe_request = true;
    return;
  }

  // Standard SmartPort reset signature: cancel a private probe and
  // release ACK so the normal bus can resume.
  if (_phases == 0b0101)
  {
    fast_iwm_probe_armed = false;
    fast_iwm_probe_request = false;
    smartport.iwm_ack_set();
  }
#endif

'''
    ltext = replace_once(ltext, isr_anchor, isr_block, 'phi ISR anchor')

    # --------------------------------------------------------------
    # Private deterministic TX routine.
    #
    # The existing encoder turns each logical IWM bit into two SPI bits.
    # Sending the same encoded waveform at 2 MHz halves the nominal cell
    # period from 4 us to 2 us. This runs in normal service context, not
    # the GPIO ISR.
    # --------------------------------------------------------------
    method_anchor = '#define IWM_NEXT_BIT()'
    fast_method = r'''#ifdef IIGS_FAST_IWM_PROBE
error_is_true IRAM_ATTR iwm_sp_ll::iwm_send_fast_probe_spi()
{
  // 16 sync bytes + marker + 512 deterministic bytes + guard.
  // All logical bytes have bit 7 set so the IWM read-data latch can
  // present them directly to the host's tight polling loop.
  memset(packet_buffer, 0, sizeof(packet_buffer));

  int p = 0;
  for (int i = 0; i < 16; i++)
    packet_buffer[p++] = 0xff;

  packet_buffer[p++] = 0xd5;
  packet_buffer[p++] = 0xaa;
  packet_buffer[p++] = 0x96;

  for (int i = 0; i < 512; i++)
    packet_buffer[p++] = 0x80 | (i & 0x7f);

  // Guard bytes absorb the existing encoder's trailing-bit behavior.
  for (int i = 0; i < 4; i++)
    packet_buffer[p++] = 0xff;

  packet_buffer[p] = 0x00;

  set_output_to_spi();
  int spi_len = encode_spi_packet();

  spi_transaction_t trans;
  memset(&trans, 0, sizeof(spi_transaction_t));
  trans.tx_buffer = spi_buffer;
  trans.length = spi_len * 8;

  // Mirror the timing discipline of the normal SmartPort transmitter:
  // no unrelated interrupt jitter while the physical packet is on wire.
  portDISABLE_INTERRUPTS();
  enable_output();
  esp_err_t ret = spi_device_polling_transmit(spifast, &trans);
  disable_output();
  portENABLE_INTERRUPTS();

  if (ret != ESP_OK)
    RETURN_ERROR_AS_TRUE();

  RETURN_SUCCESS_AS_FALSE();
}
#endif

'''
    if method_anchor not in ltext:
        raise SystemExit('Expected IWM_NEXT_BIT anchor not found.')
    ltext = ltext.replace(method_anchor, fast_method + method_anchor, 1)

    # --------------------------------------------------------------
    # setup_spi: add a second device on whichever TX bus normal
    # SmartPort uses. No CS line is involved, just as with normal TX.
    # --------------------------------------------------------------
    setup_anchor = '''  if (smartport.spiMutex == NULL)
  {
    smartport.spiMutex = xSemaphoreCreateMutex();
  }
'''
    setup_insert = '''#ifdef IIGS_FAST_IWM_PROBE
  // Dedicated 2-MHz transmitter for the private IIgs fast probe.
  // The normal SmartPort device remains configured at 1 MHz.
  spi_device_interface_config_t fastcfg = devcfg;
  fastcfg.clock_speed_hz = 2 * MHZ;

  if (!fnSystem.spishared())
  {
    ret = spi_bus_add_device(VSPI_HOST, &fastcfg, &spifast);
    assert(ret == ESP_OK);
  }
  else
  {
    ret = spi_bus_add_device(HSPI_HOST, &fastcfg, &spifast);
    assert(ret == ESP_OK);
  }
#endif

  if (smartport.spiMutex == NULL)
  {
    smartport.spiMutex = xSemaphoreCreateMutex();
  }
'''
    ltext = replace_once(ltext, setup_anchor, setup_insert, 'setup_spi mutex anchor')

    # --------------------------------------------------------------
    # Normal system service context: service one queued private packet
    # before ordinary SmartPort/DiskII work. This is intentionally a
    # one-request latch; the IIgs drops PH0 back to 1110 to re-arm.
    # --------------------------------------------------------------
    include_anchor = '#include "compat_esp.h" // empty IRAM_ATTR macro for FujiNet-PC\n'
    include_insert = '''#include "compat_esp.h" // empty IRAM_ATTR macro for FujiNet-PC

#ifdef IIGS_FAST_IWM_PROBE
extern volatile bool fast_iwm_probe_request;
#endif
'''
    btext = replace_once(btext, include_anchor, include_insert, 'iwm.cpp include anchor')

    service_anchor = '''void IRAM_ATTR systemBus::service()
{
#ifndef DEV_RELAY_SLIP
'''
    service_insert = '''void IRAM_ATTR systemBus::service()
{
#ifdef IIGS_FAST_IWM_PROBE
  // The GPIO phase ISR only latches this request. Perform the blocking
  // SPI transfer here in normal bus-service context.
  if (fast_iwm_probe_request)
  {
    fast_iwm_probe_request = false;
    smartport.iwm_ack_set();
    smartport.iwm_send_fast_probe_spi();
    smartport.iwm_ack_clr();
    return;
  }
#endif

#ifndef DEV_RELAY_SLIP
'''
    btext = replace_once(btext, service_anchor, service_insert, 'systemBus::service anchor')

    # Final sanity checks.
    required = [
        'IIGS_FAST_IWM_PROBE',
        'spifast',
        'fast_iwm_probe_armed',
        'fast_iwm_probe_request',
        'iwm_send_fast_probe_spi',
        '0b1110',
        '0b1111',
        'fastcfg.clock_speed_hz = 2 * MHZ',
        'if (fast_iwm_probe_request)',
    ]
    joined = htext + '\n' + ltext + '\n' + btext
    for item in required:
        if item not in joined:
            raise SystemExit(f'Missing required Fast-IWM marker: {item}')

    # Safety assertion: no blocking fast SPI call may remain in the
    # private phase-ISR branch.
    isr_start = ltext.index('void IRAM_ATTR phi_isr_handler')
    isr_end = ltext.index('inline void iwm_ll::iwm_extra_set', isr_start)
    isr_text = ltext[isr_start:isr_end]
    if 'iwm_send_fast_probe_spi()' in isr_text:
        raise SystemExit('Unsafe P0.2B patch: fast SPI transmit still appears in GPIO ISR.')

    hdr.write_text(htext, encoding='utf-8', newline='\n')
    llcpp.write_text(ltext, encoding='utf-8', newline='\n')
    buscpp.write_text(btext, encoding='utf-8', newline='\n')

    print('Applied FujiNet Fast-IWM P0.2B production-safe responder patch.')
    print(f'Firmware root: {root}')
    print('Normal SmartPort remains 1 MHz; private responder TX is 2 MHz.')
    print('Fast SPI transmit runs in systemBus::service(), not the GPIO ISR.')
    print('Build with -D IIGS_FAST_IWM_PROBE.')


if __name__ == '__main__':
    main()
