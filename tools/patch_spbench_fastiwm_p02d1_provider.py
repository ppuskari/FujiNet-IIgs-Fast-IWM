from pathlib import Path
import argparse
import subprocess
import sys


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f'Expected {label} pattern not found.')
    return text.replace(old, new, 1)


def replace_section(text: str, start: str, end: str, new: str, label: str) -> str:
    try:
        first = text.index(start)
        last = text.index(end, first)
    except ValueError as exc:
        raise SystemExit(f'Expected {label} section not found.') from exc
    return text[:first] + new + text[last:]


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            'Turn the proven P0.2D0 DOC test into a continuous FujiNet TCP '
            'provider client with a locked 512 KiB Tool225 source ring.'
        )
    )
    parser.add_argument('--project-root', default='.')
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    base = root / 'tools' / 'patch_spbench_fastiwm_p02d0.py'
    src = root / 'iigs' / 'spbench' / 'src' / 'SPBench.s'
    macros = root / 'iigs' / 'spbench' / 'src' / 'Tool225.Macs.s'
    if not base.is_file() or not src.is_file() or not macros.is_file():
        raise SystemExit('Missing P0.2D0 transform, SPBENCH source, or Tool225 macros.')

    text = src.read_text(encoding='utf-8')
    if 'FASTPROBE P0.2D1' in text:
        print('FASTPROBE P0.2D1 provider overlay already applied.')
        return
    if 'FASTPROBE P0.2D0' not in text:
        subprocess.run(
            [sys.executable, str(base), '--project-root', str(root)],
            check=True,
        )
        text = src.read_text(encoding='utf-8')
    if 'FASTPROBE P0.2D0' not in text:
        raise SystemExit('P0.2D0 host transform did not apply.')

    old_constants = '''FastArmBlockLo  equ   $A55A
FastArmBlockHi  equ   $7F
FastPayload     equ   $0200
FastBurstPackets equ  $00F0
FastBurstNumeratorLo equ $7000
FastBurstNumeratorHi equ $0062
D0PCMBytesPerPacket equ $01C0
D0StartPackets  equ   $0060
D0DOCBlocksAtStart equ $00A8
D0DrainTarget   equ   $0200
D0DrainDelayTicks equ $002D
D0DrainTimeoutTicks equ $02D0
D0DOCBytesPerSecond equ 21973
D0RingBytesHigh equ  $0002
D0RingBlocks    equ   $0200
D0ClearChunks   equ   $0100
D0AttrLocked    equ   $8000
D0ToneFreq      equ   $0058
D0DOCRight      equ   $00
D0DOCLeft       equ   $10
'''
    new_constants = '''FastArmBlockLo  equ   $A55A
FastArmBlockHi  equ   $7F
FastPayload     equ   $024A
FastBurstPackets equ  $0020
D0PCMBytesPerPacket equ $0200
D0DOCBytesPerSecond equ 21973
D0DrainTarget   equ   $0800
D0DrainDelayTicks equ $002D
D0DrainTimeoutTicks equ $02D0
D0RingBytesHigh equ  $0008
D0RingBlocks    equ   $0800
D0ClearChunks   equ   $0400
D0AttrLocked    equ   $8000
D0ToneFreq      equ   $0058
D0DOCRight      equ   $00
D0DOCLeft       equ   $10
D1ProviderStartBlockLo equ $A559
D1ProviderStatusBlockLo equ $A558
D1ProviderStopBlockLo equ $A557
D1ProviderReadyBytes equ $4000
D1ProviderStatusSize equ $0020
D1StartPackets equ   $03C0
D1RingPackets  equ   $0400
D1InitialWaitTicks equ $0078
D1ProviderTimeoutTicks equ $0E10
KBD             equ   $E1C000
KBDSTRB         equ   $E1C010
'''
    text = replace_once(text, old_constants, new_constants, 'D0 constants')

    text = replace_once(
        text,
        "         asc   'FASTPROBE P0.2D0 - live DOC PCM streamer'0d\n"
        "         asc   '8-to-7 packed 2us link, Tool225 21973 Hz'0d\n",
        "         asc   'FASTPROBE P0.2D1 - FujiNet provider streamer'0d\n"
        "         asc   '512K Tool225 ring, TCP raw U8 at 21973 Hz'0d\n",
        'D0 banner',
    )

    text = replace_once(
        text,
        '''         stz   D0DOCError
         stz   D0Underrun

         _TLStartUp
''',
        '''         stz   D0DOCError
         stz   D0Underrun
         stz   D1ProviderError
         stz   D1UserStop
         stz   D1PacketCount
         stz   D1PacketCount+2
         stz   D1RingPacketIndex
         stz   D1BatchCount
         stz   D1BatchCount+2
         stz   D0ProducedBlocks
         stz   D0ProducedBlocks+2
         stz   RawStagePtr+2

         _TLStartUp
''',
        'D1 state initialization',
    )

    text = replace_once(
        text,
        '''D0DOCPrepared
         PushLong #D0ReadyMsg
         _WriteCString
         jsr   RunFastArmTest
         brl   WaitAndQuit
''',
        '''D0DOCPrepared
         PushLong #D0ReadyMsg
         _WriteCString
         PushLong #D1ConnectMsg
         _WriteCString
         jsr   RunProviderStreamD1
         bcc   D1StreamStopped

         PushLong #FastTimeoutMsg
         _WriteCString
         PushLong #FastBurstErrorMsg
         _WriteCString
         lda   FastBurstError
         jsr   WriteHexWord
         PushLong #D1ProviderErrorMsg
         _WriteCString
         lda   D1ProviderError
         jsr   WriteHexWord
         jsr   WriteCRLF
         brl   WaitAndQuit

D1StreamStopped
         PushLong #FastPassMsg
         _WriteCString
         jsr   PrintD1Report
         brl   WaitAndQuit
''',
        'D1 application entry',
    )

    new_controller = '''
RunProviderStreamD1
* Ask FujiNet to open the configured [Network] netstream_host/netstream_port
* TCP source. The command returns at the normal SmartPort rate; connection
* and provider buffering happen from FujiNet service context.
         stz   FastBurstError
         stz   D1ProviderError
         stz   D1UserStop
         stz   D1PacketCount
         stz   D1PacketCount+2
         stz   D1RingPacketIndex
         stz   D1BatchCount
         stz   D1BatchCount+2
         stz   D0PCMBytes
         stz   D0PCMBytes+2
         stz   D0ProducedBlocks
         stz   D0ProducedBlocks+2
         stz   D0Underrun
         lda   #$FFFF
         sta   D0MinimumLead
         lda   D0RingPointer
         sta   D0PCMWritePtr
         lda   D0RingPointer+2
         sta   D0PCMWritePtr+2

         lda   #D1ProviderStartBlockLo
         jsr   CallProviderBlockD1
         bcs   D1ProviderCallFailed

* Give the asynchronous TCP connect a two-second window before the first
* status poll. Interrupts remain enabled throughout provider waits.
         jsr   ReadSystemTick
         lda   CurrentTick
         sta   D1PollTick
         lda   CurrentTick+2
         sta   D1PollTick+2
D1InitialWait
         jsr   CheckStopKeyD1
         bcs   D1ProviderStopped
         jsr   ReadSystemTick
         lda   CurrentTick
         sec
         sbc   D1PollTick
         cmp   #D1InitialWaitTicks
         bcc   D1InitialWait

         jsr   ReadSystemTick
         lda   CurrentTick
         sta   StartTick
         lda   CurrentTick+2
         sta   StartTick+2

D1ProviderBatchLoop
         jsr   WaitProviderBatchD1
         bcs   D1ProviderLoopExit
         lda   D1UserStop
         bne   D1ProviderStopped

* A status reply promised a complete 16 KiB batch. Arm exactly 32 packets;
* no network wait can therefore occur while the IIgs has interrupts masked.
         lda   #FastArmBlockLo
         jsr   CallProviderBlockD1
         bcs   D1ProviderCallFailed
         lda   #FastBurstPackets
         sta   FastBurstRemaining
         stz   FastBurstIndex
         jsr   ReadFastPacketC
         bcs   D1ProviderReceiveFailed

         inc   D1BatchCount
         bne   D1BatchCountReady
         inc   D1BatchCount+2
D1BatchCountReady
         lda   D1UserStop
         beq   D1ProviderBatchLoop

D1ProviderStopped
         jsr   StopProviderD1
         jsr   FinishTiming
         jsr   ComputeD1Rate
         jsr   StopDOCPlaybackD0
         clc
         rts

D1ProviderLoopExit
         lda   D1UserStop
         bne   D1ProviderStopped
D1ProviderReceiveFailed
         lda   FastBurstError
         bne   D1ReceiveErrorReady
         lda   #$0002
         sta   FastBurstError
D1ReceiveErrorReady
         bra   D1ProviderFailed

D1ProviderCallFailed
         sta   LastError
         lda   #$0001
         sta   FastBurstError
D1ProviderFailed
         jsr   StopProviderD1
         jsr   FinishTiming
         jsr   StopDOCPlaybackD0
         sec
         rts

CallProviderBlockD1
ArmBlockStore
         sta   >$000000
ArmSmartPortCall
         jsl   $000000
         rts

StopProviderD1
         lda   #D1ProviderStopBlockLo
         jsr   CallProviderBlockD1
         rts

WaitProviderBatchD1
         jsr   ReadSystemTick
         lda   CurrentTick
         sta   D1PollStartTick
         lda   CurrentTick+2
         sta   D1PollStartTick+2
         stz   D1PollTick
         stz   D1PollTick+2

D1ProviderPoll
         jsr   CheckStopKeyD1
         bcc   D1ProviderPollCall
         clc
         rts

D1ProviderPollCall
         lda   #D1ProviderStatusBlockLo
         jsr   CallProviderBlockD1
         bcs   D1ProviderStatusCallFailed

         PushLong RawStagePtr
         PushLong #D1ProviderStatus
         pea   $0000
         pea   D1ProviderStatusSize
         _BlockMove

* Status begins "D1FS", then version/state/error, then little-endian FIFO
* depth at offset 8. State 2 plus 16 KiB guarantees a no-wait fast burst.
         lda   D1ProviderStatus
         cmp   #$3144
         bne   D1ProviderBadStatus
         lda   D1ProviderStatus+2
         cmp   #$5346
         bne   D1ProviderBadStatus
         sep   #$20
         lda   D1ProviderStatus+5
         cmp   #$03
         beq   D1ProviderReportedError
         cmp   #$02
         bne   D1ProviderNotReady
         rep   #$20
         lda   D1ProviderStatus+8
         cmp   #D1ProviderReadyBytes
         bcs   D1ProviderReady
         bra   D1ProviderPollDelay

D1ProviderNotReady
         rep   #$20
         bra   D1ProviderPollDelay

D1ProviderReportedError
         lda   D1ProviderStatus+6
         sta   D1ProviderError
         rep   #$20
         lda   #$0003
         sta   FastBurstError
         sec
         rts

D1ProviderBadStatus
         lda   #$00F1
         sta   D1ProviderError
         lda   #$0003
         sta   FastBurstError
         sec
         rts

D1ProviderStatusCallFailed
         sta   LastError
         lda   #$00F2
         sta   D1ProviderError
         lda   #$0003
         sta   FastBurstError
         sec
         rts

D1ProviderPollDelay
         jsr   ReadSystemTick
         lda   CurrentTick
         cmp   D1PollTick
         bne   D1ProviderNewTick
         lda   CurrentTick+2
         cmp   D1PollTick+2
         beq   D1ProviderPollDelay
D1ProviderNewTick
         lda   CurrentTick
         sta   D1PollTick
         sec
         sbc   D1PollStartTick
         sta   D1PollElapsed
         lda   CurrentTick+2
         sta   D1PollTick+2
         sbc   D1PollStartTick+2
         bne   D1ProviderPollTimedOut
         lda   D1PollElapsed
         cmp   #D1ProviderTimeoutTicks
         bcs   D1ProviderPollTimedOut
         brl   D1ProviderPoll

D1ProviderPollTimedOut
         lda   #$00F3
         sta   D1ProviderError
         lda   #$0003
         sta   FastBurstError
         sec
         rts

D1ProviderReady
         clc
         rts

CheckStopKeyD1
         sep   #$20
         lda   >KBD
         bpl   D1NoStopKey
         lda   >KBDSTRB
         rep   #$20
         lda   #1
         sta   D1UserStop
         sec
         rts
D1NoStopKey
         rep   #$20
         clc
         rts

ComputeD1Rate
* TestNumerator = PCM bytes * 60 = (bytes << 6) - (bytes << 2).
         lda   D0PCMBytes
         sta   TestNumerator
         sta   RateWork
         lda   D0PCMBytes+2
         sta   TestNumerator+2
         sta   RateWork+2
         ldx   #6
D1RateShift64
         asl   TestNumerator
         rol   TestNumerator+2
         dex
         bne   D1RateShift64
         asl   RateWork
         rol   RateWork+2
         asl   RateWork
         rol   RateWork+2
         lda   TestNumerator
         sec
         sbc   RateWork
         sta   TestNumerator
         lda   TestNumerator+2
         sbc   RateWork+2
         sta   TestNumerator+2
         jsr   ComputeRate
         rts

'''
    text = replace_section(
        text,
        '\nRunFastArmTest\n',
        '* Enter the actual upstream SmartPort enable state 1010',
        new_controller,
        'D0 arm/result controller',
    )

    old_complete_start = '\nFastCaptureCompleteC\n'
    old_complete_end = '\nFastBurstPatternBadC\n'
    new_complete = '''
FastCaptureCompleteC
* Drop READY and enable DOC interrupts before decoding/committing this packet.
         lda   >IWM_PH0_OFF
         cli
         jsr   DecodeFastPacketD1
         bcs   FastBurstPatternBadC

         rep   #$20
         inc   SuccessfulBlocks
         inc   D1PacketCount
         bne   D1PacketCountReady
         inc   D1PacketCount+2
D1PacketCountReady
         lda   D0ProducedBlocks
         clc
         adc   #$0002
         sta   D0ProducedBlocks
         lda   D0ProducedBlocks+2
         adc   #$0000
         sta   D0ProducedBlocks+2

* Match the proven provider profile: start after 30 x 16 KiB = 480 KiB.
* Tool225 immediately preloads 32 KiB, leaving 448 KiB producer lead.
         lda   D0DOCStarted
         bne   D1CheckRunning
         lda   D1PacketCount+2
         bne   D1PacketAccounted
         lda   D1PacketCount
         cmp   #D1StartPackets
         bne   D1PacketAccounted
         jsr   StartDOCPlaybackD0
         bcs   FastBurstDOCFailedD0

D1CheckRunning
         jsr   CheckDOCUnderrunD1
         bcs   FastBurstUnderrunD0

D1PacketAccounted
         jsr   CheckStopKeyD1
         bcs   FastBurstCompleteC
         dec   FastBurstRemaining
         beq   FastBurstCompleteC

* Re-arm the next already-buffered provider packet in this 16 KiB batch.
         sep   #$20
         sei
         lda   >IWM_PH0_ON
         ldx   #MarkerScan
         ldy   #ByteTimeout
         brl   FastFindD5C

FastBurstDOCFailedD0
         lda   #$0003
         sta   FastBurstError
         bra   FastBurstAbortD0

FastBurstUnderrunD0
         lda   #$0004
         sta   FastBurstError

FastBurstAbortD0
         sep   #$20
         jsr   ResetFastBusC
         rep   #$20
         plp
         sec
         rts

FastBurstCompleteC
         sep   #$20
         jsr   ResetFastBusC
         rep   #$20
         plp
         clc
         rts

'''
    text = replace_section(
        text,
        old_complete_start,
        old_complete_end,
        new_complete,
        'D0 packet completion',
    )

    new_decoder = '''
DecodeFastPacketD1
* 73 complete 8-to-7 groups carry 511 PCM bytes in 584 physical bytes.
* The final PCM byte uses one low-7 byte plus one packed-MSB byte, for an
* exact 586-byte IWM-safe payload -> 512 chronological provider bytes.
         php
         sep   #$20
         mx    %10
         ldx   #$0000
         ldy   #$0000
         lda   #$49
         sta   D0GroupRemaining

D1DecodeGroup
         lda   FastBufferC+7,x
         and   #$7F
         sta   D0HighBits
         lda   #$07
         sta   D1LaneRemaining
D1DecodeByte
         lda   FastBufferC,x
         and   #$7F
         lsr   D0HighBits
         bcc   D1DecodedLow
         ora   #$80
D1DecodedLow
         sta   PCMDecodeBuffer,y
         inx
         iny
         dec   D1LaneRemaining
         bne   D1DecodeByte
         inx
         dec   D0GroupRemaining
         bne   D1DecodeGroup

         lda   FastBufferC+584
         and   #$7F
         sta   PCMDecodeBuffer,y
         lda   FastBufferC+585
         and   #$01
         beq   D1FinalPCMReady
         lda   PCMDecodeBuffer,y
         ora   #$80
         sta   PCMDecodeBuffer,y
D1FinalPCMReady
         rep   #$20
         mx    %00
         PushLong #PCMDecodeBuffer
         PushLong D0PCMWritePtr
         pea   $0000
         pea   D0PCMBytesPerPacket
         _BlockMove

         inc   D1RingPacketIndex
         lda   D1RingPacketIndex
         cmp   #D1RingPackets
         bcc   D1AdvanceWritePointer
         stz   D1RingPacketIndex
         lda   D0RingPointer
         sta   D0PCMWritePtr
         lda   D0RingPointer+2
         sta   D0PCMWritePtr+2
         bra   D1WritePointerReady
D1AdvanceWritePointer
         lda   D0PCMWritePtr
         clc
         adc   #D0PCMBytesPerPacket
         sta   D0PCMWritePtr
         lda   D0PCMWritePtr+2
         adc   #$0000
         sta   D0PCMWritePtr+2
D1WritePointerReady
         lda   D0PCMBytes
         clc
         adc   #D0PCMBytesPerPacket
         sta   D0PCMBytes
         lda   D0PCMBytes+2
         adc   #$0000
         sta   D0PCMBytes+2
         plp
         clc
         rts

*-------------------------------------------------
* P0.2D1 Tool225 / DOC setup and monitoring.
*-------------------------------------------------

'''
    text = replace_section(
        text,
        '\nDecodeFastPacketD0\n',
        '\nPrepareDOCStreamD0\n',
        new_decoder,
        'D0 decoder',
    )

    text = text.replace(
        '* Allocate a fixed/locked 128 KiB source ring. It holds all 107520 test PCM\n'
        '* bytes plus unsigned $80 silence through the 512-block drain boundary.',
        '* Allocate the proven fixed/locked 512 KiB mono source ring. The producer\n'
        '* wraps only after 1024 exact 512-byte packets.',
        1,
    )

    new_underrun = '''
CheckDOCUnderrunD1
         jsr   ReadDOCCounterD0

* Fail when the monotonic Tool225 source counter catches the monotonic
* two-block-per-packet producer counter.
         lda   D0ConsumedBlocks+2
         cmp   D0ProducedBlocks+2
         bcc   D1ProducerAhead
         bne   D0ProducerCaught
         lda   D0ConsumedBlocks
         cmp   D0ProducedBlocks
         bcs   D0ProducerCaught

D1ProducerAhead
         lda   D0ProducedBlocks
         sec
         sbc   D0ConsumedBlocks
         sta   D1LeadWork
         lda   D0ProducedBlocks+2
         sbc   D0ConsumedBlocks+2
         bne   D1LeadOkay
         lda   D1LeadWork
         cmp   D0MinimumLead
         bcs   D1LeadOkay
         sta   D0MinimumLead
D1LeadOkay
         clc
         rts

D0ProducerCaught
         lda   #1
         sta   D0Underrun
         lda   #$FD05
         sta   D0DOCError
         sec
         rts

'''
    text = replace_section(
        text,
        '\nCheckDOCUnderrunD0\n',
        '\nWaitDOCDrainD0\n',
        new_underrun,
        'D0 underrun monitor',
    )

    text = replace_section(
        text,
        '\nPrintD0Report\n',
        '\nPrintReadFailure\n',
        '''
PrintD1Report
         PushLong #D0PacketsMsg
         _WriteCString
         lda   D1PacketCount
         sta   MetricValue
         lda   D1PacketCount+2
         sta   MetricValue+2
         jsr   PrintMetricDecimal
         PushLong #D1BatchesMsg
         _WriteCString
         lda   D1BatchCount
         sta   MetricValue
         lda   D1BatchCount+2
         sta   MetricValue+2
         jsr   PrintMetricDecimal
         PushLong #D0PCMBytesMsg
         _WriteCString
         lda   D0PCMBytes
         sta   MetricValue
         lda   D0PCMBytes+2
         sta   MetricValue+2
         jsr   PrintMetricDecimal
         jsr   WriteCRLF

         PushLong #D0TicksMsg
         _WriteCString
         lda   ElapsedTicks
         sta   MetricValue
         lda   ElapsedTicks+2
         sta   MetricValue+2
         jsr   PrintMetricDecimal
         PushLong #D0PCMBpsMsg
         _WriteCString
         lda   BytesPerSecond
         sta   MetricValue
         lda   BytesPerSecond+2
         sta   MetricValue+2
         jsr   PrintMetricDecimal
         PushLong #D0PCMRateMsg
         _WriteCString
         lda   KbitPerSecond
         sta   MetricValue
         lda   KbitPerSecond+2
         sta   MetricValue+2
         jsr   PrintMetricDecimal
         jsr   WriteCRLF

         PushLong #D0MinLeadMsg
         _WriteCString
         lda   D0MinimumLead
         sta   MetricValue
         stz   MetricValue+2
         jsr   PrintMetricDecimal
         PushLong #D0UnderrunMsg
         _WriteCString
         lda   D0Underrun
         jsr   WriteHexWord
         jsr   WriteCRLF
         jsr   WriteCRLF
         rts
''',
        'D0 report',
    )

    text = replace_once(
        text,
        'FastBufferC     ds    512\n',
        'FastBufferC     ds    586\n',
        'fast receive buffer size',
    )
    text = replace_once(
        text,
        'D0ProducedBlocks ds  2\nD0MinimumLead  ds    2\n',
        '''D0ProducedBlocks ds  4
D0MinimumLead  ds    2
D1PacketCount  ds    4
D1BatchCount   ds    4
D1RingPacketIndex ds 2
D1UserStop     ds    2
D1ProviderError ds   2
D1PollStartTick ds   4
D1PollTick     ds    4
D1PollElapsed  ds    2
D1LaneRemaining ds   2
D1LeadWork     ds    2
D1ProviderStatus ds  32
''',
        'D1 state allocation',
    )
    text = replace_once(
        text,
        'D0ExpectedPCM  ds    2\n',
        '',
        'obsolete deterministic PCM state',
    )
    text = replace_once(
        text,
        'RawStagePtr    ds    2\n',
        'RawStagePtr    ds    4\n',
        'bank-zero stage pointer width',
    )
    text = replace_once(
        text,
        'PCMDecodeBuffer ds   448\n',
        'PCMDecodeBuffer ds   512\n',
        'PCM decode buffer size',
    )
    text = replace_once(
        text,
        '         adrl  $00020000\n',
        '         adrl  $00080000\n',
        'Tool225 ring descriptor size',
    )

    text = text.replace(
        "         asc   'Tool225 ready; 128 KiB ring cleared to $80 silence.'0d00",
        "         asc   'Tool225 ready; 512 KiB mono ring cleared to $80.'0d00",
        1,
    )
    text = text.replace(
        "         asc   'FAST FAILED: D0 packed PCM stream did not complete.'0d00",
        "         asc   'STREAM FAILED: provider/batch transport stopped.'0d00",
        1,
    )
    text = text.replace(
        "         asc   'FAST PCM PASS: 240 packets / 107520 bytes verified.'0d00",
        "         asc   'STREAM STOPPED: provider PCM played without underrun.'0d00",
        1,
    )
    text = replace_once(
        text,
        '''D0ReadyMsg
         asc   'Tool225 ready; 512 KiB mono ring cleared to $80.'0d00
''',
        '''D0ReadyMsg
         asc   'Tool225 ready; 512 KiB mono ring cleared to $80.'0d00
D1ConnectMsg
         asc   'Connecting FujiNet to configured 22-mono provider ...'0d00
D1ProviderErrorMsg
         asc   ' provider=$'00
D1BatchesMsg
         asc   ' batches='00
''',
        'D1 messages',
    )

    required = (
        'FASTPROBE P0.2D1 - FujiNet provider streamer',
        'FastPayload     equ   $024A',
        'D1ProviderStartBlockLo equ $A559',
        'D1ProviderStatusBlockLo equ $A558',
        'D1ProviderStopBlockLo equ $A557',
        'D1StartPackets equ   $03C0',
        'DecodeFastPacketD1',
        'FastBufferC     ds    586',
        'PCMDecodeBuffer ds   512',
        'adrl  $00080000',
        'CheckDOCUnderrunD1',
        'RunProviderStreamD1',
        'D1ProviderStatus ds  32',
        'STREAM STOPPED: provider PCM played without underrun.',
    )
    for marker in required:
        if marker not in text:
            raise SystemExit(f'Missing P0.2D1 host marker: {marker}')
    for forbidden in (
        'FASTPROBE P0.2D0',
        'DecodeFastPacketD0',
        'D0ExpectedPCM',
        'cmp   D0ExpectedPCM',
        'FastPayload     equ   $0200',
        'adrl  $00020000',
    ):
        if forbidden in text:
            raise SystemExit(f'Obsolete D0 host path remains: {forbidden}')

    receive = text[text.index('\nReadFastPacketC\n'):text.index('\nSetIWMModeC\n')]
    if '_WriteCString' in receive or '_ReadChar' in receive:
        raise SystemExit('P0.2D1 performs TextTools I/O in a fast batch.')

    src.write_text(text, encoding='utf-8', newline='\n')
    print('Applied FASTPROBE P0.2D1 continuous TCP-provider Tool225 streamer overlay.')


if __name__ == '__main__':
    main()
