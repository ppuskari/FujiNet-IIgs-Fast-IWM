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
            'Apply the proven P0.2C19 receiver, decode 240 IWM-safe '
            'packets into 107520 arbitrary PCM bytes, and play them '
            'through the frozen Tool225 21.973-kHz DOC ring.'
        )
    )
    parser.add_argument('--project-root', default='.')
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    base = root / 'tools' / 'patch_spbench_fastiwm_p02c19.py'
    src = root / 'iigs' / 'spbench' / 'src' / 'SPBench.s'
    macros = root / 'iigs' / 'spbench' / 'src' / 'Tool225.Macs.s'
    if not base.is_file() or not src.is_file() or not macros.is_file():
        raise SystemExit('Missing P0.2C19 transform, SPBENCH source, or Tool225 macros.')

    text = src.read_text(encoding='utf-8')
    if 'FASTPROBE P0.2D0' in text:
        print('FASTPROBE P0.2D0 host overlay already applied.')
        return
    if 'FASTPROBE P0.2C19' not in text:
        subprocess.run(
            [sys.executable, str(base), '--project-root', str(root)],
            check=True,
        )
        text = src.read_text(encoding='utf-8')
    if 'FASTPROBE P0.2C19' not in text:
        raise SystemExit('P0.2C19 host transform did not apply.')

    text = replace_once(
        text,
        '         use   4/Util.Macs\n',
        '         use   4/Util.Macs\n'
        '         use   Tool225.Macs.s\n',
        'Tool225 macro include',
    )
    text = replace_once(
        text,
        '''FastBurstPackets equ  $0020
FastBurstNumeratorLo equ $0000
FastBurstNumeratorHi equ $000F
''',
        '''FastBurstPackets equ  $00F0
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
''',
        'C19 burst constants',
    )
    text = replace_once(
        text,
        "         asc   'FASTPROBE P0.2C19 - 16KiB burst benchmark'0d\n"
        "         asc   'one 4us arm, 32 x 512-byte 2us packets'0d\n",
        "         asc   'FASTPROBE P0.2D0 - live DOC PCM streamer'0d\n"
        "         asc   '8-to-7 packed 2us link, Tool225 21973 Hz'0d\n",
        'C19 banner',
    )

    text = replace_once(
        text,
        '''         stz   RawTransferCount

         _TLStartUp
''',
        '''         stz   RawTransferCount
         stz   D0RingHandle
         stz   D0RingHandle+2
         stz   D0RingPointer
         stz   D0RingPointer+2
         stz   D0PCMWritePtr
         stz   D0PCMWritePtr+2
         stz   D0ToolLoaded
         stz   D0ToolActive
         stz   D0DOCStarted
         stz   D0DOCError
         stz   D0Underrun

         _TLStartUp
''',
        'D0 state initialization',
    )
    text = replace_once(
        text,
        '''RawSmartPortReady
         jsr   PrintRawInfo

         jsr   RunFastArmTest
         brl   WaitAndQuit
''',
        '''RawSmartPortReady
         jsr   PrintRawInfo

         jsr   PrepareDOCStreamD0
         bcc   D0DOCPrepared

         PushLong #D0SetupFailMsg
         _WriteCString
         lda   D0DOCError
         jsr   WriteHexWord
         jsr   WriteCRLF
         brl   WaitAndQuit

D0DOCPrepared
         PushLong #D0ReadyMsg
         _WriteCString
         jsr   RunFastArmTest
         brl   WaitAndQuit
''',
        'D0 pre-arm setup',
    )

    old_result = '''FastArmReturned
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
'''
    new_result = '''FastArmReturned
* D0 times the complete useful-PCM producer: 240 physical packets,
* 8-to-7 decode, ring writes, and all concurrent DOC interrupt service.
         stz   FastBurstIndex
         lda   #FastBurstPackets
         sta   FastBurstRemaining
         stz   FastBurstError
         stz   SuccessfulBlocks
         stz   LastError
         stz   D0PCMBytes
         stz   D0PCMBytes+2
         stz   D0Underrun
         lda   #$FFFF
         sta   D0MinimumLead
         lda   #$0001
         sta   D0ExpectedPCM
         lda   D0RingPointer
         sta   D0PCMWritePtr
         lda   D0RingPointer+2
         sta   D0PCMWritePtr+2
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
         jsr   PrintD0Report
         jsr   WaitDOCDrainD0
         bcs   D0DrainFailed
         PushLong #D0PlaybackPassMsg
         _WriteCString
         rts

D0DrainFailed
         PushLong #D0DrainFailMsg
         _WriteCString
         lda   D0DOCError
         jsr   WriteHexWord
         jsr   WriteCRLF
         rts

FastBurstFailedC
         jsr   FinishTiming
         jsr   StopDOCPlaybackD0
         PushLong #FastTimeoutMsg
         _WriteCString
'''
    text = replace_once(text, old_result, new_result, 'C19 result handling')

    old_complete = '''FastCaptureCompleteC
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
'''
    new_complete = '''FastCaptureCompleteC
* READY stays low while interrupts run, the arbitrary 8-bit PCM is decoded,
* and the 448-byte result is committed to the Tool225 source ring.
         lda   >IWM_PH0_OFF
         cli
         jsr   DecodeFastPacketD0
         bcs   FastBurstPatternBadC

         rep   #$20
         inc   SuccessfulBlocks
         inc   FastBurstIndex

* Start the proven immediate 32K DOC ring only after 96 packets / 43008 PCM
* bytes are committed. Tool225 preloads 32768 bytes, leaving 40 source blocks
* of initial producer lead while packet production continues in foreground.
         lda   D0DOCStarted
         bne   D0CheckRunning
         lda   FastBurstIndex
         cmp   #D0StartPackets
         bne   D0PacketAccounted
         jsr   StartDOCPlaybackD0
         bcs   FastBurstDOCFailedD0

D0CheckRunning
         jsr   CheckDOCUnderrunD0
         bcs   FastBurstUnderrunD0

D0PacketAccounted
         dec   FastBurstRemaining
         beq   FastBurstCompleteC

* The low interval includes decode, ring commit, and any pending DOC refill.
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
'''
    text = replace_once(text, old_complete, new_complete, 'C19 packet completion')

    old_validate = '''ValidateFastBufferC
         php
         sep   #$20
         ldx   #$0000
FastValidateLoopC
         txa
         clc
         adc   FastBurstIndex
         and   #$7F
         ora   #$80
         cmp   FastBufferC,x
         bne   FastPatternBadC
         inx
         cpx   #FastPayload
         bne   FastValidateLoopC

         rep   #$20
         plp
         clc
         rts

FastPatternBadC
         rep   #$20
         stx   FastPatternFail
         plp
         sec
         rts
'''
    new_validate = '''DecodeFastPacketD0
* Decode 64 groups. Bytes 0..6 carry PCM low bits and byte 7 carries their
* seven MSBs. Every physical byte remains IWM-valid (bit 7 set). Validate the
* decoded arbitrary-byte sequence 1..255 while producing the DOC ring data.
         php
         sep   #$20
         mx    %10
         ldx   #$0000
         ldy   #$0000

D0DecodeGroup
         lda   FastBufferC+7,x
         and   #$7F
         sta   D0HighBits
         lda   #$07
         sta   D0GroupRemaining

D0DecodeByte
         lda   FastBufferC,x
         and   #$7F
         lsr   D0HighBits
         bcc   D0DecodedLow
         ora   #$80

D0DecodedLow
         cmp   D0ExpectedPCM
         bne   D0DecodedMismatch
         sta   PCMDecodeBuffer,y
         inc   D0ExpectedPCM
         bne   D0ExpectedReady
         inc   D0ExpectedPCM

D0ExpectedReady
         inx
         iny
         dec   D0GroupRemaining
         bne   D0DecodeByte
         inx
         cpx   #FastPayload
         bne   D0DecodeGroup

         rep   #$20
         mx    %00
         PushLong #PCMDecodeBuffer
         PushLong D0PCMWritePtr
         pea   $0000
         pea   D0PCMBytesPerPacket
         _BlockMove

         lda   D0PCMWritePtr
         clc
         adc   #D0PCMBytesPerPacket
         sta   D0PCMWritePtr
         lda   D0PCMWritePtr+2
         adc   #$0000
         sta   D0PCMWritePtr+2

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

D0DecodedMismatch
         rep   #$20
         stx   FastPatternFail
         plp
         sec
         rts

*-------------------------------------------------
* P0.2D0 Tool225 / DOC setup and monitoring.
*-------------------------------------------------

PrepareDOCStreamD0
* Allocate a fixed/locked 128 KiB source ring. It holds all 107520 test PCM
* bytes plus unsigned $80 silence through the 512-block drain boundary.
         pha
         pha
         pea   D0RingBytesHigh
         pea   $0000
         PushWord MyID
         PushWord #D0AttrLocked
         PushLong #0
         _NewHandle
         bcc   D0RingAllocated

         pla
         pla
         sta   D0DOCError
         bne   D0PrepareFailed
         lda   #$FD01
         sta   D0DOCError
D0PrepareFailed
         sec
         rts

D0RingAllocated
         phd
         tsc
         tcd
         lda   [3]
         sta   D0RingPointer
         ldy   #2
         lda   [3],y
         sta   D0RingPointer+2
         pld
         ply
         sty   D0RingHandle
         plx
         stx   D0RingHandle+2

         lda   D0RingPointer
         ora   D0RingPointer+2
         bne   D0RingPointerGood
         lda   #$FD02
         sta   D0DOCError
         sec
         rts

D0RingPointerGood
         lda   D0RingPointer
         sta   D0RingStream
         sta   D0PCMWritePtr
         lda   D0RingPointer+2
         sta   D0RingStream+2
         sta   D0PCMWritePtr+2

* Build one 512-byte $80 source and copy it across the full ring. This makes
* every not-yet-produced byte safe DOC silence and gives deterministic drain.
         sep   #$20
         mx    %10
         lda   #$80
         ldx   #$01FF
D0FillSilenceSource
         sta   PCMSilenceBuffer,x
         dex
         bpl   D0FillSilenceSource
         rep   #$20
         mx    %00

         lda   D0RingPointer
         sta   D0ClearPointer
         lda   D0RingPointer+2
         sta   D0ClearPointer+2
         lda   #D0ClearChunks
         sta   D0ClearRemaining

D0ClearRingLoop
         PushLong #PCMSilenceBuffer
         PushLong D0ClearPointer
         pea   $0000
         pea   $0200
         _BlockMove
         lda   D0ClearPointer
         clc
         adc   #$0200
         sta   D0ClearPointer
         lda   D0ClearPointer+2
         adc   #$0000
         sta   D0ClearPointer+2
         dec   D0ClearRemaining
         bne   D0ClearRingLoop

* Load and initialize the exact frozen Tool225 used by the proven streamer.
         pea   $00E1
         pea   $0000
         _LoadOneTool
         bcc   D0ToolWasLoaded
         sta   D0DOCError
         sec
         rts

D0ToolWasLoaded
         lda   #1
         sta   D0ToolLoaded
         pea   $E1AD
         _PCM225StartUp
         bcc   D0ToolWasStarted
         sta   D0DOCError
         sec
         rts

D0ToolWasStarted
         lda   #1
         sta   D0ToolActive
         _PCM225Init
         bcc   D0ToolInitialized
         sta   D0DOCError
         sec
         rts

D0ToolInitialized
         pea   $0000
         pea   $0000
         _PCM225GetRingStatus
         bcc   D0RingStatusReturned
         pla
         pla
         sta   D0DOCError
         sec
         rts

D0RingStatusReturned
         pla
         sta   D0RingStatusPtr
         pla
         sta   D0RingStatusPtr+2
         lda   D0RingStatusPtr
         ora   D0RingStatusPtr+2
         bne   D0PatchCounterReads
         lda   #$FD03
         sta   D0DOCError
         sec
         rts

D0PatchCounterReads
         lda   D0RingStatusPtr
         sta   D0CounterLowRead+1
         lda   D0RingStatusPtr+2
         jsr   D0StoreLowCounterBank

         lda   D0RingStatusPtr
         clc
         adc   #62
         sta   D0CounterHighRead+1
         lda   D0RingStatusPtr+2
         adc   #0
         jsr   D0StoreHighCounterBank
         clc
         rts

D0StoreLowCounterBank
         sep   #$20
         sta   D0CounterLowRead+3
         rep   #$20
         rts

D0StoreHighCounterBank
         sep   #$20
         sta   D0CounterHighRead+3
         rep   #$20
         rts

StartDOCPlaybackD0
         pea   ^D0RingStream
         pea   D0RingStream
         _PCM225StreamRing
         bcc   D0PlaybackStarted
         sta   D0DOCError
         sec
         rts

D0PlaybackStarted
         lda   #1
         sta   D0DOCStarted
         jsr   ReadDOCCounterD0
         lda   D0ConsumedBlocks+2
         bne   D0StartCounterBad
         lda   D0ConsumedBlocks
         cmp   #$0080
         beq   D0StartCounterGood
D0StartCounterBad
         lda   #$FD04
         sta   D0DOCError
         sec
         rts
D0StartCounterGood
         clc
         rts

ReadDOCCounterD0
         php
         sei
D0CounterLowRead
         lda   >$000000
         sta   D0ConsumedBlocks
D0CounterHighRead
         lda   >$000000
         sta   D0ConsumedBlocks+2
         plp
         rts

CheckDOCUnderrunD0
         jsr   ReadDOCCounterD0

* Convert the 32-bit produced byte count to floor(bytes/256) blocks.
         lda   D0PCMBytes
         xba
         and   #$00FF
         sta   D0ProducedBlocks
         lda   D0PCMBytes+2
         xba
         and   #$FF00
         ora   D0ProducedBlocks
         sta   D0ProducedBlocks

         lda   D0ConsumedBlocks+2
         bne   D0ProducerCaught
         lda   D0ProducedBlocks
         cmp   D0ConsumedBlocks
         bcc   D0ProducerCaught
         sec
         sbc   D0ConsumedBlocks
         cmp   D0MinimumLead
         bcs   D0LeadOkay
         sta   D0MinimumLead
D0LeadOkay
         clc
         rts

D0ProducerCaught
         lda   #1
         sta   D0Underrun
         lda   #$FD05
         sta   D0DOCError
         sec
         rts

WaitDOCDrainD0
         lda   D0DOCStarted
         bne   D0DrainStarted
         lda   #$FD06
         sta   D0DOCError
         sec
         rts

D0DrainStarted
         jsr   ReadSystemTick
         lda   CurrentTick
         sta   D0DrainStartTick
         lda   CurrentTick+2
         sta   D0DrainStartTick+2

D0DrainPoll
         jsr   ReadDOCCounterD0
         lda   D0ConsumedBlocks+2
         bne   D0DrainReached
         lda   D0ConsumedBlocks
         cmp   #D0DrainTarget
         bcs   D0DrainReached

         jsr   ReadSystemTick
         lda   CurrentTick
         sec
         sbc   D0DrainStartTick
         sta   D0DrainElapsed
         lda   CurrentTick+2
         sbc   D0DrainStartTick+2
         bne   D0DrainTimedOut
         lda   D0DrainElapsed
         cmp   #D0DrainTimeoutTicks
         bcc   D0DrainPoll

D0DrainTimedOut
         lda   #$FD07
         sta   D0DOCError
         sec
         rts

D0DrainReached
* Counter 512 means blocks 448..511 (silence) were just loaded while the
* final mixed half 384..447 begins. One 16K period lets all audio finish.
         jsr   ReadSystemTick
         lda   CurrentTick
         sta   D0DrainStartTick
         lda   CurrentTick+2
         sta   D0DrainStartTick+2
D0DrainDelay
         jsr   ReadSystemTick
         lda   CurrentTick
         sec
         sbc   D0DrainStartTick
         cmp   #D0DrainDelayTicks
         bcc   D0DrainDelay

         jsr   StopDOCPlaybackD0
         lda   D0DOCError
         beq   D0DrainOkay
         sec
         rts
D0DrainOkay
         clc
         rts

StopDOCPlaybackD0
         lda   D0DOCStarted
         beq   D0PlaybackAlreadyStopped
         _PCM225Stop
         bcc   D0PlaybackStopOkay
         sta   D0DOCError
D0PlaybackStopOkay
         stz   D0DOCStarted
D0PlaybackAlreadyStopped
         rts

ShutdownDOCStreamD0
         jsr   StopDOCPlaybackD0
         lda   D0ToolActive
         beq   D0ToolAlreadyDown
         _PCM225ShutDown
         stz   D0ToolActive
D0ToolAlreadyDown
         lda   D0ToolLoaded
         beq   D0ToolAlreadyUnloaded
         pea   $00E1
         _UnloadOneTool
         stz   D0ToolLoaded
D0ToolAlreadyUnloaded
         lda   D0RingHandle
         ora   D0RingHandle+2
         beq   D0RingAlreadyDisposed
         PushLong D0RingHandle
         _DisposeHandle
         stz   D0RingHandle
         stz   D0RingHandle+2
D0RingAlreadyDisposed
         rts
'''
    text = replace_once(text, old_validate, new_validate, 'C19 validator')

    text = replace_once(
        text,
        '''
PrintReadFailure
         PushLong #ReadFailureMsg
''',
        '''PrintD0Report
         jsr   ComputeTransferredBytes
         PushLong #D0PacketsMsg
         _WriteCString
         lda   SuccessfulBlocks
         sta   MetricValue
         stz   MetricValue+2
         jsr   PrintMetricDecimal
         PushLong #D0EncodedMsg
         _WriteCString
         lda   BytesTransferred
         sta   MetricValue
         lda   BytesTransferred+2
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

         lda   BytesPerSecond
         sec
         sbc   #D0DOCBytesPerSecond
         sta   D0Headroom
         lda   BytesPerSecond+2
         sbc   #0
         sta   D0Headroom+2
         bcs   D0HeadroomReady
         stz   D0Headroom
         stz   D0Headroom+2
D0HeadroomReady
         PushLong #D0HeadroomMsg
         _WriteCString
         lda   D0Headroom
         sta   MetricValue
         lda   D0Headroom+2
         sta   MetricValue+2
         jsr   PrintMetricDecimal
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

PrintReadFailure
         PushLong #ReadFailureMsg
''',
        'D0 metric reporter',
    )

    text = replace_once(
        text,
        '''ShutTools
         lda   RawHandle
''',
        '''ShutTools
         jsr   ShutdownDOCStreamD0
         lda   RawHandle
''',
        'D0 shutdown hook',
    )

    text = replace_once(
        text,
        '''FastBufferC     ds    512

RawHandle''',
        '''FastBufferC     ds    512

D0RingHandle   ds    4
D0RingPointer  ds    4
D0PCMWritePtr  ds    4
D0RingStatusPtr ds   4
D0ClearPointer ds    4
D0PCMBytes     ds    4
D0Headroom     ds    4
D0DrainStartTick ds  4
D0DrainElapsed ds    2
D0ClearRemaining ds  2
D0ToolLoaded   ds    2
D0ToolActive   ds    2
D0DOCStarted   ds    2
D0DOCError     ds    2
D0Underrun     ds    2
D0ExpectedPCM  ds    2
D0HighBits     ds    2
D0GroupRemaining ds  2
D0ConsumedBlocks ds  4
D0ProducedBlocks ds  2
D0MinimumLead  ds    2

RawHandle''',
        'D0 state allocation',
    )
    text = replace_once(
        text,
        '''ReadBuffer     ds    512

*-------------------------------------------------
* Text
''',
        '''ReadBuffer     ds    512
PCMDecodeBuffer ds   448
PCMSilenceBuffer ds  512

D0RingStream
         adrl  $00000000
         adrl  $00020000
         dw    D0ToneFreq
         dfb   $80
         dfb   $00
         dfb   $02
         dfb   $FF
         dfb   D0DOCRight
         dfb   $FF
         dfb   D0DOCLeft

*-------------------------------------------------
* Text
''',
        'D0 buffers and descriptor',
    )

    text = text.replace(
        "         asc   'FAST FAILED: C19 16KiB burst did not complete.'0d00",
        "         asc   'FAST FAILED: D0 packed PCM stream did not complete.'0d00",
        1,
    )
    text = text.replace(
        "         asc   'FAST BURST PASS: 32 exact packets / 16 KiB verified.'0d00",
        "         asc   'FAST PCM PASS: 240 packets / 107520 bytes verified.'0d00",
        1,
    )
    text = replace_once(
        text,
        '''FastPassMsg
         asc   'FAST PCM PASS: 240 packets / 107520 bytes verified.'0d00
CRLFMsg
''',
        '''FastPassMsg
         asc   'FAST PCM PASS: 240 packets / 107520 bytes verified.'0d00
D0ReadyMsg
         asc   'Tool225 ready; 128 KiB ring cleared to $80 silence.'0d00
D0SetupFailMsg
         asc   'DOC/Tool225 setup failed. error=$'00
D0PlaybackPassMsg
         asc   'DOC PLAY PASS: 21973 Hz drain complete, no underrun.'0d00
D0DrainFailMsg
         asc   'DOC PLAY FAILED during final drain. error=$'00
D0PacketsMsg
         asc   '  packets='00
D0EncodedMsg
         asc   ' encoded bytes='00
D0PCMBytesMsg
         asc   ' PCM bytes='00
D0TicksMsg
         asc   '  ticks='00
D0PCMBpsMsg
         asc   ' useful PCM bytes/sec='00
D0PCMRateMsg
         asc   ' kbit/sec='00
D0HeadroomMsg
         asc   '  DOC headroom bytes/sec='00
D0MinLeadMsg
         asc   ' min lead blocks='00
D0UnderrunMsg
         asc   ' underrun=$'00
CRLFMsg
''',
        'D0 messages',
    )

    required = (
        'FASTPROBE P0.2D0 - live DOC PCM streamer',
        'FastBurstPackets equ  $00F0',
        'D0PCMBytesPerPacket equ $01C0',
        'D0StartPackets  equ   $0060',
        'DecodeFastPacketD0',
        'PCMDecodeBuffer ds   448',
        'D0RingStream',
        '_PCM225StreamRing',
        'CheckDOCUnderrunD0',
        'D0MinimumLead',
        'DOC PLAY PASS: 21973 Hz drain complete, no underrun.',
        'FAST PCM PASS: 240 packets / 107520 bytes verified.',
        'jsr   ShutdownDOCStreamD0',
    )
    for marker in required:
        if marker not in text:
            raise SystemExit(f'Missing P0.2D0 host marker: {marker}')
    for forbidden in (
        'FASTPROBE P0.2C19',
        'FAST BURST PASS: 32 exact packets',
        'FastBurstPackets equ  $0020',
        'ValidateFastBufferC',
    ):
        if forbidden in text:
            raise SystemExit(f'Obsolete C19 host path remains: {forbidden}')

    receive = text[text.index('\nReadFastPacketC\n'):text.index('\nResetFastBusC\n')]
    if '_WriteCString' in receive:
        raise SystemExit('P0.2D0 performs TextTools I/O in the live packet path.')
    if 'FastCaptureWaitC\n         lda   >IWM_Q6_OFF' not in receive:
        raise SystemExit('P0.2D0 lost the proven inline C18 receiver.')

    src.write_text(text, encoding='utf-8', newline='\n')
    print('Applied FASTPROBE P0.2D0 live Tool225/DOC PCM streamer overlay.')


if __name__ == '__main__':
    main()
