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
            'Apply P0.2C12 and route the internal IWM to the documented '
            'IIgs 3.5-inch path through DISKREG bit 6.'
        )
    )
    parser.add_argument('--project-root', default='.')
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    base = root / 'tools' / 'patch_spbench_fastiwm_p02c12.py'
    src = root / 'iigs' / 'spbench' / 'src' / 'SPBench.s'
    if not base.is_file() or not src.is_file():
        raise SystemExit('Missing P0.2C12 host transform or SPBENCH source.')

    text = src.read_text(encoding='utf-8')
    if 'FASTPROBE P0.2C13' in text:
        print('FASTPROBE P0.2C13 host overlay already applied.')
        return
    if 'FASTPROBE P0.2C12' not in text:
        subprocess.run(
            [sys.executable, str(base), '--project-root', str(root)],
            check=True,
        )
        text = src.read_text(encoding='utf-8')
    if 'FASTPROBE P0.2C12' not in text:
        raise SystemExit('P0.2C12 host transform did not apply.')

    text = replace_once(
        text,
        "         asc   'FASTPROBE P0.2C12 - exact-$0F 2us receive'0d\n",
        "         asc   'FASTPROBE P0.2C13 - 3.5-routed exact-$0F link'0d\n",
        'P0.2C12 banner',
    )

    text = replace_once(
        text,
        '''         lda   >IIGS_DISKREG
         sta   FastDiskRegSaved
         and   #$BF
         sta   >IIGS_DISKREG
''',
        '''         lda   >IIGS_DISKREG
         sta   FastDiskRegSaved
* P0.2C13: DISKREG bit 6 selects the IIgs 3.5-inch path. C11/C12
* accidentally cleared this bit and routed the IWM to the 5.25-inch input.
         ora   #$40
         sta   FastDiskRegActive
         sta   >IIGS_DISKREG
''',
        'P0.2C12 DISKREG route selection',
    )

    text = replace_once(
        text,
        '''FastDiskRegSaved ds  2
FastModeSaved  ds    2
''',
        '''FastDiskRegSaved ds  2
FastDiskRegActive ds 2
FastModeSaved  ds    2
''',
        'P0.2C12 DISKREG state',
    )

    text = replace_once(
        text,
        '''         lda   FastModeReceive
         and   #$00FF
         jsr   WriteHexWord
         jsr   WriteCRLF
         rts
''',
        '''         lda   FastModeReceive
         and   #$00FF
         jsr   WriteHexWord
         jsr   WriteCRLF
         PushLong #FastDiskDiagMsg
         _WriteCString
         lda   FastDiskRegSaved
         and   #$00FF
         jsr   WriteHexWord
         PushLong #FastModeArrowMsg
         _WriteCString
         lda   FastDiskRegActive
         and   #$00FF
         jsr   WriteHexWord
         jsr   WriteCRLF
         rts
''',
        'P0.2C12 timeout diagnostics',
    )

    text = replace_once(
        text,
        "         asc   'FAST FAILED: C12 exact-$0F IWM read timed out.'0d00\n",
        "         asc   'FAST FAILED: C13 3.5-route IWM read timed out.'0d00\n",
        'P0.2C12 timeout message',
    )
    text = replace_once(
        text,
        "FastModeDiagMsg\n         asc   'IWM mode saved/receive=$'00\n",
        "FastModeDiagMsg\n         asc   'IWM mode saved/receive=$'00\n"
        "FastDiskDiagMsg\n         asc   'DISKREG saved/active=$'00\n",
        'P0.2C12 diagnostic messages',
    )

    required = (
        'FASTPROBE P0.2C13',
        'P0.2C13: DISKREG bit 6 selects the IIgs 3.5-inch path',
        'ora   #$40',
        'sta   FastDiskRegActive',
        'DISKREG saved/active=$',
        'cmp   #IWMFastMode',
        'IWM_PH0_ON      equ   $E1C0E1',
    )
    for marker in required:
        if marker not in text:
            raise SystemExit(f'Missing P0.2C13 host marker: {marker}')

    receive = text[text.index('\nReadFastPacketC\n'):text.index('\nFastFindD5C\n')]
    slot_route = receive.index('sta   >IIGS_SLTROMSEL')
    disk_route = receive.index('ora   #$40')
    mode = receive.index('jsr   SetIWMModeC')
    ready = receive.index('lda   >IWM_PH0_ON')
    if not (slot_route < disk_route < mode < ready):
        raise SystemExit('Unsafe P0.2C13 Slot/DISKREG/mode/READY ordering.')

    src.write_text(text, encoding='utf-8', newline='\n')
    print('Applied FASTPROBE P0.2C13 documented 3.5-inch route overlay.')


if __name__ == '__main__':
    main()
