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
            'Apply the proven P0.2C19 burst transport, then carry 240 '
            'packets of arbitrary 8-bit PCM through an IWM-safe 8-to-7 codec.'
        )
    )
    parser.add_argument('--project-root', default='.')
    parser.add_argument('--firmware-root', required=True)
    args = parser.parse_args()

    project = Path(args.project_root).resolve()
    root = Path(args.firmware_root).resolve()
    base = project / 'tools' / 'patch_fujinet_fastiwm_p02c19_burst.py'
    llcpp = root / 'lib' / 'bus' / 'iwm' / 'iwm_ll.cpp'
    buscpp = root / 'lib' / 'bus' / 'iwm' / 'iwm.cpp'
    if not base.is_file() or not llcpp.is_file() or not buscpp.is_file():
        raise SystemExit('Missing P0.2C19 transform or IWM sources.')

    ltext = llcpp.read_text(encoding='utf-8')
    btext = buscpp.read_text(encoding='utf-8')
    if 'FASTIWM D0 PCM BURST ARMED' in btext:
        print('FujiNet P0.2D0 PCM overlay already applied.')
        return
    if 'FASTIWM C19 BURST ARMED' not in btext:
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
    if 'FASTIWM C19 BURST ARMED' not in btext:
        raise SystemExit('P0.2C19 firmware transform did not apply.')

    old_payload = '''  for (int i = 0; i < 512; i++)
    packet_buffer[p++] = 0x80 | ((i + fast_iwm_probe_burst_index) & 0x7f);
'''
    new_payload = '''  // D0 carries arbitrary unsigned 8-bit PCM while retaining the IWM
  // requirement that every physical byte have bit 7 set. Seven PCM bytes
  // become seven low-7-bit bytes followed by one packed-MSB byte. The test
  // waveform is the exact repeating sequence 1..255 (never DOC terminator 0).
  const uint32_t packet_pcm_base =
      static_cast<uint32_t>(fast_iwm_probe_burst_index) * 448UL;
  for (uint16_t group = 0; group < 64; group++)
  {
    uint8_t packed_msb = 0;
    const uint16_t group_base = group * 7;
    for (uint8_t lane = 0; lane < 7; lane++)
    {
      const uint32_t sample_number = packet_pcm_base + group_base + lane;
      const uint8_t pcm = static_cast<uint8_t>((sample_number % 255UL) + 1UL);
      packet_buffer[p++] = 0x80 | (pcm & 0x7f);
      packed_msb |= static_cast<uint8_t>(((pcm >> 7) & 1U) << lane);
    }
    packet_buffer[p++] = 0x80 | packed_msb;
  }
'''
    ltext = replace_once(ltext, old_payload, new_payload, 'C19 payload loop')
    ltext = ltext.replace(
        '// 16 sync bytes + marker + 512 deterministic bytes + guard.',
        '// 16 sync bytes + marker + 512 encoded bytes (448 PCM) + guard.',
        1,
    )
    ltext = ltext.replace(
        '// C19 keeps C14\'s proven encoder-native 0.5-us pulse in a 2-us',
        '// D0 keeps C14\'s proven encoder-native 0.5-us pulse in a 2-us',
        1,
    )

    replacements = (
        ('fast_iwm_probe_burst_remaining = 32;',
         'fast_iwm_probe_burst_remaining = 240;'),
        ('FASTIWM C19 READY ARMED', 'FASTIWM D0 READY ARMED'),
        ('FASTIWM C19 READY TRIGGER', 'FASTIWM D0 READY TRIGGER'),
        ('FASTIWM C19 ARM EXPIRED', 'FASTIWM D0 ARM EXPIRED'),
        ('FASTIWM C19 BURST ARMED packets=32 bytes=16384',
         'FASTIWM D0 PCM BURST ARMED packets=240 encoded=122880 pcm=107520'),
        ('packet=31 count=%lu err=0', 'packet=239 count=%lu err=0'),
        ('FASTIWM C19 BURST DONE packets=32 bytes=16384',
         'FASTIWM D0 PCM BURST DONE packets=240 encoded=122880 pcm=107520'),
    )
    for old, new in replacements:
        if old not in btext:
            raise SystemExit(f'Expected D0 firmware conversion pattern not found: {old}')
        btext = btext.replace(old, new, 1)

    required = (
        'FASTIWM D0 PCM BURST ARMED packets=240 encoded=122880 pcm=107520',
        'FASTIWM D0 PCM BURST DONE packets=240 encoded=122880 pcm=107520',
        'fast_iwm_probe_burst_remaining = 240',
        'packet=239 count=%lu err=0',
        'packet_pcm_base',
        'group < 64',
        'lane < 7',
        '(sample_number % 255UL) + 1UL',
        '0x80 | packed_msb',
        'fastcfg.clock_speed_hz = 2 * MHZ',
    )
    joined = ltext + '\n' + btext
    for marker in required:
        if marker not in joined:
            raise SystemExit(f'Missing P0.2D0 firmware marker: {marker}')
    for forbidden in (
        'FASTIWM C19 BURST ARMED',
        'FASTIWM C19 BURST DONE',
        'packets=32 bytes=16384',
        '((i + fast_iwm_probe_burst_index) & 0x7f)',
    ):
        if forbidden in joined:
            raise SystemExit(f'Obsolete C19 firmware path remains: {forbidden}')

    llcpp.write_text(ltext, encoding='utf-8', newline='\n')
    buscpp.write_text(btext, encoding='utf-8', newline='\n')
    print('Applied FujiNet P0.2D0 240-packet 8-to-7 PCM transmitter overlay.')


if __name__ == '__main__':
    main()
