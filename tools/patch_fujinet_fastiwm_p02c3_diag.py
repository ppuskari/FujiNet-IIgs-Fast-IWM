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
        description='Apply P0.2C2 then add explicit decoded READBLOCK diagnostics.'
    )
    parser.add_argument('--project-root', default='.')
    parser.add_argument('--firmware-root', required=True)
    args = parser.parse_args()

    project = Path(args.project_root).resolve()
    root = Path(args.firmware_root).resolve()
    base_patch = project / 'tools' / 'patch_fujinet_fastiwm_p02c2.py'
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

    if 'FASTIWM C3 DIAG ACTIVE' in text:
        print('FujiNet P0.2C3 diagnostics already applied.')
        return

    old = '''#ifdef IIGS_FAST_IWM_PROBE
  if ((cmd.frame.sp_command == SP_CMD_READBLOCK) &&
      (cmd.frame.block_rw.num == 0x7fa55a))
  {
    fast_iwm_probe_armed = true;
    fast_iwm_probe_reset_grace = 1;
    fast_iwm_probe_request = false;
    fast_iwm_probe_arm_count++;

    Debug_printf("\\r\\nFASTIWM ARM block=7fa55a count=%lu",
                 (unsigned long)fast_iwm_probe_arm_count);

    // Return a normal 512-byte 4-us block so the ROM SmartPort call that
    // performed negotiation completes exactly like the proven B3 baseline.
    std::array<uint8_t, 512> fast_arm_reply;
    fast_arm_reply.fill(0xa5);
    transaction_accept(TRANS_STATE::NO_GET);
    transaction_send(fast_arm_reply.data(), fast_arm_reply.size());
    goto done;
  }
#endif
'''

    new = '''#ifdef IIGS_FAST_IWM_PROBE
  // P0.2C3: self-identifying diagnostics.  Do not pass the packed u24le_t
  // object directly through printf varargs; convert it explicitly first.
  static bool fast_iwm_probe_c3_banner_printed = false;
  static uint32_t fast_iwm_probe_c3_read_count = 0;

  if (!fast_iwm_probe_c3_banner_printed)
  {
    fast_iwm_probe_c3_banner_printed = true;
    Debug_printf("\\r\\nFASTIWM C3 DIAG ACTIVE magic=7fa55a");
  }

  if (cmd.frame.sp_command == SP_CMD_READBLOCK)
  {
    const uint32_t fast_iwm_probe_c3_block =
        static_cast<uint32_t>(cmd.frame.block_rw.num);
    fast_iwm_probe_c3_read_count++;

    Debug_printf("\\r\\nFASTIWM C3 READ count=%lu block=%06lx raw=%02x %02x %02x armed=%d grace=%u",
                 (unsigned long)fast_iwm_probe_c3_read_count,
                 (unsigned long)fast_iwm_probe_c3_block,
                 (unsigned int)cmd.frame.block_rw.num.bytes[0],
                 (unsigned int)cmd.frame.block_rw.num.bytes[1],
                 (unsigned int)cmd.frame.block_rw.num.bytes[2],
                 fast_iwm_probe_armed ? 1 : 0,
                 (unsigned int)fast_iwm_probe_reset_grace);

    if (fast_iwm_probe_c3_block == 0x7fa55a)
    {
      fast_iwm_probe_armed = true;
      fast_iwm_probe_reset_grace = 1;
      fast_iwm_probe_request = false;
      fast_iwm_probe_arm_count++;

      Debug_printf("\\r\\nFASTIWM ARM block=7fa55a count=%lu raw=%02x %02x %02x",
                   (unsigned long)fast_iwm_probe_arm_count,
                   (unsigned int)cmd.frame.block_rw.num.bytes[0],
                   (unsigned int)cmd.frame.block_rw.num.bytes[1],
                   (unsigned int)cmd.frame.block_rw.num.bytes[2]);

      // Return a normal 512-byte 4-us block so the ROM SmartPort call that
      // performed negotiation completes exactly like the proven B3 baseline.
      std::array<uint8_t, 512> fast_arm_reply;
      fast_arm_reply.fill(0xa5);
      transaction_accept(TRANS_STATE::NO_GET);
      transaction_send(fast_arm_reply.data(), fast_arm_reply.size());
      goto done;
    }
  }
#endif
'''

    text = replace_once(text, old, new, 'P0.2C2 magic arm block')

    required = (
        'FASTIWM C3 DIAG ACTIVE',
        'FASTIWM C3 READ count=',
        'static_cast<uint32_t>(cmd.frame.block_rw.num)',
        'raw=%02x %02x %02x',
        'FASTIWM ARM block=7fa55a',
        'held_resets=%lu',
        'FASTIWM TX START',
        'FASTIWM TX DONE',
    )
    for marker in required:
        if marker not in text:
            raise SystemExit(f'Missing P0.2C3 marker: {marker}')

    buscpp.write_text(text, encoding='utf-8', newline='\n')

    print('Applied FujiNet P0.2C3 decoded-READBLOCK diagnostic overlay.')
    print('Host image remains FASTPROBE-P0.2C.po.')


if __name__ == '__main__':
    main()
