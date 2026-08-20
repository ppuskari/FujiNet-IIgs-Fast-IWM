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
        description='Apply P0.2C3 diagnostics then replace manual 1011 trigger with delayed autosend.'
    )
    parser.add_argument('--project-root', default='.')
    parser.add_argument('--firmware-root', required=True)
    args = parser.parse_args()

    project = Path(args.project_root).resolve()
    root = Path(args.firmware_root).resolve()
    base_patch = project / 'tools' / 'patch_fujinet_fastiwm_p02c3_diag.py'
    buscpp = root / 'lib' / 'bus' / 'iwm' / 'iwm.cpp'

    subprocess.run(
        [sys.executable, str(base_patch),
         '--project-root', str(project),
         '--firmware-root', str(root)],
        check=True,
    )

    if not buscpp.is_file():
        raise SystemExit(f'Missing FujiNet IWM bus source: {buscpp}')

    text = buscpp.read_text(encoding='utf-8')

    if 'FASTIWM C4 AUTO TX START' in text:
        print('FujiNet P0.2C4 delayed-autosend overlay already applied.')
        return

    # Add autosend state beside the existing P0.2C counters.  This state is
    # deliberately owned by normal service context, not the GPIO phase ISR.
    text = replace_once(
        text,
        'static uint32_t fast_iwm_probe_arm_count = 0;\n'
        'static uint32_t fast_iwm_probe_tx_count = 0;\n',
        'static uint32_t fast_iwm_probe_arm_count = 0;\n'
        'static uint32_t fast_iwm_probe_tx_count = 0;\n'
        'static bool fast_iwm_probe_autosend_pending = false;\n'
        'static unsigned long fast_iwm_probe_autosend_due = 0;\n'
        'static uint32_t fast_iwm_probe_autosend_count = 0;\n',
        'P0.2C counter block',
    )

    # C3 proved the host sends and FujiNet decodes $7FA55A exactly.  For C4,
    # do not depend on any manually generated phase transition after the ROM
    # call returns.  The magic READBLOCK itself schedules a one-shot transmit
    # 50 ms later.  The synthetic A5 block reply still completes normally at
    # the standard 4-us SmartPort rate.
    old_arm = '''      fast_iwm_probe_armed = true;
      fast_iwm_probe_reset_grace = 1;
      fast_iwm_probe_request = false;
      fast_iwm_probe_arm_count++;

      Debug_printf("\\r\\nFASTIWM ARM block=7fa55a count=%lu raw=%02x %02x %02x",
                   (unsigned long)fast_iwm_probe_arm_count,
                   (unsigned int)cmd.frame.block_rw.num.bytes[0],
                   (unsigned int)cmd.frame.block_rw.num.bytes[1],
                   (unsigned int)cmd.frame.block_rw.num.bytes[2]);
'''
    new_arm = '''      // P0.2C4: negotiation is complete.  Do not arm the GPIO ISR path;
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
    text = replace_once(text, old_arm, new_arm, 'C3 magic arm state')

    # Service the delayed one-shot before the old manual-request path.  The
    # host's existing P0.2C program may still drive 1010->1011, but because
    # fast_iwm_probe_armed is false, that transition cannot queue a duplicate.
    service_anchor = '''#ifdef IIGS_FAST_IWM_PROBE
  if (fast_iwm_probe_request)
  {
'''
    service_insert = '''#ifdef IIGS_FAST_IWM_PROBE
  if (fast_iwm_probe_autosend_pending &&
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

  if (fast_iwm_probe_request)
  {
'''
    text = replace_once(text, service_anchor, service_insert, 'P0.2C service block')

    required = (
        'FASTIWM C3 DIAG ACTIVE',
        'FASTIWM ARM block=7fa55a',
        'FASTIWM C4 AUTOSEND scheduled',
        'FASTIWM C4 AUTO TX START',
        'FASTIWM C4 AUTO TX DONE',
        'fast_iwm_probe_autosend_pending',
        'fnSystem.millis() + 50UL',
        'iwm_send_fast_probe_spi',
    )
    for marker in required:
        if marker not in text:
            raise SystemExit(f'Missing P0.2C4 marker: {marker}')

    buscpp.write_text(text, encoding='utf-8', newline='\n')

    print('Applied FujiNet P0.2C4 delayed-autosend overlay.')
    print('Magic READBLOCK $7FA55A schedules one 2-us packet 50 ms later.')
    print('Host image remains FASTPROBE-P0.2C.po.')


if __name__ == '__main__':
    main()
