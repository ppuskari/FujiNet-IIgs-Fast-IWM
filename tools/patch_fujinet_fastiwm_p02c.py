from pathlib import Path
import argparse
import re
import subprocess
import sys

MAGIC_BLOCK = 0x7FA55A


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f'Expected {label} pattern not found.')
    return text.replace(old, new, 1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Apply P0.2B physical TX support, then convert trigger to SmartPort-armed P0.2C.'
    )
    parser.add_argument('--project-root', default='.')
    parser.add_argument('--firmware-root', required=True)
    args = parser.parse_args()

    project = Path(args.project_root).resolve()
    root = Path(args.firmware_root).resolve()
    base_patch = project / 'tools' / 'patch_fujinet_fastiwm_p02b.py'
    llcpp = root / 'lib' / 'bus' / 'iwm' / 'iwm_ll.cpp'
    buscpp = root / 'lib' / 'bus' / 'iwm' / 'iwm.cpp'

    if not base_patch.is_file():
        raise SystemExit(f'P0.2B base patch missing: {base_patch}')
    if not llcpp.is_file() or not buscpp.is_file():
        raise SystemExit(f'FujiNet IWM sources not found below {root}')

    subprocess.run(
        [sys.executable, str(base_patch), '--firmware-root', str(root)],
        check=True,
    )

    ltext = llcpp.read_text(encoding='utf-8')
    btext = buscpp.read_text(encoding='utf-8')

    if 'FASTIWM ARM block=7fa55a' in btext:
        print('FujiNet P0.2C SmartPort-arm patch already applied.')
        return

    # Add a request counter beside the B2 latches. The ISR only increments
    # it; all printing remains in normal bus-service context.
    ltext = replace_once(
        ltext,
        'volatile bool fast_iwm_probe_armed = false;\n'
        'volatile bool fast_iwm_probe_request = false;\n',
        'volatile bool fast_iwm_probe_armed = false;\n'
        'volatile bool fast_iwm_probe_request = false;\n'
        'volatile uint32_t fast_iwm_probe_req_count = 0;\n',
        'B2 fast-IWM latch declarations',
    )

    # Replace the raw 1110/1111 private ISR protocol. Upstream FujiNet
    # identifies 1010/1011 as normal SmartPort enable states, and B5 proved
    # normal SmartPort activity reaches this hardware while 1110/1111 did not.
    pattern = re.compile(
        r'#ifdef IIGS_FAST_IWM_PROBE\n'
        r'  // Private IIgs Fast-IWM P0\.2B probe\..*?'
        r'#endif\n\n',
        re.S,
    )
    replacement = '''#ifdef IIGS_FAST_IWM_PROBE
  // P0.2C: normal SmartPort traffic arms the one-shot responder.
  // Once armed, intercept the proven SmartPort enable/REQ state 1011
  // before the normal command-packet receive path can consume it.
  if (fast_iwm_probe_armed && (_phases == 0b1011))
  {
    fast_iwm_probe_armed = false;
    fast_iwm_probe_request = true;
    fast_iwm_probe_req_count++;
    return;
  }

  // Standard SmartPort reset cancels an outstanding experiment.
  if (_phases == 0b0101)
  {
    fast_iwm_probe_armed = false;
    fast_iwm_probe_request = false;
    smartport.iwm_ack_set();
  }
#endif

'''
    ltext, count = pattern.subn(replacement, ltext, count=1)
    if count != 1:
        raise SystemExit('Unable to replace P0.2B private phase ISR block.')

    # iwm.cpp needs both latches and the ISR request counter.
    btext = replace_once(
        btext,
        '#ifdef IIGS_FAST_IWM_PROBE\n'
        'extern volatile bool fast_iwm_probe_request;\n'
        '#endif\n',
        '#ifdef IIGS_FAST_IWM_PROBE\n'
        'extern volatile bool fast_iwm_probe_armed;\n'
        'extern volatile bool fast_iwm_probe_request;\n'
        'extern volatile uint32_t fast_iwm_probe_req_count;\n'
        'static uint32_t fast_iwm_probe_arm_count = 0;\n'
        'static uint32_t fast_iwm_probe_tx_count = 0;\n'
        '#endif\n',
        'B2 iwm.cpp extern block',
    )

    # Arm on one impossible-for-this-test reserved standard READBLOCK. This
    # happens after the ordinary 4-us command packet has been decoded and the
    # target FujiNet device is known, but before any media read occurs.
    process_anchor = '''void systemBus::iwm_process(const iwm_decoded_cmd_t &cmd)
{
  fnLedManager.set(LED_BUS, true);

'''
    process_insert = f'''void systemBus::iwm_process(const iwm_decoded_cmd_t &cmd)
{{
  fnLedManager.set(LED_BUS, true);

#ifdef IIGS_FAST_IWM_PROBE
  if ((cmd.frame.sp_command == SP_CMD_READBLOCK) &&
      (cmd.frame.block_rw.num == 0x{MAGIC_BLOCK:06x}))
  {{
    fast_iwm_probe_armed = true;
    fast_iwm_probe_request = false;
    fast_iwm_probe_arm_count++;

    Debug_printf("\\r\\nFASTIWM ARM block={MAGIC_BLOCK:06x} count=%lu",
                 (unsigned long)fast_iwm_probe_arm_count);

    // Return a normal 512-byte 4-us block so the ROM SmartPort call that
    // performed negotiation completes exactly like the proven B3 baseline.
    std::array<uint8_t, 512> fast_arm_reply;
    fast_arm_reply.fill(0xa5);
    transaction_accept(TRANS_STATE::NO_GET);
    transaction_send(fast_arm_reply.data(), fast_arm_reply.size());
    goto done;
  }}
#endif

'''
    btext = replace_once(btext, process_anchor, process_insert, 'iwm_process entry')

    # Replace B2 service action with explicit diagnostics and leave ACK high-Z.
    old_service = '''#ifdef IIGS_FAST_IWM_PROBE
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
'''
    new_service = '''#ifdef IIGS_FAST_IWM_PROBE
  if (fast_iwm_probe_request)
  {
    fast_iwm_probe_request = false;
    fast_iwm_probe_tx_count++;

    Debug_printf("\\r\\nFASTIWM REQ count=%lu phase=%02x",
                 (unsigned long)fast_iwm_probe_req_count,
                 (unsigned int)smartport.iwm_phase_vector());
    Debug_printf("\\r\\nFASTIWM TX START count=%lu",
                 (unsigned long)fast_iwm_probe_tx_count);

    // Keep ACK released; this private packet is triggered by the armed
    // normal-enable transition and does not use ROM SmartPort receive.
    smartport.iwm_ack_set();
    error_is_true fast_err = smartport.iwm_send_fast_probe_spi();
    smartport.iwm_ack_set();

    Debug_printf("\\r\\nFASTIWM TX DONE count=%lu err=%d",
                 (unsigned long)fast_iwm_probe_tx_count,
                 fast_err ? 1 : 0);
    return;
  }
#endif
'''
    btext = replace_once(btext, old_service, new_service, 'B2 fast service block')

    required = (
        '0b1011',
        'FASTIWM ARM block=7fa55a',
        'FASTIWM REQ count=',
        'FASTIWM TX START',
        'FASTIWM TX DONE',
        'fast_iwm_probe_req_count',
        'fastcfg.clock_speed_hz = 2 * MHZ',
        'iwm_send_fast_probe_spi',
    )
    joined = ltext + '\n' + btext
    for item in required:
        if item not in joined:
            raise SystemExit(f'Missing P0.2C marker: {item}')

    if 'if (_phases == 0b1110)' in ltext:
        raise SystemExit('Old raw 1110 arm trigger remains after P0.2C patch.')

    # The blocking fast transmit must remain outside phi_isr_handler.
    isr_start = ltext.index('void IRAM_ATTR phi_isr_handler')
    isr_end = ltext.index('inline void iwm_ll::iwm_extra_set', isr_start)
    if 'iwm_send_fast_probe_spi()' in ltext[isr_start:isr_end]:
        raise SystemExit('Unsafe P0.2C patch: blocking fast TX appears in GPIO ISR.')

    llcpp.write_text(ltext, encoding='utf-8', newline='\n')
    buscpp.write_text(btext, encoding='utf-8', newline='\n')

    print('Applied FujiNet P0.2C SmartPort-arm / 1011 fast-trigger patch.')
    print(f'Magic arm READBLOCK: ${MAGIC_BLOCK:06X}')
    print('Normal SmartPort remains 1 MHz; private TX remains 2 MHz.')


if __name__ == '__main__':
    main()
