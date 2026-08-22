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
            'Apply P0.2C9, then use an already-live 2-us C bit without '
            'waiting for an unnecessary exact $0F mode write.'
        )
    )
    parser.add_argument('--project-root', default='.')
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    base = root / 'tools' / 'patch_spbench_fastiwm_p02c9.py'
    src = root / 'iigs' / 'spbench' / 'src' / 'SPBench.s'
    if not base.is_file() or not src.is_file():
        raise SystemExit('Missing P0.2C9 host transform or SPBENCH source.')

    text = src.read_text(encoding='utf-8')
    if 'FASTPROBE P0.2C10' in text:
        print('FASTPROBE P0.2C10 host overlay already applied.')
        return
    if 'FASTPROBE P0.2C9' not in text:
        subprocess.run(
            [sys.executable, str(base), '--project-root', str(root)],
            check=True,
        )
        text = src.read_text(encoding='utf-8')
    if 'FASTPROBE P0.2C9' not in text:
        raise SystemExit('P0.2C9 host transform did not apply.')

    text = replace_once(
        text,
        "         asc   'FASTPROBE P0.2C9 - host-ready IWM 2us link'0d\n",
        "         asc   'FASTPROBE P0.2C10 - live-C fast READY link'0d\n",
        'P0.2C9 banner',
    )

    old_prepare = '''         lda   #IWMFastMode
         jsr   SetIWMModeC

* P0.2C9: an exact $0F write is preferred, but observed mode $0C is also
* a valid 2-us receive configuration: C=1 selects 2-us cells, and the
* short data latch remains long enough for this interrupt-free polling loop.
* Never hang here if the SmartPort-selected IWM refuses the H/L mode bits.
         lda   FastModeObserved
         sta   FastModeReceive
         and   #IWMCell2usMask
         bne   FastModeUsableC
         brl   FastPacketTimeoutC

FastModeUsableC
'''
    new_prepare = '''* P0.2C10: C8 proved the live mode is $0C. Its C bit already selects
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
    text = replace_once(
        text,
        old_prepare,
        new_prepare,
        'P0.2C9 unconditional exact-mode attempt',
    )

    text = replace_once(
        text,
        "         asc   'FAST FAILED: ready-triggered 2us IWM read timed out.'0d00\n",
        "         asc   'FAST FAILED: C10 READY 2us IWM read timed out.'0d00\n",
        'P0.2C9 timeout message',
    )

    required = (
        'FASTPROBE P0.2C10',
        'P0.2C10: C8 proved the live mode is $0C',
        'FastModeLiveC',
        'lda   FastModeSaved',
        'and   #IWMCell2usMask',
        'lda   >IWM_PH0_ON',
    )
    for marker in required:
        if marker not in text:
            raise SystemExit(f'Missing P0.2C10 marker: {marker}')

    receive_start = text.index('\nReadFastPacketC\n')
    ready = text.index('\nFastModeUsableC\n', receive_start)
    mode_test = text.index('and   #IWMCell2usMask', receive_start)
    mode_write = text.index('jsr   SetIWMModeC', receive_start)
    trigger = text.index('lda   >IWM_PH0_ON', ready)
    if not (mode_test < mode_write < ready < trigger):
        raise SystemExit('Unsafe P0.2C10 live-mode/READY ordering.')

    src.write_text(text, encoding='utf-8', newline='\n')
    print('Applied FASTPROBE P0.2C10 live-C immediate-READY overlay.')


if __name__ == '__main__':
    main()
