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
            'Apply P0.2C9, then preserve the armed READY latch across all '
            'ROM cleanup resets until trigger or a five-second expiry.'
        )
    )
    parser.add_argument('--project-root', default='.')
    parser.add_argument('--firmware-root', required=True)
    args = parser.parse_args()

    project = Path(args.project_root).resolve()
    root = Path(args.firmware_root).resolve()
    base = project / 'tools' / 'patch_fujinet_fastiwm_p02c9_ready.py'
    llcpp = root / 'lib' / 'bus' / 'iwm' / 'iwm_ll.cpp'
    buscpp = root / 'lib' / 'bus' / 'iwm' / 'iwm.cpp'
    if not base.is_file() or not llcpp.is_file() or not buscpp.is_file():
        raise SystemExit('Missing P0.2C9 firmware transform or IWM sources.')

    ltext = llcpp.read_text(encoding='utf-8')
    btext = buscpp.read_text(encoding='utf-8')
    if 'FASTIWM C10 READY ARMED' in btext:
        print('FujiNet P0.2C10 reset-hold overlay already applied.')
        return
    if 'FASTIWM C9 READY ARMED' not in btext:
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
    if 'FASTIWM C9 READY ARMED' not in btext:
        raise SystemExit('P0.2C9 firmware transform did not apply.')

    old_reset = '''  // P0.2C2 arm-hold: the normal 4-us READBLOCK arm transaction ends
  // with one SmartPort reset. Preserve the freshly armed one-shot across
  // exactly that reset. Any later reset still cancels stale experiment state.
  if (_phases == 0b0101)
  {
    if (fast_iwm_probe_armed && fast_iwm_probe_reset_grace)
    {
      fast_iwm_probe_reset_grace--;
      fast_iwm_probe_reset_hold_count++;
      smartport.iwm_ack_set();
      return;
    }

    fast_iwm_probe_armed = false;
    fast_iwm_probe_reset_grace = 0;
    fast_iwm_probe_request = false;
    smartport.iwm_ack_set();
  }
'''
    new_reset = '''  // P0.2C10: ROM cleanup can emit more than one reset after the arm
  // response. Preserve an armed one-shot across every reset; normal service
  // context expires it after five seconds if the host never raises READY.
  if (_phases == 0b0101)
  {
    if (fast_iwm_probe_armed)
    {
      fast_iwm_probe_reset_hold_count++;
      smartport.iwm_ack_set();
      return;
    }

    fast_iwm_probe_reset_grace = 0;
    fast_iwm_probe_request = false;
    smartport.iwm_ack_set();
  }
'''
    ltext = replace_once(ltext, old_reset, new_reset, 'P0.2C9 reset grace')

    btext = replace_once(
        btext,
        '''static uint32_t fast_iwm_probe_arm_count = 0;
static uint32_t fast_iwm_probe_tx_count = 0;
''',
        '''static uint32_t fast_iwm_probe_arm_count = 0;
static uint32_t fast_iwm_probe_tx_count = 0;
static unsigned long fast_iwm_probe_arm_deadline = 0;
''',
        'P0.2C9 counter state',
    )

    btext = replace_once(
        btext,
        '''      fast_iwm_probe_armed = true;
      fast_iwm_probe_reset_grace = 1;
      fast_iwm_probe_request = false;
      fast_iwm_probe_arm_count++;
''',
        '''      fast_iwm_probe_armed = true;
      fast_iwm_probe_reset_grace = 0;
      fast_iwm_probe_request = false;
      fast_iwm_probe_arm_count++;
      fast_iwm_probe_arm_deadline = fnSystem.millis() + 5000UL;
''',
        'P0.2C9 arm state',
    )

    btext = btext.replace('FASTIWM C9 READY ARMED', 'FASTIWM C10 READY ARMED')
    btext = btext.replace('FASTIWM C9 READY TRIGGER', 'FASTIWM C10 READY TRIGGER')

    service_anchor = '''#ifdef IIGS_FAST_IWM_PROBE
  if (fast_iwm_probe_request)
  {
'''
    service_insert = '''#ifdef IIGS_FAST_IWM_PROBE
  if (fast_iwm_probe_armed && fast_iwm_probe_arm_deadline &&
      (static_cast<int32_t>(fnSystem.millis() - fast_iwm_probe_arm_deadline) >= 0))
  {
    fast_iwm_probe_armed = false;
    fast_iwm_probe_reset_grace = 0;
    fast_iwm_probe_arm_deadline = 0;
    Debug_printf("\\r\\nFASTIWM C10 ARM EXPIRED held_resets=%lu",
                 (unsigned long)fast_iwm_probe_reset_hold_count);
  }

  if (fast_iwm_probe_request)
  {
'''
    btext = replace_once(
        btext,
        service_anchor,
        service_insert,
        'P0.2C9 service request entry',
    )

    required = (
        'FASTIWM C10 READY ARMED',
        'FASTIWM C10 READY TRIGGER',
        'FASTIWM C10 ARM EXPIRED',
        'fast_iwm_probe_arm_deadline',
        'fnSystem.millis() + 5000UL',
        'if (fast_iwm_probe_armed)',
        'fast_iwm_probe_reset_hold_count++',
    )
    joined = ltext + '\n' + btext
    for marker in required:
        if marker not in joined:
            raise SystemExit(f'Missing P0.2C10 firmware marker: {marker}')

    if 'fast_iwm_probe_armed && fast_iwm_probe_reset_grace' in ltext:
        raise SystemExit('P0.2C10 still limits reset preservation to one reset.')

    llcpp.write_text(ltext, encoding='utf-8', newline='\n')
    buscpp.write_text(btext, encoding='utf-8', newline='\n')
    print('Applied FujiNet P0.2C10 all-reset arm hold with five-second expiry.')


if __name__ == '__main__':
    main()
