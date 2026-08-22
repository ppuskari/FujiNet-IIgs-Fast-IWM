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
            'Apply P0.2C17, then replace the per-byte subroutine receiver '
            'with native-style inline IWM polling for P0.2C18.'
        )
    )
    parser.add_argument('--project-root', default='.')
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    base = root / 'tools' / 'patch_spbench_fastiwm_p02c17.py'
    src = root / 'iigs' / 'spbench' / 'src' / 'SPBench.s'
    if not base.is_file() or not src.is_file():
        raise SystemExit('Missing P0.2C17 transform or SPBENCH source.')

    text = src.read_text(encoding='utf-8')
    if 'FASTPROBE P0.2C18' in text:
        print('FASTPROBE P0.2C18 host overlay already applied.')
        return
    if 'FASTPROBE P0.2C17' not in text:
        subprocess.run(
            [sys.executable, str(base), '--project-root', str(root)],
            check=True,
        )
        text = src.read_text(encoding='utf-8')
    if 'FASTPROBE P0.2C17' not in text:
        raise SystemExit('P0.2C17 host transform did not apply.')

    text = replace_once(
        text,
        "         asc   'FASTPROBE P0.2C17 - verified byte trace'0d\n",
        "         asc   'FASTPROBE P0.2C18 - inline 2us receiver'0d\n",
        'P0.2C17 banner',
    )
    text = replace_once(
        text,
        "         asc   'FAST FAILED: C17 IWM byte trace timed out.'0d00\n",
        "         asc   'FAST FAILED: C18 inline IWM read timed out.'0d00\n",
        'P0.2C17 timeout message',
    )

    old_receiver = '''         ldx   #MarkerScan

FastFindD5C
         jsr   ReadIWMByteC
         bcs   FastPacketTimeoutC
         cmp   #$D5
         beq   FastD5SeenC
         dex
         bne   FastFindD5C
         bra   FastPacketTimeoutC

FastD5SeenC
         jsr   ReadIWMByteC
         bcs   FastPacketTimeoutC
         cmp   #$AA
         bne   FastMarkerRestartC

         jsr   ReadIWMByteC
         bcs   FastPacketTimeoutC
         cmp   #$96
         beq   FastMarkerCompleteC

FastMarkerRestartC
         dex
         bne   FastFindD5C
         bra   FastPacketTimeoutC

FastMarkerCompleteC
         ldx   #$0000

FastCaptureLoopC
         jsr   ReadIWMByteC
         bcs   FastPacketTimeoutC
         sta   FastBufferC,x
         inx
         cpx   #FastPayload
         bne   FastCaptureLoopC
'''
    new_receiver = '''* P0.2C18: poll the IWM data latch inline, matching native Apple 3.5-inch
* code. At 2-us cells a byte arrives every 16 us; avoiding JSR/RTS and a
* fresh timeout setup on every byte leaves adequate 2.8-MHz CPU margin.
         mx    %10
         ldx   #MarkerScan
         ldy   #ByteTimeout

FastFindD5C
         lda   >IWM_Q6_OFF
         bmi   FastD5ByteC
         dey
         bne   FastFindD5C
         brl   FastPacketTimeoutC

FastD5ByteC
         cmp   #$D5
         beq   FastD5SeenC
         dex
         bne   FastFindD5NextC
         brl   FastPacketTimeoutC
FastFindD5NextC
         ldy   #ByteTimeout
         bra   FastFindD5C

FastD5SeenC
         ldy   #ByteTimeout
FastWaitAAC
         lda   >IWM_Q6_OFF
         bmi   FastAAByteC
         dey
         bne   FastWaitAAC
         brl   FastPacketTimeoutC
FastAAByteC
         cmp   #$AA
         bne   FastMarkerRestartC

         ldy   #ByteTimeout
FastWait96C
         lda   >IWM_Q6_OFF
         bmi   Fast96ByteC
         dey
         bne   FastWait96C
         brl   FastPacketTimeoutC
Fast96ByteC
         cmp   #$96
         beq   FastMarkerCompleteC

FastMarkerRestartC
         dex
         bne   FastMarkerRestartNextC
         brl   FastPacketTimeoutC
FastMarkerRestartNextC
         ldy   #ByteTimeout
         bra   FastFindD5C

FastMarkerCompleteC
         ldx   #$0000
         ldy   #ByteTimeout

FastCaptureWaitC
         lda   >IWM_Q6_OFF
         bmi   FastCaptureReadyC
         dey
         bne   FastCaptureWaitC
         brl   FastPacketTimeoutC
FastCaptureReadyC
         sta   FastBufferC,x
         inx
         cpx   #FastPayload
         beq   FastCaptureCompleteC
         ldy   #ByteTimeout
         bra   FastCaptureWaitC
FastCaptureCompleteC
'''
    text = replace_once(
        text,
        old_receiver,
        new_receiver,
        'P0.2C17 subroutine marker/payload receiver',
    )

    required = (
        'FASTPROBE P0.2C18 - inline 2us receiver',
        'FAST FAILED: C18 inline IWM read timed out.',
        'P0.2C18: poll the IWM data latch inline',
        'FastFindD5C\n         lda   >IWM_Q6_OFF',
        'FastWaitAAC\n         lda   >IWM_Q6_OFF',
        'FastWait96C\n         lda   >IWM_Q6_OFF',
        'FastCaptureWaitC\n         lda   >IWM_Q6_OFF',
        'sta   FastBufferC,x',
        'cpx   #FastPayload',
        'cmp   #IWMFastMode',
        'P0.2C13: DISKREG bit 6 selects the IIgs 3.5-inch path',
    )
    for marker in required:
        if marker not in text:
            raise SystemExit(f'Missing P0.2C18 host marker: {marker}')

    receive = text[text.index('\nReadFastPacketC\n'):text.index('\nResetFastBusC\n')]
    for forbidden in (
        'FastFindD5C\n         jsr   ReadIWMByteC',
        'FastCaptureLoopC\n         jsr   ReadIWMByteC',
    ):
        if forbidden in receive:
            raise SystemExit(f'P0.2C18 still contains slow receive path: {forbidden}')
    if '_WriteCString' in receive:
        raise SystemExit('P0.2C18 performs TextTools I/O in the receive path.')

    src.write_text(text, encoding='utf-8', newline='\n')
    print('Applied FASTPROBE P0.2C18 inline 2-us IWM receiver overlay.')


if __name__ == '__main__':
    main()
