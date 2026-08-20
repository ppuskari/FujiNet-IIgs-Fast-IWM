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
        description='Apply P0.2B responder then add STATUS $AA arm + delayed 2us autosend.'
    )
    parser.add_argument('--project-root', default='.')
    parser.add_argument('--firmware-root', required=True)
    args = parser.parse_args()

    project = Path(args.project_root).resolve()
    firmware = Path(args.firmware_root).resolve()

    base_patch = project / 'tools' / 'patch_fujinet_fastiwm_p02b.py'
    llcpp = firmware / 'lib' / 'bus' / 'iwm' / 'iwm_ll.cpp'
    buscpp = firmware / 'lib' / 'bus' / 'iwm' / 'iwm.cpp'
    fujicpp = firmware / 'lib' / 'device' / 'iwm' / 'iwmFuji.cpp'

    for required in (base_patch, llcpp, buscpp, fujicpp):
        if not required.is_file():
            raise SystemExit(f'Missing required file: {required}')

    subprocess.run(
        [sys.executable, str(base_patch), '--firmware-root', str(firmware)],
        check=True,
    )

    ltext = llcpp.read_text(encoding='utf-8')
    btext = buscpp.read_text(encoding='utf-8')
    ftext = fujicpp.read_text(encoding='utf-8')

    if 'P0.2B6 STATUS-AA autosend' in btext:
        print('FujiNet P0.2B6 STATUS-arm patch already applied.')
        return

    ltext = replace_once(
        ltext,
        'volatile bool fast_iwm_probe_request = false;\n',
        'volatile bool fast_iwm_probe_request = false;\n'
        'volatile bool fast_iwm_probe_autosend_pending = false;\n'
        'volatile uint32_t fast_iwm_probe_autosend_due_ms = 0;\n',
        'Fast-IWM global request state',
    )

    btext = replace_once(
        btext,
        'extern volatile bool fast_iwm_probe_request;\n',
        'extern volatile bool fast_iwm_probe_request;\n'
        'extern volatile bool fast_iwm_probe_autosend_pending;\n'
        'extern volatile uint32_t fast_iwm_probe_autosend_due_ms;\n',
        'iwm.cpp Fast-IWM extern block',
    )

    service_old = '''#ifdef IIGS_FAST_IWM_PROBE
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
    service_new = '''#ifdef IIGS_FAST_IWM_PROBE
  // P0.2B6 STATUS-AA autosend.
  // A completely ordinary SmartPort STATUS $AA request arms one packet.
  // The normal 4-us status response finishes first.  A short delay then
  // gives the IIgs ROM time to return to the application and the host time
  // to enter its direct IWM read loop before the 2-us packet is driven.
  if (fast_iwm_probe_autosend_pending)
  {
    uint32_t now = fnSystem.millis();
    if ((int32_t)(now - fast_iwm_probe_autosend_due_ms) >= 0)
    {
      fast_iwm_probe_autosend_pending = false;
      Debug_printf("\\r\\nFASTIWM B6 AUTO TX START");
      smartport.iwm_send_fast_probe_spi();
      Debug_printf("\\r\\nFASTIWM B6 AUTO TX DONE");
      return;
    }
  }

  // Keep the earlier direct-request latch available for diagnostics, but
  // P0.2B6 no longer depends on undocumented 1110/1111 phase signatures.
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
    btext = replace_once(btext, service_old, service_new, 'systemBus Fast-IWM service block')

    include_anchor = '#include "fnSystem.h"\n'
    if include_anchor not in ftext:
        raise SystemExit('Expected fnSystem include not found in iwmFuji.cpp.')
    ftext = ftext.replace(
        include_anchor,
        include_anchor +
        '#ifdef IIGS_FAST_IWM_PROBE\n'
        'extern volatile bool fast_iwm_probe_autosend_pending;\n'
        'extern volatile uint32_t fast_iwm_probe_autosend_due_ms;\n'
        '#endif\n',
        1,
    )

    status_old = '        { 0xAA, [this](const iwm_decoded_cmd_t &cmd)                               { this->iwm_hello_world(); }},\n'
    status_new = '''        { 0xAA, [this](const iwm_decoded_cmd_t &cmd)                               {
#ifdef IIGS_FAST_IWM_PROBE
            // P0.2B6: use a legal, known-good SmartPort STATUS transaction
            // as the one-shot negotiation.  Preserve the normal HELLO WORLD
            // response so the host call completes through stock ROM firmware.
            fast_iwm_probe_autosend_pending = true;
            fast_iwm_probe_autosend_due_ms = fnSystem.millis() + 20;
            Debug_printf("\\r\\nFASTIWM B6 ARMED by STATUS $AA; autosend in 20 ms");
#endif
            this->iwm_hello_world();
        }},
'''
    ftext = replace_once(ftext, status_old, status_new, 'STATUS $AA handler')

    required_markers = (
        'fast_iwm_probe_autosend_pending',
        'fast_iwm_probe_autosend_due_ms',
        'FASTIWM B6 ARMED by STATUS $AA',
        'FASTIWM B6 AUTO TX START',
        'FASTIWM B6 AUTO TX DONE',
        'fnSystem.millis() + 20',
    )
    joined = ltext + '\n' + btext + '\n' + ftext
    for marker in required_markers:
        if marker not in joined:
            raise SystemExit(f'Missing required B6 marker: {marker}')

    llcpp.write_text(ltext, encoding='utf-8', newline='\n')
    buscpp.write_text(btext, encoding='utf-8', newline='\n')
    fujicpp.write_text(ftext, encoding='utf-8', newline='\n')

    print('Applied FujiNet P0.2B6 STATUS $AA arm + delayed 2-us autosend patch.')
    print('Normal SmartPort remains upstream 1 MHz / 4-us timing.')
    print('The private 2-MHz TX starts 20 ms after STATUS $AA arms it.')


if __name__ == '__main__':
    main()
