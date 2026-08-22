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
            'Apply the proven P0.2C5 transmitter, then replace delayed '
            'autosend with a host-ready 1010/1011 handshake.'
        )
    )
    parser.add_argument('--project-root', default='.')
    parser.add_argument('--firmware-root', required=True)
    args = parser.parse_args()

    project = Path(args.project_root).resolve()
    root = Path(args.firmware_root).resolve()
    base = project / 'tools' / 'patch_fujinet_fastiwm_p02c5_buslock.py'
    llcpp = root / 'lib' / 'bus' / 'iwm' / 'iwm_ll.cpp'
    buscpp = root / 'lib' / 'bus' / 'iwm' / 'iwm.cpp'

    if not base.is_file():
        raise SystemExit(f'Missing P0.2C5 firmware transform: {base}')
    if not llcpp.is_file() or not buscpp.is_file():
        raise SystemExit(f'FujiNet IWM sources not found below {root}')

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
    if 'FASTIWM C9 READY ARMED' in btext:
        print('FujiNet P0.2C9 host-ready overlay already applied.')
        return

    btext = replace_once(
        btext,
        '''static uint32_t fast_iwm_probe_arm_count = 0;
static uint32_t fast_iwm_probe_tx_count = 0;
static bool fast_iwm_probe_autosend_pending = false;
static unsigned long fast_iwm_probe_autosend_due = 0;
static uint32_t fast_iwm_probe_autosend_count = 0;
''',
        '''static uint32_t fast_iwm_probe_arm_count = 0;
static uint32_t fast_iwm_probe_tx_count = 0;
''',
        'P0.2C5 autosend state',
    )

    old_arm = '''      // P0.2C4: negotiation is complete.  Do not arm the GPIO ISR path;
      // schedule one private packet from normal service context instead.
      fast_iwm_probe_armed = false;
      fast_iwm_probe_reset_grace = 0;
      fast_iwm_probe_request = false;
      fast_iwm_probe_arm_count++;
      fast_iwm_probe_autosend_pending = true;
      fast_iwm_probe_autosend_due = fnSystem.millis() + 50UL;

      Debug_printf("\\r\\nFASTIWM ARM block=7fa55a count=%lu raw=%02x %02x %02x",
                   (unsigned long)fast_iwm_probe_arm_count,
                   (unsigned int)cmd.frame.block_rw.num.bytes[0],
                   (unsigned int)cmd.frame.block_rw.num.bytes[1],
                   (unsigned int)cmd.frame.block_rw.num.bytes[2]);
      Debug_printf("\\r\\nFASTIWM C4 AUTOSEND scheduled due=%lu now=%lu",
                   fast_iwm_probe_autosend_due,
                   fnSystem.millis());
'''
    new_arm = '''      // P0.2C9: keep the one-shot armed after the ordinary 4-us arm
      // reply. The host first prepares its IWM receive mode, establishes
      // phase state 1010, and raises PH0 to 1011 only when polling is live.
      fast_iwm_probe_armed = true;
      fast_iwm_probe_reset_grace = 1;
      fast_iwm_probe_request = false;
      fast_iwm_probe_arm_count++;

      Debug_printf("\\r\\nFASTIWM ARM block=7fa55a count=%lu raw=%02x %02x %02x",
                   (unsigned long)fast_iwm_probe_arm_count,
                   (unsigned int)cmd.frame.block_rw.num.bytes[0],
                   (unsigned int)cmd.frame.block_rw.num.bytes[1],
                   (unsigned int)cmd.frame.block_rw.num.bytes[2]);
      Debug_printf("\\r\\nFASTIWM C9 READY ARMED count=%lu trigger=1011",
                   (unsigned long)fast_iwm_probe_arm_count);
'''
    btext = replace_once(btext, old_arm, new_arm, 'P0.2C5 magic arm state')

    old_autosend = '''  if (fast_iwm_probe_autosend_pending &&
      (static_cast<int32_t>(fnSystem.millis() - fast_iwm_probe_autosend_due) >= 0))
  {
    fast_iwm_probe_autosend_pending = false;
    fast_iwm_probe_autosend_count++;
    fast_iwm_probe_tx_count++;

    Debug_printf("\\r\\nFASTIWM C4 AUTO TX START count=%lu now=%lu",
                 (unsigned long)fast_iwm_probe_autosend_count,
                 fnSystem.millis());

    smartport.iwm_ack_set();
    error_is_true fast_err = smartport.iwm_send_fast_probe_spi();
    smartport.iwm_ack_set();

    Debug_printf("\\r\\nFASTIWM C4 AUTO TX DONE count=%lu err=%d now=%lu",
                 (unsigned long)fast_iwm_probe_autosend_count,
                 fast_err ? 1 : 0,
                 fnSystem.millis());
    return;
  }

'''
    btext = replace_once(
        btext,
        old_autosend,
        '',
        'P0.2C5 delayed autosend service path',
    )

    btext = replace_once(
        btext,
        '''    Debug_printf("\\r\\nFASTIWM REQ count=%lu phase=%02x held_resets=%lu",
                 (unsigned long)fast_iwm_probe_req_count,
                 (unsigned int)smartport.iwm_phase_vector(),
                 (unsigned long)fast_iwm_probe_reset_hold_count);
''',
        '''    Debug_printf("\\r\\nFASTIWM C9 READY TRIGGER count=%lu phase=%02x held_resets=%lu",
                 (unsigned long)fast_iwm_probe_req_count,
                 (unsigned int)smartport.iwm_phase_vector(),
                 (unsigned long)fast_iwm_probe_reset_hold_count);
''',
        'P0.2C5 request diagnostic',
    )

    required = (
        'FASTIWM C9 READY ARMED',
        'FASTIWM C9 READY TRIGGER',
        'fast_iwm_probe_armed = true',
        'fast_iwm_probe_reset_grace = 1',
        'FASTIWM TX START',
        'FASTIWM TX DONE',
        'FASTIWM C5 BUS ACQUIRE START',
        'spi_device_acquire_bus(spifast, portMAX_DELAY)',
        'fastcfg.clock_speed_hz = 2 * MHZ',
    )
    joined = ltext + '\n' + btext
    for marker in required:
        if marker not in joined:
            raise SystemExit(f'Missing P0.2C9 firmware marker: {marker}')

    for forbidden in (
        'fast_iwm_probe_autosend_pending',
        'fast_iwm_probe_autosend_due',
        'FASTIWM C4 AUTO TX START',
        'FASTIWM C4 AUTOSEND scheduled',
    ):
        if forbidden in btext:
            raise SystemExit(f'P0.2C9 still contains delayed-send marker: {forbidden}')

    isr_start = ltext.index('void IRAM_ATTR phi_isr_handler')
    isr_end = ltext.index('inline void iwm_ll::iwm_extra_set', isr_start)
    isr_text = ltext[isr_start:isr_end]
    if 'fast_iwm_probe_armed && (_phases == 0b1011)' not in isr_text:
        raise SystemExit('P0.2C9 1011 ready trigger is not in the phase ISR.')
    if 'iwm_send_fast_probe_spi()' in isr_text:
        raise SystemExit('Unsafe P0.2C9: blocking transmit appears in phase ISR.')

    buscpp.write_text(btext, encoding='utf-8', newline='\n')
    print('Applied FujiNet P0.2C9 host-ready 2-us transmit overlay.')
    print('Packet transmission now waits for the paired host 1011 READY edge.')


if __name__ == '__main__':
    main()
