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
            'Make successful provider batches return to SmartPort without '
            'presenting the 0101 bus-reset phase state.'
        )
    )
    parser.add_argument('--project-root', default='.')
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    base = root / 'tools' / 'patch_spbench_fastiwm_p02d1_provider.py'
    src = root / 'iigs' / 'spbench' / 'src' / 'SPBench.s'
    if not base.is_file() or not src.is_file():
        raise SystemExit('Missing P0.2D1 transform or SPBENCH source.')

    text = src.read_text(encoding='utf-8')
    if 'FASTPROBE P0.2D2' in text:
        print('FASTPROBE P0.2D2 soft-return overlay already applied.')
        return
    if 'FASTPROBE P0.2D1' not in text:
        subprocess.run(
            [sys.executable, str(base), '--project-root', str(root)],
            check=True,
        )
        text = src.read_text(encoding='utf-8')
    if 'FASTPROBE P0.2D1' not in text:
        raise SystemExit('P0.2D1 host transform did not apply.')

    text = replace_once(
        text,
        "         asc   'FASTPROBE P0.2D1 - FujiNet provider streamer'0d\n",
        "         asc   'FASTPROBE P0.2D2 - reset-free provider stream'0d\n",
        'D1 banner',
    )

    # A keypress can leave FujiNet expecting another packet in the current
    # 32-packet burst. Preserve the proven hard-reset recovery for that path.
    text = replace_once(
        text,
        '''         jsr   CheckStopKeyD1
         bcs   FastBurstCompleteC
         dec   FastBurstRemaining
''',
        '''         jsr   CheckStopKeyD1
         bcs   FastBurstStopD2
         dec   FastBurstRemaining
''',
        'D1 in-burst stop branch',
    )

    # The additional D2 cleanup paths move the existing corruption handler
    # beyond the 8-bit conditional-branch range by one byte.
    text = replace_once(
        text,
        '''         jsr   DecodeFastPacketD1
         bcs   FastBurstPatternBadC

         rep   #$20
''',
        '''         jsr   DecodeFastPacketD1
         bcc   D2DecodeValid
         brl   FastBurstPatternBadC
D2DecodeValid

         rep   #$20
''',
        'D1 short corruption branch',
    )

    text = replace_once(
        text,
        '''FastBurstCompleteC
         sep   #$20
         jsr   ResetFastBusC
         rep   #$20
         plp
         clc
         rts

''',
        '''FastBurstStopD2
* An explicit user stop can leave a partial batch armed on FujiNet. Use the
* existing reset path only for that recovery case, then report a clean stop.
         sep   #$20
         jsr   ResetFastBusC
         rep   #$20
         plp
         clc
         rts

FastBurstCompleteC
* A complete 32-packet batch has already disarmed FujiNet. Restore the saved
* IWM mode and IIgs speed without ever presenting phase 0101. Keeping the
* proven 1010 SmartPort-enable phase state avoids full device enumeration
* between provider status/arm commands.
         sep   #$20
         jsr   LeaveFastBusD2
         rep   #$20
         plp
         clc
         rts

''',
        'D1 successful batch exit',
    )

    text = replace_once(
        text,
        '''* Pulse the documented SmartPort reset state 0101, then leave phases low.
* M=8 on entry/return.
ResetFastBusC
''',
        '''* Successful D2 batch return. PH3..PH0 is already the normal upstream
* SmartPort enable state 1010 after the final READY-low edge. Do not touch the
* phase lines here: 0101 would reset FujiNet and force complete re-enumeration.
* M=8 on entry/return.
LeaveFastBusD2
         lda   >IWM_DRIVE_OFF
         lda   FastModeSaved
         jsr   SetIWMModeC
         lda   FastSpeedSaved
         sta   >IIGS_SPEED
         rts

* Pulse the documented SmartPort reset state 0101, then leave phases low.
* Reserved for timeout, corruption, DOC failure, underrun, and explicit stop.
* M=8 on entry/return.
ResetFastBusC
''',
        'reset routine anchor',
    )

    required = (
        'FASTPROBE P0.2D2 - reset-free provider stream',
        'FastBurstStopD2',
        'brl   FastBurstPatternBadC',
        'jsr   LeaveFastBusD2',
        'LeaveFastBusD2',
        'lda   FastModeSaved',
        'sta   >IIGS_SPEED',
        'ResetFastBusC',
        'D1StartPackets equ   $03C0',
        'D0DOCBytesPerSecond equ 21973',
    )
    for marker in required:
        if marker not in text:
            raise SystemExit(f'Missing P0.2D2 host marker: {marker}')
    if 'FASTPROBE P0.2D1 - FujiNet provider streamer' in text:
        raise SystemExit('Obsolete D1 host banner remains.')

    success = text[
        text.index('\nFastBurstCompleteC\n'):
        text.index('\nFastBurstPatternBadC\n')
    ]
    if 'ResetFastBusC' in success:
        raise SystemExit('Successful P0.2D2 batch still pulses SmartPort reset.')
    if 'LeaveFastBusD2' not in success:
        raise SystemExit('Successful P0.2D2 batch lost soft-return cleanup.')

    src.write_text(text, encoding='utf-8', newline='\n')
    print('Applied FASTPROBE P0.2D2 reset-free provider batch overlay.')


if __name__ == '__main__':
    main()
