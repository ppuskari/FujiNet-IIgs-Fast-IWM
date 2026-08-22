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
            'Apply P0.2C11, require the documented exact $0F receive mode, '
            'and report saved/active mode values on failure.'
        )
    )
    parser.add_argument('--project-root', default='.')
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    base = root / 'tools' / 'patch_spbench_fastiwm_p02c11.py'
    src = root / 'iigs' / 'spbench' / 'src' / 'SPBench.s'
    if not base.is_file() or not src.is_file():
        raise SystemExit('Missing P0.2C11 host transform or SPBENCH source.')

    text = src.read_text(encoding='utf-8')
    if 'FASTPROBE P0.2C12' in text:
        print('FASTPROBE P0.2C12 host overlay already applied.')
        return
    if 'FASTPROBE P0.2C11' not in text:
        subprocess.run(
            [sys.executable, str(base), '--project-root', str(root)],
            check=True,
        )
        text = src.read_text(encoding='utf-8')
    if 'FASTPROBE P0.2C11' not in text:
        raise SystemExit('P0.2C11 host transform did not apply.')

    text = replace_once(
        text,
        "         asc   'FASTPROBE P0.2C11 - routed internal-IWM link'0d\n",
        "         asc   'FASTPROBE P0.2C12 - exact-$0F 2us receive'0d\n",
        'P0.2C11 banner',
    )

    old_prepare = '''* P0.2C10: C8 proved the live mode is $0C. Its C bit already selects
* 2-us cells, so do not spend the host-ready interval trying to change only
* H/L. Attempt the bounded ROM-style $0F write only if C is not already set.
         lda   FastModeSaved
         sta   FastModeObserved
         and   #IWMCell2usMask
         bne   FastModeLiveC

         lda   #IWMFastMode
         jsr   SetIWMModeC

FastModeLiveC
         lda   FastModeObserved
         sta   FastModeReceive
         and   #IWMCell2usMask
         bne   FastModeUsableC
         brl   FastPacketTimeoutC

FastModeUsableC
'''
    new_prepare = '''* P0.2C12: now that internal Slot 6 is explicitly selected, require the
* complete documented 3.5-inch mode. C-only $0C has 2-us cell timing but
* leaves H/L clear; exact $0F supplies asynchronous timing and full-byte
* Read Data latching. SetIWMModeC remains bounded and records the live mode.
         lda   #IWMFastMode
         jsr   SetIWMModeC
         lda   FastModeObserved
         sta   FastModeReceive
         and   #IWMModeMask
         cmp   #IWMFastMode
         beq   FastModeUsableC
         brl   FastPacketTimeoutC

FastModeUsableC
'''
    text = replace_once(
        text,
        old_prepare,
        new_prepare,
        'P0.2C11 C-bit-only receive mode acceptance',
    )

    text = replace_once(
        text,
        '''         PushLong #FastTimeoutMsg
         _WriteCString
         rts
''',
        '''         PushLong #FastTimeoutMsg
         _WriteCString
         PushLong #FastModeDiagMsg
         _WriteCString
         lda   FastModeSaved
         and   #$00FF
         jsr   WriteHexWord
         PushLong #FastModeArrowMsg
         _WriteCString
         lda   FastModeReceive
         and   #$00FF
         jsr   WriteHexWord
         jsr   WriteCRLF
         rts
''',
        'P0.2C11 timeout report',
    )

    text = replace_once(
        text,
        "         asc   'FAST FAILED: C11 routed 2us IWM read timed out.'0d00\n",
        "         asc   'FAST FAILED: C12 exact-$0F IWM read timed out.'0d00\n"
        "FastModeDiagMsg\n"
        "         asc   'IWM mode saved/receive=$'00\n"
        "FastModeArrowMsg\n"
        "         asc   ' -> $'00\n",
        'P0.2C11 timeout message',
    )

    required = (
        'FASTPROBE P0.2C12',
        'P0.2C12: now that internal Slot 6 is explicitly selected',
        'cmp   #IWMFastMode',
        'FastModeDiagMsg',
        'FastModeArrowMsg',
        'lda   FastModeSaved',
        'lda   FastModeReceive',
        'IWM_PH0_ON      equ   $E1C0E1',
    )
    for marker in required:
        if marker not in text:
            raise SystemExit(f'Missing P0.2C12 host marker: {marker}')

    receive = text[text.index('\nReadFastPacketC\n'):text.index('\nFastFindD5C\n')]
    if receive.index('jsr   SetIWMModeC') > receive.index('lda   >IWM_PH0_ON'):
        raise SystemExit('P0.2C12 raises READY before exact mode programming.')
    if 'FastModeLiveC' in receive:
        raise SystemExit('P0.2C12 still bypasses exact mode programming.')

    src.write_text(text, encoding='utf-8', newline='\n')
    print('Applied FASTPROBE P0.2C12 exact-$0F receive-mode overlay.')


if __name__ == '__main__':
    main()
