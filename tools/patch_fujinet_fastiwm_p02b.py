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
    cpp = root / 'lib' / 'bus' / 'iwm' / 'iwm_ll.cpp'

    if not hdr.is_file() or not cpp.is_file():
        raise SystemExit(f'FujiNet IWM sources not found under {root}')

    htext = hdr.read_text(encoding='utf-8')
    ctext = cpp.read_text(encoding='utf-8')

    if 'iwm_send_fast_probe_spi' in htext and 'fast_iwm_probe_armed' in ctext:
        print('FujiNet Fast-IWM P0.2B patch already applied.')
        return

    # --------------------------------------------------------------
    # Header: add a second TX device handle at 2 MHz and one private
    # probe-send entry point.  The normal 1 MHz SmartPort handle stays
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
    # CPP state and phase ISR.
    # 1110 is the private arm signature; PH0 is still the physical
    # SmartPort REQ line, so 1111 becomes the request edge.
    # --------------------------------------------------------------
    ctext = replace_once(
        ctext,
        'volatile int isrctr = 0;\n',
        'volatile int isrctr = 0;\n'
        '#ifdef IIGS_FAST_IWM_PROBE\n'
        'volatile bool fast_iwm_probe_armed = false;\n'
        '#endif\n',
        'global ISR state'
    )

    isr_anchor = '  _phases = IWM_PHASE_COMBINE();\n\n'
    isr_block = '''  _phases = IWM_PHASE_COMBINE();

#ifdef IIGS_FAST_IWM_PROBE
  // Private IIgs Fast-IWM P0.2B probe.
  //
  // PH3..PH0 = 1110 arms the responder and asserts ACK low.
  // Raising PH0 (REQ) produces 1111 and transmits a deterministic
  // test stream through a dedicated 2-MHz SPI device handle.
  // Ordinary SmartPort still uses the original 1-MHz TX handle.
  if (_phases == 0b1110)
  {
    fast_iwm_probe_armed = true;
    smartport.iwm_ack_clr();
    return;
  }

  if (fast_iwm_probe_armed && (_phases == 0b1111))
  {
    fast_iwm_probe_armed = false;
    smartport.iwm_ack_set();
    smartport.iwm_send_fast_probe_spi();
    smartport.iwm_ack_clr();
    return;
  }

  // Standard SmartPort reset signature: cancel a private probe and
  // release ACK so the normal bus can resume.
  if (_phases == 0b0101)
  {
    fast_iwm_probe_armed = false;
    smartport.iwm_ack_set();
  }
#endif

'''
    ctext = replace_once(ctext, isr_anchor, isr_block, 'phi ISR anchor')

    # --------------------------------------------------------------
    # Private deterministic TX routine.  The existing encoder turns
    # each logical IWM bit into two SPI bits.  Sending that same encoded
    # waveform at 2 MHz halves the cell period from 4 us to 2 us.
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

  enable_output();
  esp_err_t ret = spi_device_polling_transmit(spifast, &trans);
  disable_output();

  if (ret != ESP_OK)
    RETURN_ERROR_AS_TRUE();

  RETURN_SUCCESS_AS_FALSE();
}
#endif

'''
    if method_anchor not in ctext:
        raise SystemExit('Expected IWM_NEXT_BIT anchor not found.')
    ctext = ctext.replace(method_anchor, fast_method + method_anchor, 1)

    # --------------------------------------------------------------
    # setup_spi: add a second device on whichever TX bus normal
    # SmartPort uses.  No CS line is involved, just as with normal TX.
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
    ctext = replace_once(ctext, setup_anchor, setup_insert, 'setup_spi mutex anchor')

    # Final sanity checks.
    required = [
        'IIGS_FAST_IWM_PROBE',
        'spifast',
        'fast_iwm_probe_armed',
        'iwm_send_fast_probe_spi',
        '0b1110',
        '0b1111',
        'fastcfg.clock_speed_hz = 2 * MHZ',
    ]
    joined = htext + '\n' + ctext
    for item in required:
        if item not in joined:
            raise SystemExit(f'Missing required Fast-IWM marker: {item}')

    hdr.write_text(htext, encoding='utf-8', newline='\n')
    cpp.write_text(ctext, encoding='utf-8', newline='\n')

    print('Applied FujiNet Fast-IWM P0.2B private 2-us responder patch.')
    print(f'Firmware root: {root}')
    print('Build with -D IIGS_FAST_IWM_PROBE.')


if __name__ == '__main__':
    main()
