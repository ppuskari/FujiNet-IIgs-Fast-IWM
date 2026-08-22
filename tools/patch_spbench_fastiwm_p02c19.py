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
            'Apply the proven P0.2C18 inline receiver, then extend it into '
            'a 32-packet / 16-KiB validated burst benchmark.'
        )
    )
    parser.add_argument('--project-root', default='.')
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    base = root / 'tools' / 'patch_spbench_fastiwm_p02c18.py'
    src = root / 'iigs' / 'spbench' / 'src' / 'SPBench.s'
    if not base.is_file() or not src.is_file():
        raise SystemExit('Missing P0.2C18 transform or SPBENCH source.')

    text = src.read_text(encoding='utf-8')
    if 'FASTPROBE P0.2C19' in text:
        print('FASTPROBE P0.2C19 host overlay already applied.')
        return
    if 'FASTPROBE P0.2C18' not in text:
        subprocess.run(
            [sys.executable, str(base), '--project-root', str(root)],
            check=True,
        )
        text = src.read_text(encoding='utf-8')
    if 'FASTPROBE P0.2C18' not in text:
        raise SystemExit('P0.2C18 host transform did not apply.')

    text = replace_once(
        text,
        "FastPayload     equ   $0200\n",
        "FastPayload     equ   $0200\n"
        "FastBurstPackets equ  $0020\n"
        "FastBurstNumeratorLo equ $0000\n"
        "FastBurstNumeratorHi equ $000F\n",
        'fast payload constants',
    )
    text = replace_once(
        text,
        "         asc   'FASTPROBE P0.2C18 - inline 2us receiver'0d\n"
        "         asc   '4us arm READBLOCK then 2us one-shot response'0d\n",
        "         asc   'FASTPROBE P0.2C19 - 16KiB burst benchmark'0d\n"
        "         asc   'one 4us arm, 32 x 512-byte 2us packets'0d\n",
        'P0.2C18 banner',
    )

    old_result = '''FastArmReturned
* P0.2C6: no TextTools or other output here.  C4's 50-ms timer started
* before the ordinary arm reply was transmitted, so every millisecond
* between ROM return and Read Data polling matters.
         jsr   ReadFastPacketC
         bcs   FastPacketFailedC
         brl   FastPacketReceivedC
FastPacketFailedC
         PushLong #FastTimeoutMsg
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
         PushLong #FastReadyDiagMsg
         _WriteCString
         lda   FastReadyCount
         and   #$00FF
         jsr   WriteHexWord
         PushLong #FastReadyDataMsg
         _WriteCString
         lda   FastReadySamples+0
         and   #$00FF
         jsr   WriteHexWord
         PushLong #FastReadySpaceMsg
         _WriteCString
         lda   FastReadySamples+1
         and   #$00FF
         jsr   WriteHexWord
         PushLong #FastReadySpaceMsg
         _WriteCString
         lda   FastReadySamples+2
         and   #$00FF
         jsr   WriteHexWord
         PushLong #FastReadySpaceMsg
         _WriteCString
         lda   FastReadySamples+3
         and   #$00FF
         jsr   WriteHexWord
         PushLong #FastReadySpaceMsg
         _WriteCString
         lda   FastReadySamples+4
         and   #$00FF
         jsr   WriteHexWord
         PushLong #FastReadySpaceMsg
         _WriteCString
         lda   FastReadySamples+5
         and   #$00FF
         jsr   WriteHexWord
         PushLong #FastReadySpaceMsg
         _WriteCString
         lda   FastReadySamples+6
         and   #$00FF
         jsr   WriteHexWord
         PushLong #FastReadySpaceMsg
         _WriteCString
         lda   FastReadySamples+7
         and   #$00FF
         jsr   WriteHexWord
         PushLong #FastReadySpaceMsg
         _WriteCString
         jsr   WriteCRLF
         rts

FastPacketReceivedC
         jsr   ValidateFastBufferC
         bcc   FastPatternOKC

         PushLong #FastPatternFailMsg
         _WriteCString
         lda   FastPatternFail
         jsr   WriteHexWord
         jsr   WriteCRLF
         rts

FastPatternOKC
         PushLong #FastPassMsg
         _WriteCString
         rts
'''
    new_result = '''FastArmReturned
* Time the complete producer operation: route/mode setup, 32 physical
* packets, per-packet validation, and exact restoration of IIgs state.
         stz   FastBurstIndex
         lda   #FastBurstPackets
         sta   FastBurstRemaining
         stz   FastBurstError
         stz   SuccessfulBlocks
         stz   LastError
         jsr   ReadSystemTick
         lda   CurrentTick
         sta   StartTick
         lda   CurrentTick+2
         sta   StartTick+2

         jsr   ReadFastPacketC
         bcs   FastBurstFailedC

         jsr   FinishTiming
         lda   #FastBurstNumeratorLo
         sta   TestNumerator
         lda   #FastBurstNumeratorHi
         sta   TestNumerator+2
         jsr   ComputeRate
         PushLong #FastPassMsg
         _WriteCString
         jsr   PrintTestReport
         rts

FastBurstFailedC
         jsr   FinishTiming
         PushLong #FastTimeoutMsg
         _WriteCString
         PushLong #FastBurstErrorMsg
         _WriteCString
         lda   FastBurstError
         jsr   WriteHexWord
         PushLong #FastBurstPacketsMsg
         _WriteCString
         lda   SuccessfulBlocks
         sta   MetricValue
         stz   MetricValue+2
         jsr   PrintMetricDecimal
         PushLong #FastBurstPacketMsg
         _WriteCString
         lda   FastBurstIndex
         jsr   WriteHexWord
         PushLong #FastBurstByteMsg
         _WriteCString
         lda   FastPatternFail
         jsr   WriteHexWord
         PushLong #FastBurstTicksMsg
         _WriteCString
         lda   ElapsedTicks
         sta   MetricValue
         lda   ElapsedTicks+2
         sta   MetricValue+2
         jsr   PrintMetricDecimal
         jsr   WriteCRLF
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
'''
    text = replace_once(
        text,
        old_result,
        new_result,
        'P0.2C18 one-packet result handling',
    )

    text = replace_once(
        text,
        '''FastCaptureCompleteC

         jsr   ResetFastBusC
         rep   #$20
         plp
         clc
         rts

FastPacketTimeoutC
         jsr   ResetFastBusC
         rep   #$20
         plp
         sec
         rts
''',
        '''FastCaptureCompleteC
* Return READY low immediately after the final payload byte. Interrupts are
* safe while validating and let GetTick advance between physical packets.
         lda   >IWM_PH0_OFF
         cli
         jsr   ValidateFastBufferC
         bcs   FastBurstPatternBadC

         rep   #$20
         inc   SuccessfulBlocks
         inc   FastBurstIndex
         dec   FastBurstRemaining
         beq   FastBurstCompleteC

* The low phase interval includes the full 512-byte validator. FujiNet uses
* that 1010 interval to re-arm before this next explicit READY edge.
         sep   #$20
         sei
         lda   >IWM_PH0_ON
         ldx   #MarkerScan
         ldy   #ByteTimeout
         brl   FastFindD5C

FastBurstCompleteC
         sep   #$20
         jsr   ResetFastBusC
         rep   #$20
         plp
         clc
         rts

FastBurstPatternBadC
         rep   #$20
         lda   #$0002
         sta   FastBurstError
         sep   #$20
         jsr   ResetFastBusC
         rep   #$20
         plp
         sec
         rts

FastPacketTimeoutC
         rep   #$20
         lda   #$0001
         sta   FastBurstError
         lda   #$FFFF
         sta   FastPatternFail
         sep   #$20
         jsr   ResetFastBusC
         rep   #$20
         plp
         sec
         rts
''',
        'P0.2C18 one-packet completion path',
    )

    text = replace_once(
        text,
        '''FastValidateLoopC
         txa
         and   #$7F
         ora   #$80
''',
        '''FastValidateLoopC
         txa
         clc
         adc   FastBurstIndex
         and   #$7F
         ora   #$80
''',
        'P0.2C18 payload validator',
    )

    text = replace_once(
        text,
        '''FastPatternFail ds   2
FastSpeedSaved ds    2
''',
        '''FastPatternFail ds   2
FastBurstIndex ds    2
FastBurstRemaining ds 2
FastBurstError ds    2
FastSpeedSaved ds    2
''',
        'fast state allocation',
    )

    text = replace_once(
        text,
        "         asc   'FAST FAILED: C18 inline IWM read timed out.'0d00\n",
        "         asc   'FAST FAILED: C19 16KiB burst did not complete.'0d00\n",
        'P0.2C18 timeout message',
    )
    text = replace_once(
        text,
        '''FastPatternFailMsg
         asc   'FAST FAILED: payload mismatch at index $'00
FastPassMsg
         asc   'FAST PASS: exact 512-byte 2us payload verified.'0d00
''',
        '''FastPatternFailMsg
         asc   'FAST FAILED: payload mismatch at index $'00
FastBurstErrorMsg
         asc   '  error=$'00
FastBurstPacketsMsg
         asc   '  completed packets='00
FastBurstPacketMsg
         asc   '  packet=$'00
FastBurstByteMsg
         asc   '  byte=$'00
FastBurstTicksMsg
         asc   '  ticks='00
FastPassMsg
         asc   'FAST BURST PASS: 32 exact packets / 16 KiB verified.'0d00
''',
        'P0.2C18 result messages',
    )

    required = (
        'FASTPROBE P0.2C19 - 16KiB burst benchmark',
        'one 4us arm, 32 x 512-byte 2us packets',
        'FastBurstPackets equ  $0020',
        'FastBurstNumeratorHi equ $000F',
        'FAST BURST PASS: 32 exact packets / 16 KiB verified.',
        'inc   SuccessfulBlocks',
        'dec   FastBurstRemaining',
        'adc   FastBurstIndex',
        'lda   >IWM_PH0_OFF\n         cli\n         jsr   ValidateFastBufferC',
        'sei\n         lda   >IWM_PH0_ON',
        'jsr   ComputeRate',
        'jsr   PrintTestReport',
    )
    for marker in required:
        if marker not in text:
            raise SystemExit(f'Missing P0.2C19 host marker: {marker}')

    receive = text[text.index('\nReadFastPacketC\n'):text.index('\nResetFastBusC\n')]
    if '_WriteCString' in receive:
        raise SystemExit('P0.2C19 performs TextTools I/O in the burst path.')
    if 'FastCaptureWaitC\n         lda   >IWM_Q6_OFF' not in receive:
        raise SystemExit('P0.2C19 lost the proven inline C18 receiver.')

    src.write_text(text, encoding='utf-8', newline='\n')
    print('Applied FASTPROBE P0.2C19 32-packet burst benchmark overlay.')


if __name__ == '__main__':
    main()
