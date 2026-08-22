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
            'Apply P0.2C8, bound IWM mode programming, and restore the '
            'host-ready 1010/1011 transmit handshake.'
        )
    )
    parser.add_argument('--project-root', default='.')
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    base = root / 'tools' / 'patch_spbench_fastiwm_p02c8.py'
    src = root / 'iigs' / 'spbench' / 'src' / 'SPBench.s'

    if not base.is_file():
        raise SystemExit(f'Missing P0.2C8 host transform: {base}')
    if not src.is_file():
        raise SystemExit(f'Missing SPBENCH source: {src}')

    subprocess.run(
        [sys.executable, str(base), '--project-root', str(root)],
        check=True,
    )

    text = src.read_text(encoding='utf-8')
    if 'FASTPROBE P0.2C9' in text:
        print('FASTPROBE P0.2C9 host overlay already applied.')
        return
    if 'FASTPROBE P0.2C8' not in text:
        raise SystemExit('P0.2C8 host transform did not apply.')

    text = replace_once(
        text,
        'ByteTimeout     equ   $FFFF\n',
        'ByteTimeout     equ   $FFFF\n'
        'ModeWritePasses equ   $0003\n'
        'IWMCell2usMask  equ   $08\n',
        'P0.2C byte-timeout constants',
    )

    text = replace_once(
        text,
        "         asc   'FASTPROBE P0.2C8 - 8-bit-safe IWM 2us mode'0d\n",
        "         asc   'FASTPROBE P0.2C9 - host-ready IWM 2us link'0d\n",
        'P0.2C8 banner',
    )

    old_receive = '''         lda   #IWMFastMode
         jsr   SetIWMModeC

* Technical Note #30: Read Data is DRIVE ENABLED, Q7=0, Q6=0.
         lda   >IWM_DRIVE_ON
         lda   >IWM_Q7_OFF
         lda   >IWM_Q6_OFF
         lda   >IWM_Q6_OFF

         ldx   #MarkerScan
'''
    new_receive = '''         lda   #IWMFastMode
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
* Establish the proven SmartPort enable state 1010 only after the receiver
* is ready. Raising PH0 to 1011 is the explicit one-shot READY request that
* causes paired P0.2C9 FujiNet firmware to transmit; there is no timer race.
         lda   >IWM_PH0_OFF
         lda   >IWM_PH2_OFF
         lda   >IWM_PH3_ON
         lda   >IWM_PH1_ON

* Technical Note #30: Read Data is DRIVE ENABLED, Q7=0, Q6=0.
         lda   >IWM_DRIVE_ON
         lda   >IWM_Q7_OFF
         lda   >IWM_Q6_OFF
         lda   >IWM_Q6_OFF

* PH3..PH0 = 1011: tell FujiNet that Read Data polling is live.
         lda   >IWM_PH0_ON

         ldx   #MarkerScan
'''
    text = replace_once(
        text,
        old_receive,
        new_receive,
        'P0.2C8 mode-to-receive transition',
    )

    old_mode = '''* P0.2C8: enforce M=8 in both the CPU and Merlin assembler state.
* C7 assembled AND #IWMModeMask as 29 1F 00 while the CPU had M=1;
* the leftover 00 at $0A/0640 executed as BRK before the receive loop.
* Desired mode is passed in A; M=8 on return.
SetIWMModeC
         sep   #$20
         sta   FastModeDesired
         lda   >IWM_DRIVE_OFF
         lda   >IWM_Q6_ON
SetIWMModeLoopC
         lda   FastModeDesired
         sta   >IWM_Q7_ON
         lda   FastModeDesired
         eor   >IWM_Q7_OFF
         and   #IWMModeMask
         bne   SetIWMModeLoopC
         rts
'''
    new_mode = '''* P0.2C9: enforce M=8 and bound the ROM-style mode-write loop.
* The IWM may reject mode writes while its drive-disable timer is active.
* Three full 16-bit passes cover the documented interval without allowing
* the host to hang forever. Carry clear means exact match; carry set means
* timeout. FastModeObserved always contains the final live mode bits.
SetIWMModeC
         sep   #$20
         sta   FastModeDesired
         lda   >IWM_DRIVE_OFF
         lda   >IWM_Q6_ON
         ldy   #ModeWritePasses
SetIWMModePassC
         ldx   #$FFFF
SetIWMModeLoopC
         lda   FastModeDesired
         sta   >IWM_Q7_ON
         lda   FastModeDesired
         eor   >IWM_Q7_OFF
         and   #IWMModeMask
         beq   SetIWMModeExactC
         dex
         bne   SetIWMModeLoopC
         dey
         bne   SetIWMModePassC

         lda   >IWM_Q7_OFF
         and   #IWMModeMask
         sta   FastModeObserved
         sec
         rts

SetIWMModeExactC
         lda   >IWM_Q7_OFF
         and   #IWMModeMask
         sta   FastModeObserved
         clc
         rts
'''
    text = replace_once(
        text,
        old_mode,
        new_mode,
        'P0.2C8 unbounded mode-write routine',
    )

    text = replace_once(
        text,
        '''FastModeSaved  ds    2
FastModeDesired ds   2
FastBufferC     ds    512
''',
        '''FastModeSaved  ds    2
FastModeDesired ds   2
FastModeObserved ds  2
FastModeReceive ds   2
FastBufferC     ds    512
''',
        'P0.2C8 mode state',
    )

    text = replace_once(
        text,
        "         asc   'FAST FAILED: 2us-mode IWM read timed out.'0d00\n",
        "         asc   'FAST FAILED: ready-triggered 2us IWM read timed out.'0d00\n",
        'P0.2C8 timeout message',
    )

    required = (
        'FASTPROBE P0.2C9',
        'ModeWritePasses',
        'IWMCell2usMask',
        'FastModeObserved',
        'FastModeReceive',
        'SetIWMModePassC',
        'lda   >IWM_PH3_ON',
        'lda   >IWM_PH1_ON',
        'lda   >IWM_PH0_ON',
        'Three full 16-bit passes',
        'there is no timer race',
    )
    for marker in required:
        if marker not in text:
            raise SystemExit(f'Missing P0.2C9 marker: {marker}')

    entry_start = text.index('\nReadFastPacketC\n')
    entry_end = text.index('\nFastFindD5C\n', entry_start)
    receive_entry = text[entry_start:entry_end]
    if receive_entry.index('#IWMFastMode') > receive_entry.index('FastModeUsableC'):
        raise SystemExit('P0.2C9 must prepare IWM mode before READY setup.')
    ready_entry = receive_entry[receive_entry.index('FastModeUsableC'):]
    ordering = (
        'IWM_PH3_ON',
        'IWM_PH1_ON',
        'IWM_DRIVE_ON',
        'IWM_Q7_OFF',
        'IWM_Q6_OFF',
        'IWM_PH0_ON',
    )
    offsets = [ready_entry.index(marker) for marker in ordering]
    if offsets != sorted(offsets):
        raise SystemExit('Unsafe P0.2C9 receiver/ready-trigger ordering.')

    src.write_text(text, encoding='utf-8', newline='\n')
    print('Applied FASTPROBE P0.2C9 bounded-mode / host-ready overlay.')
    print('Use only with paired FujiNet P0.2C9 ready-trigger firmware.')


if __name__ == '__main__':
    main()
