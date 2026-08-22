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
            'Apply P0.2C10, add a service-context phase poll, and retain a '
            'three-second proven delayed-send fallback for the routed host.'
        )
    )
    parser.add_argument('--project-root', default='.')
    parser.add_argument('--firmware-root', required=True)
    args = parser.parse_args()

    project = Path(args.project_root).resolve()
    root = Path(args.firmware_root).resolve()
    base = project / 'tools' / 'patch_fujinet_fastiwm_p02c10_hold.py'
    llcpp = root / 'lib' / 'bus' / 'iwm' / 'iwm_ll.cpp'
    buscpp = root / 'lib' / 'bus' / 'iwm' / 'iwm.cpp'
    if not base.is_file() or not llcpp.is_file() or not buscpp.is_file():
        raise SystemExit('Missing P0.2C10 firmware transform or IWM sources.')

    ltext = llcpp.read_text(encoding='utf-8')
    btext = buscpp.read_text(encoding='utf-8')
    if 'FASTIWM C11 READY ARMED' in btext:
        print('FujiNet P0.2C11 routed-host overlay already applied.')
        return
    if 'FASTIWM C10 READY ARMED' not in btext:
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
    if 'FASTIWM C10 READY ARMED' not in btext:
        raise SystemExit('P0.2C10 firmware transform did not apply.')

    btext = replace_once(
        btext,
        '''static uint32_t fast_iwm_probe_tx_count = 0;
static unsigned long fast_iwm_probe_arm_deadline = 0;
''',
        '''static uint32_t fast_iwm_probe_tx_count = 0;
static unsigned long fast_iwm_probe_arm_deadline = 0;
static unsigned long fast_iwm_probe_fallback_due = 0;
''',
        'P0.2C10 deadline state',
    )

    btext = replace_once(
        btext,
        '''      fast_iwm_probe_arm_deadline = fnSystem.millis() + 5000UL;
''',
        '''      fast_iwm_probe_arm_deadline = fnSystem.millis() + 10000UL;
      fast_iwm_probe_fallback_due = fnSystem.millis() + 3000UL;
''',
        'P0.2C10 arm deadline',
    )

    service_anchor = '''#ifdef IIGS_FAST_IWM_PROBE
  if (fast_iwm_probe_armed && fast_iwm_probe_arm_deadline &&
'''
    service_insert = '''#ifdef IIGS_FAST_IWM_PROBE
  // P0.2C11 normally triggers from the GPIO phase ISR. Polling the held
  // vector here also catches a missed edge. If neither path observes READY,
  // the proven delayed-send mechanism fires after three seconds, by which
  // time the routed host is already polling the 2-us Read Data register.
  if (fast_iwm_probe_armed)
  {
    const uint8_t fast_phase = smartport.iwm_phase_vector();
    const bool ready_polled = (fast_phase == 0b1011);
    const bool fallback_due = fast_iwm_probe_fallback_due &&
      (static_cast<int32_t>(fnSystem.millis() - fast_iwm_probe_fallback_due) >= 0);
    if (ready_polled || fallback_due)
    {
      fast_iwm_probe_armed = false;
      fast_iwm_probe_arm_deadline = 0;
      fast_iwm_probe_fallback_due = 0;
      fast_iwm_probe_request = true;
      fast_iwm_probe_req_count++;
      Debug_printf(ready_polled
        ? "\\r\\nFASTIWM C11 READY POLLED phase=%02x"
        : "\\r\\nFASTIWM C11 READY FALLBACK phase=%02x",
        (unsigned int)fast_phase);
    }
  }

  if (fast_iwm_probe_armed && fast_iwm_probe_arm_deadline &&
'''
    btext = replace_once(
        btext,
        service_anchor,
        service_insert,
        'P0.2C10 service deadline entry',
    )

    btext = replace_once(
        btext,
        '''    fast_iwm_probe_arm_deadline = 0;
    Debug_printf("\\r\\nFASTIWM C10 ARM EXPIRED held_resets=%lu",
                 (unsigned long)fast_iwm_probe_reset_hold_count);
''',
        '''    fast_iwm_probe_arm_deadline = 0;
    fast_iwm_probe_fallback_due = 0;
    Debug_printf("\\r\\nFASTIWM C11 ARM EXPIRED phase=%02x held_resets=%lu",
                 (unsigned int)smartport.iwm_phase_vector(),
                 (unsigned long)fast_iwm_probe_reset_hold_count);
''',
        'P0.2C10 expiry diagnostic',
    )

    btext = btext.replace('FASTIWM C10 READY ARMED', 'FASTIWM C11 READY ARMED')
    btext = btext.replace('FASTIWM C10 READY TRIGGER', 'FASTIWM C11 READY TRIGGER')

    required = (
        'FASTIWM C11 READY ARMED',
        'FASTIWM C11 READY TRIGGER',
        'FASTIWM C11 READY POLLED',
        'FASTIWM C11 READY FALLBACK',
        'FASTIWM C11 ARM EXPIRED',
        'fast_iwm_probe_fallback_due',
        'fnSystem.millis() + 3000UL',
        'fnSystem.millis() + 10000UL',
        'fast_phase == 0b1011',
        'iwm_send_fast_probe_spi()',
    )
    joined = ltext + '\n' + btext
    for marker in required:
        if marker not in joined:
            raise SystemExit(f'Missing P0.2C11 firmware marker: {marker}')

    llcpp.write_text(ltext, encoding='utf-8', newline='\n')
    buscpp.write_text(btext, encoding='utf-8', newline='\n')
    print('Applied FujiNet P0.2C11 routed-host READY poll/fallback overlay.')


if __name__ == '__main__':
    main()
