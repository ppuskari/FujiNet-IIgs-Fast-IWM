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
        description='Apply P0.2C then preserve the arm across its terminating SmartPort reset.'
    )
    parser.add_argument('--project-root', default='.')
    parser.add_argument('--firmware-root', required=True)
    args = parser.parse_args()

    project = Path(args.project_root).resolve()
    root = Path(args.firmware_root).resolve()
    base_patch = project / 'tools' / 'patch_fujinet_fastiwm_p02c.py'
    llcpp = root / 'lib' / 'bus' / 'iwm' / 'iwm_ll.cpp'
    buscpp = root / 'lib' / 'bus' / 'iwm' / 'iwm.cpp'

    subprocess.run(
        [sys.executable, str(base_patch),
         '--project-root', str(project),
         '--firmware-root', str(root)],
        check=True,
    )

    ltext = llcpp.read_text(encoding='utf-8')
    btext = buscpp.read_text(encoding='utf-8')

    if 'P0.2C2 arm-hold' in ltext:
        print('FujiNet P0.2C2 arm-hold overlay already applied.')
        return

    ltext = replace_once(
        ltext,
        'volatile uint32_t fast_iwm_probe_req_count = 0;\n',
        'volatile uint32_t fast_iwm_probe_req_count = 0;\n'
        'volatile uint8_t fast_iwm_probe_reset_grace = 0; // P0.2C2 arm-hold\n'
        'volatile uint32_t fast_iwm_probe_reset_hold_count = 0;\n',
        'P0.2C request counter',
    )

    old_req = '''  if (fast_iwm_probe_armed && (_phases == 0b1011))
  {
    fast_iwm_probe_armed = false;
    fast_iwm_probe_request = true;
    fast_iwm_probe_req_count++;
    return;
  }
'''
    new_req = '''  if (fast_iwm_probe_armed && (_phases == 0b1011))
  {
    fast_iwm_probe_armed = false;
    fast_iwm_probe_reset_grace = 0;
    fast_iwm_probe_request = true;
    fast_iwm_probe_req_count++;
    return;
  }
'''
    ltext = replace_once(ltext, old_req, new_req, 'P0.2C 1011 request block')

    old_reset = '''  // Standard SmartPort reset cancels an outstanding experiment.
  if (_phases == 0b0101)
  {
    fast_iwm_probe_armed = false;
    fast_iwm_probe_request = false;
    smartport.iwm_ack_set();
  }
'''
    new_reset = '''  // P0.2C2 arm-hold: the normal 4-us READBLOCK arm transaction ends
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
    ltext = replace_once(ltext, old_reset, new_reset, 'P0.2C reset cancellation block')

    btext = replace_once(
        btext,
        'extern volatile uint32_t fast_iwm_probe_req_count;\n'
        'static uint32_t fast_iwm_probe_arm_count = 0;\n',
        'extern volatile uint32_t fast_iwm_probe_req_count;\n'
        'extern volatile uint8_t fast_iwm_probe_reset_grace;\n'
        'extern volatile uint32_t fast_iwm_probe_reset_hold_count;\n'
        'static uint32_t fast_iwm_probe_arm_count = 0;\n',
        'P0.2C iwm.cpp extern block',
    )

    btext = replace_once(
        btext,
        '''    fast_iwm_probe_armed = true;
    fast_iwm_probe_request = false;
    fast_iwm_probe_arm_count++;
''',
        '''    fast_iwm_probe_armed = true;
    fast_iwm_probe_reset_grace = 1;
    fast_iwm_probe_request = false;
    fast_iwm_probe_arm_count++;
''',
        'P0.2C magic arm state',
    )

    btext = replace_once(
        btext,
        '''    Debug_printf("\\r\\nFASTIWM REQ count=%lu phase=%02x",
                 (unsigned long)fast_iwm_probe_req_count,
                 (unsigned int)smartport.iwm_phase_vector());
''',
        '''    Debug_printf("\\r\\nFASTIWM REQ count=%lu phase=%02x held_resets=%lu",
                 (unsigned long)fast_iwm_probe_req_count,
                 (unsigned int)smartport.iwm_phase_vector(),
                 (unsigned long)fast_iwm_probe_reset_hold_count);
''',
        'P0.2C REQ diagnostic',
    )

    required = (
        'P0.2C2 arm-hold',
        'fast_iwm_probe_reset_grace = 1',
        'fast_iwm_probe_reset_hold_count++',
        'held_resets=%lu',
        'FASTIWM TX START',
        'FASTIWM TX DONE',
    )
    joined = ltext + '\n' + btext
    for item in required:
        if item not in joined:
            raise SystemExit(f'Missing P0.2C2 marker: {item}')

    llcpp.write_text(ltext, encoding='utf-8', newline='\n')
    buscpp.write_text(btext, encoding='utf-8', newline='\n')

    print('Applied FujiNet P0.2C2 one-reset arm-hold overlay.')
    print('P0.2C host image is unchanged.')


if __name__ == '__main__':
    main()
