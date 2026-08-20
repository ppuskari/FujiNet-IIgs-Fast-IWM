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
        description='Apply P0.2B2 responder plus P0.2B5 serial diagnostics.'
    )
    parser.add_argument('--project-root', default='.')
    parser.add_argument('--firmware-root', required=True)
    args = parser.parse_args()

    project = Path(args.project_root).resolve()
    firmware = Path(args.firmware_root).resolve()

    b2_patch = project / 'tools' / 'patch_fujinet_fastiwm_p02b2.py'
    llcpp = firmware / 'lib' / 'bus' / 'iwm' / 'iwm_ll.cpp'
    buscpp = firmware / 'lib' / 'bus' / 'iwm' / 'iwm.cpp'

    if not b2_patch.is_file():
        raise SystemExit(f'P0.2B2 patch script missing: {b2_patch}')
    if not llcpp.is_file() or not buscpp.is_file():
        raise SystemExit(f'FujiNet IWM sources missing under: {firmware}')

    subprocess.run(
        [
            sys.executable,
            str(b2_patch),
            '--project-root',
            str(project),
            '--firmware-root',
            str(firmware),
        ],
        check=True,
    )

    ltext = llcpp.read_text(encoding='utf-8')
    btext = buscpp.read_text(encoding='utf-8')

    if 'FASTIWM_DIAG_P02B5' in ltext and 'FASTIWM TX START' in btext:
        print('FujiNet P0.2B5 diagnostic overlay already applied.')
        return

    state_old = '''volatile bool fast_iwm_probe_armed = false;
volatile bool fast_iwm_probe_request = false;
'''
    state_new = '''volatile bool fast_iwm_probe_armed = false;
volatile bool fast_iwm_probe_request = false;
volatile uint32_t fast_iwm_probe_arm_count = 0;
volatile uint32_t fast_iwm_probe_request_count = 0;
volatile uint8_t fast_iwm_probe_last_phase = 0;
volatile uint8_t fast_iwm_probe_diag_events = 0;
#define FASTIWM_DIAG_P02B5 1
'''
    ltext = replace_once(ltext, state_old, state_new, 'private probe state')

    arm_old = '''  if (_phases == 0b1110)
  {
    fast_iwm_probe_armed = true;
    fast_iwm_probe_request = false;
    smartport.iwm_ack_clr();
    return;
  }
'''
    arm_new = '''  if (_phases == 0b1110)
  {
    fast_iwm_probe_armed = true;
    fast_iwm_probe_request = false;
    fast_iwm_probe_arm_count++;
    fast_iwm_probe_last_phase = _phases;
    fast_iwm_probe_diag_events |= 0x01;
    smartport.iwm_ack_clr();
    return;
  }
'''
    ltext = replace_once(ltext, arm_old, arm_new, '1110 arm handler')

    req_old = '''  if (_phases == 0b1111) // P0.2B2 direct request
  {
    fast_iwm_probe_armed = false;
    fast_iwm_probe_request = true;
    return;
  }
'''
    req_new = '''  if (_phases == 0b1111) // P0.2B2 direct request
  {
    fast_iwm_probe_armed = false;
    fast_iwm_probe_request = true;
    fast_iwm_probe_request_count++;
    fast_iwm_probe_last_phase = _phases;
    fast_iwm_probe_diag_events |= 0x02;
    return;
  }
'''
    ltext = replace_once(ltext, req_old, req_new, '1111 request handler')

    extern_old = '''#ifdef IIGS_FAST_IWM_PROBE
extern volatile bool fast_iwm_probe_request;
#endif
'''
    extern_new = '''#ifdef IIGS_FAST_IWM_PROBE
extern volatile bool fast_iwm_probe_request;
extern volatile uint32_t fast_iwm_probe_arm_count;
extern volatile uint32_t fast_iwm_probe_request_count;
extern volatile uint8_t fast_iwm_probe_last_phase;
extern volatile uint8_t fast_iwm_probe_diag_events;
#endif
'''
    btext = replace_once(btext, extern_old, extern_new, 'iwm.cpp private externs')

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
  // P0.2B5 diagnostics are intentionally emitted from service context,
  // never from the GPIO ISR.  They may perturb timing slightly; this build
  // exists to prove which private phase events and TX stages actually occur.
  if (fast_iwm_probe_diag_events)
  {
    uint8_t events = fast_iwm_probe_diag_events;
    fast_iwm_probe_diag_events = 0;
    Debug_printf("\\r\\nFASTIWM DIAG events=%02x phase=%02x arm=%lu req=%lu",
                 events,
                 fast_iwm_probe_last_phase,
                 (unsigned long)fast_iwm_probe_arm_count,
                 (unsigned long)fast_iwm_probe_request_count);
  }

  if (fast_iwm_probe_request)
  {
    Debug_printf("\\r\\nFASTIWM TX START req=%lu",
                 (unsigned long)fast_iwm_probe_request_count);
    fast_iwm_probe_request = false;
    smartport.iwm_ack_set();
    smartport.iwm_send_fast_probe_spi();
    smartport.iwm_ack_clr();
    Debug_printf("\\r\\nFASTIWM TX DONE req=%lu",
                 (unsigned long)fast_iwm_probe_request_count);
    return;
  }
#endif
'''
    btext = replace_once(btext, service_old, service_new, 'service diagnostic block')

    required = [
        'FASTIWM_DIAG_P02B5',
        'fast_iwm_probe_arm_count',
        'fast_iwm_probe_request_count',
        'FASTIWM DIAG',
        'FASTIWM TX START',
        'FASTIWM TX DONE',
    ]
    joined = ltext + '\n' + btext
    for marker in required:
        if marker not in joined:
            raise SystemExit(f'Missing P0.2B5 diagnostic marker: {marker}')

    llcpp.write_text(ltext, encoding='utf-8', newline='\n')
    buscpp.write_text(btext, encoding='utf-8', newline='\n')

    print('Applied FujiNet P0.2B5 phase/TX serial diagnostic overlay.')
    print('Serial monitor target: 460800 baud (pinned platformio-sample.ini).')


if __name__ == '__main__':
    main()
