*
* FASTPROBE P0.2B
*
* First private IIgs/FujiNet Fast-IWM wire experiment.
*
* This program does NOT use ROM SmartPort for the fast transfer.
* It assumes experimental FujiNet firmware with the matching P0.2B
* responder is installed.
*
* Private phase protocol:
*   PH3 PH2 PH1 PH0 = 1110 : arm fast responder
*   ACK low                 : responder armed
*   PH3 PH2 PH1 PH0 = 1111 : request 2-us stream
*
* The FujiNet responder sends:
*   16 x $FF sync bytes
*   $D5 $AA $96 marker
*   512 deterministic bytes: $80 | (index & $7F)
*   4 x $FF guard bytes
*
* The IIgs receives directly from the IWM read-data register at $C0EC.
* It relies on the machine's observed idle IWM mode $0C (fast bit set)
* and never calls the ROM SmartPort dispatcher during a fast packet.
*

         lst   off
         rel
         typ   S16
         dsk   FASTPROBE.L
         lst   off

         use   4/Int.Macs
         use   4/Locator.Macs
         use   4/Mem.Macs
         use   4/Misc.Macs
         use   4/Text.Macs
         use   4/Util.Macs

         mx    %00

GSOS           equ   $E100A8
QuitCall       equ   $2029

IWM_PH0_OFF    equ   $00C0E0
IWM_PH0_ON     equ   $00C0E1
IWM_PH1_OFF    equ   $00C0E2
IWM_PH1_ON     equ   $00C0E3
IWM_PH2_OFF    equ   $00C0E4
IWM_PH2_ON     equ   $00C0E5
IWM_PH3_OFF    equ   $00C0E6
IWM_PH3_ON     equ   $00C0E7
IWM_Q6_OFF     equ   $00C0EC
IWM_Q6_ON      equ   $00C0ED
IWM_Q7_OFF     equ   $00C0EE

IWMModeMask    equ   $001F
IWMFastBit     equ   $0008

FastPayload    equ   $0200
FastPackets    equ   $0100
MarkerScan     equ   $0080
AckTimeout     equ   $FFFF
ByteTimeout    equ   $6000

ErrModeNotFast equ   $F201
ErrAckTimeout  equ   $F202
ErrByteTimeout equ   $F203
ErrBadPattern  equ   $F204

* 256 packets * 512 bytes = 131072 bytes.
* 131072 * 60 = $00780000.
BenchNumeratorLo equ $0000
BenchNumeratorHi equ $0078

*-------------------------------------------------
* Entry
*-------------------------------------------------

Start
         clc
         xce
         rep   #$30
         phk
         plb

         stz   TLStarted
         stz   MMStarted
         stz   MTStarted
         stz   TextStarted
         stz   IMStarted
         stz   LastError

         _TLStartUp
         lda   #1
         sta   TLStarted

         pha
         _MMStartUp
         pla
         sta   AppID
         lda   #1
         sta   MMStarted

         _MTStartUp
         lda   #1
         sta   MTStarted

         _TextStartUp
         lda   #1
         sta   TextStarted

         _IMStartUp
         lda   #1
         sta   IMStarted

         jsr   InitTextConsole

         PushLong #BannerMsg
         _WriteCString

         jsr   ReadIWMMode
         PushLong #ModeMsg
         _WriteCString
         lda   CurrentStatus
         jsr   WriteHexWord
         PushLong #Mode2Msg
         _WriteCString
         lda   CurrentMode
         jsr   WriteHexWord
         jsr   WriteCRLF

         lda   CurrentMode
         and   #IWMFastBit
         bne   ModeFast

         lda   #ErrModeNotFast
         sta   LastError
         PushLong #ModeAbortMsg
         _WriteCString
         brl   WaitAndQuit

ModeFast
         PushLong #SingleMsg
         _WriteCString

         jsr   EnterFastPhase
         jsr   WaitAckLow
         bcc   SingleArmed

         lda   #ErrAckTimeout
         sta   LastError
         jsr   ExitFastPhase
         PushLong #AckFailMsg
         _WriteCString
         brl   WaitAndQuit

SingleArmed
         jsr   ReadFastPacket
         bcc   SingleReceived

         lda   #ErrByteTimeout
         sta   LastError
         jsr   ExitFastPhase
         PushLong #PacketFailMsg
         _WriteCString
         brl   WaitAndQuit

SingleReceived
         jsr   ExitFastPhase
         jsr   ValidateFastBuffer
         bcc   SingleValid

         lda   #ErrBadPattern
         sta   LastError
         PushLong #PatternFailMsg
         _WriteCString
         lda   PatternFailIndex
         jsr   WriteHexWord
         jsr   WriteCRLF
         brl   WaitAndQuit

SingleValid
         PushLong #SingleOKMsg
         _WriteCString

*-------------------------------------------------
* Sustained private fast-wire benchmark.
*-------------------------------------------------

         PushLong #BenchMsg
         _WriteCString

         lda   #FastPackets
         sta   RemainingPackets
         stz   SuccessfulPackets
         stz   LastError

         jsr   ReadSystemTick
         lda   CurrentTick
         sta   StartTick
         lda   CurrentTick+2
         sta   StartTick+2

         jsr   EnterFastPhase

BenchLoop
         jsr   WaitAckLow
         bcc   BenchArmed
         lda   #ErrAckTimeout
         sta   LastError
         brl   BenchFailed

BenchArmed
         jsr   ReadFastPacket
         bcc   BenchPacketOK
         lda   #ErrByteTimeout
         sta   LastError
         brl   BenchFailed

BenchPacketOK
         inc   SuccessfulPackets
         dec   RemainingPackets
         bne   BenchLoop

         jsr   ExitFastPhase
         jsr   FinishTiming

         lda   #BenchNumeratorLo
         sta   TestNumerator
         lda   #BenchNumeratorHi
         sta   TestNumerator+2
         jsr   ComputeRate
         jsr   PrintBenchReport

         PushLong #AllDoneMsg
         _WriteCString
         bra   WaitAndQuit

BenchFailed
         jsr   ExitFastPhase
         jsr   FinishTiming
         PushLong #BenchFailMsg
         _WriteCString
         lda   LastError
         jsr   WriteHexWord
         PushLong #PacketsMsg
         _WriteCString
         lda   SuccessfulPackets
         sta   MetricValue
         stz   MetricValue+2
         jsr   PrintMetricDecimal
         jsr   WriteCRLF

WaitAndQuit
         PushLong #ExitMsg
         _WriteCString

         PushWord #0
         PushWord #0
         _ReadChar
         pla

         jsr   ShutTools

         jsl   GSOS
         dw    QuitCall
         adrl  QuitPB

QuitReturned
         bra   QuitReturned

*-------------------------------------------------
* Private Fast-IWM phase/ACK protocol.
*-------------------------------------------------

EnterFastPhase
         php
         sei
         sep   #$20

* Build 1110 without passing through normal SmartPort
* enable 1010/1011 as an intermediate state.
         lda   >IWM_PH0_OFF
         lda   >IWM_PH2_ON
         lda   >IWM_PH3_ON
         lda   >IWM_PH1_ON

         rep   #$20
         plp
         rts

WaitAckLow
         php
         sei
         sep   #$20
         ldx   #AckTimeout

AckWaitLoop
* ACK is FujiNet WRPROT/SENSE.  Q6=1,Q7=0 exposes
* SENSE in status bit 7; asserted ACK is low.
         lda   >IWM_Q6_ON
         lda   >IWM_Q7_OFF
         bpl   AckSeenLow
         dex
         bne   AckWaitLoop

         rep   #$20
         plp
         sec
         rts

AckSeenLow
         rep   #$20
         plp
         clc
         rts

ReadFastPacket
* Caller has observed ACK low in phase 1110.
* Prepare read-data mode first, then raise PH0/REQ.
* Keep interrupts disabled for the entire byte stream.

         php
         sei
         sep   #$20

         lda   >IWM_Q7_OFF
         lda   >IWM_Q6_OFF
         lda   >IWM_Q6_OFF

         lda   >IWM_PH0_ON

         ldx   #MarkerScan

FindMarkerD5
         jsr   ReadIWMByte8
         bcs   FastPacketTimeout8
         cmp   #$D5
         beq   MarkerD5Seen
         dex
         bne   FindMarkerD5
         bra   FastPacketTimeout8

MarkerD5Seen
         jsr   ReadIWMByte8
         bcs   FastPacketTimeout8
         cmp   #$AA
         bne   MarkerRestart

         jsr   ReadIWMByte8
         bcs   FastPacketTimeout8
         cmp   #$96
         beq   MarkerComplete

MarkerRestart
         dex
         bne   FindMarkerD5
         bra   FastPacketTimeout8

MarkerComplete
         ldx   #$0000

FastCaptureLoop
         jsr   ReadIWMByte8
         bcs   FastPacketTimeout8
         sta   FastBuffer,x
         inx
         cpx   #FastPayload
         bne   FastCaptureLoop

* PH0 low returns 1111 -> 1110, arming the next packet.
         lda   >IWM_PH0_OFF
         rep   #$20
         plp
         clc
         rts

FastPacketTimeout8
         lda   >IWM_PH0_OFF
         rep   #$20
         plp
         sec
         rts

* M must be 8-bit on entry and remains 8-bit on return.
* A valid IWM byte always has bit 7 set.  Poll until the
* IWM read-data register presents one or timeout expires.

ReadIWMByte8
         ldy   #ByteTimeout

ReadByteWait
         lda   >IWM_Q6_OFF
         bmi   ReadByteReady
         dey
         bne   ReadByteWait
         sec
         rts

ReadByteReady
         clc
         rts

ExitFastPhase
* Leave the private state without transiently entering
* normal SmartPort enable.  Pulse the documented reset
* phase pattern 0101, then leave all phases low.

         php
         sei
         sep   #$20

         lda   >IWM_PH1_OFF
         lda   >IWM_PH3_OFF
         lda   >IWM_PH0_ON

         ldy   #$0800
FastResetDelay
         dey
         bne   FastResetDelay

         lda   >IWM_PH0_OFF
         lda   >IWM_PH2_OFF
         lda   >IWM_Q7_OFF
         lda   >IWM_Q6_OFF

         rep   #$20
         plp
         rts

*-------------------------------------------------
* Validate deterministic 512-byte payload.
*-------------------------------------------------

ValidateFastBuffer
         php
         sep   #$20
         ldx   #$0000

ValidateLoop
         txa
         and   #$7F
         ora   #$80
         cmp   FastBuffer,x
         bne   PatternBad8
         inx
         cpx   #FastPayload
         bne   ValidateLoop

         rep   #$20
         plp
         clc
         rts

PatternBad8
         rep   #$20
         stx   PatternFailIndex
         plp
         sec
         rts

*-------------------------------------------------
* IWM mode/status observation only.
*-------------------------------------------------

ReadIWMMode
         stz   CurrentStatus
         stz   CurrentMode

         php
         sei
         sep   #$20
         lda   >IWM_Q6_ON
         lda   >IWM_Q7_OFF
         sta   CurrentStatus
         and   #$1F
         sta   CurrentMode
         rep   #$20
         plp
         rts

*-------------------------------------------------
* 60 Hz timing and rate calculations.
*-------------------------------------------------

ReadSystemTick
         pha
         pha
         _GetTick
         pla
         sta   CurrentTick
         pla
         sta   CurrentTick+2
         rts

FinishTiming
         jsr   ReadSystemTick

         lda   CurrentTick
         sec
         sbc   StartTick
         sta   ElapsedTicks

         lda   CurrentTick+2
         sbc   StartTick+2
         sta   ElapsedTicks+2

         lda   ElapsedTicks
         ora   ElapsedTicks+2
         bne   TimingNonZero
         lda   #1
         sta   ElapsedTicks
         stz   ElapsedTicks+2

TimingNonZero
         rts

ComputeRate
         stz   BytesPerSecond
         stz   BytesPerSecond+2
         stz   KbitPerSecond
         stz   KbitPerSecond+2

         pha
         pha
         pha
         pha
         PushLong TestNumerator
         PushLong ElapsedTicks
         _LongDivide
         PullLong BytesPerSecond
         pla
         pla

         lda   BytesPerSecond
         sta   RateWork
         lda   BytesPerSecond+2
         sta   RateWork+2

         ldx   #3
RateShiftLoop
         asl   RateWork
         rol   RateWork+2
         dex
         bne   RateShiftLoop

         pha
         pha
         pha
         pha
         PushLong RateWork
         PushLong #1000
         _LongDivide
         PullLong KbitPerSecond
         pla
         pla
         rts

*-------------------------------------------------
* Reports and formatting.
*-------------------------------------------------

PrintBenchReport
         PushLong #ReportPacketsMsg
         _WriteCString
         lda   SuccessfulPackets
         sta   MetricValue
         stz   MetricValue+2
         jsr   PrintMetricDecimal

         PushLong #ReportBytesMsg
         _WriteCString
         stz   MetricValue
         lda   #$0002
         sta   MetricValue+2
         jsr   PrintMetricDecimal

         PushLong #ReportTicksMsg
         _WriteCString
         lda   ElapsedTicks
         sta   MetricValue
         lda   ElapsedTicks+2
         sta   MetricValue+2
         jsr   PrintMetricDecimal
         jsr   WriteCRLF

         PushLong #ReportBpsMsg
         _WriteCString
         lda   BytesPerSecond
         sta   MetricValue
         lda   BytesPerSecond+2
         sta   MetricValue+2
         jsr   PrintMetricDecimal

         PushLong #ReportKbitMsg
         _WriteCString
         lda   KbitPerSecond
         sta   MetricValue
         lda   KbitPerSecond+2
         sta   MetricValue+2
         jsr   PrintMetricDecimal
         jsr   WriteCRLF
         jsr   WriteCRLF
         rts

PrintMetricDecimal
         PushLong MetricValue
         PushLong #DecimalBuffer
         PushWord #10
         PushWord #0
         _Long2Dec
         PushLong #DecimalBuffer
         _WriteCString
         rts

WriteCRLF
         PushLong #CRLFMsg
         _WriteCString
         rts

WriteHexWord
         sta   HexValue

         lda   HexValue
         and   #$F000
         xba
         lsr
         lsr
         lsr
         lsr
         jsr   WriteHexNibble

         lda   HexValue
         and   #$0F00
         xba
         jsr   WriteHexNibble

         lda   HexValue
         and   #$00F0
         lsr
         lsr
         lsr
         lsr
         jsr   WriteHexNibble

         lda   HexValue
         and   #$000F
         jsr   WriteHexNibble
         rts

WriteHexNibble
         and   #$000F
         cmp   #$000A
         bcc   WriteHexNumeric
         clc
         adc   #$0037
         bra   WriteHexOutput

WriteHexNumeric
         clc
         adc   #$0030

WriteHexOutput
         pha
         _WriteChar
         rts

*-------------------------------------------------
* Text console / shutdown.
*-------------------------------------------------

InitTextConsole
         PushWord #$00FF
         PushWord #$0080
         _SetInGlobals

         PushWord #$00FF
         PushWord #$0080
         _SetOutGlobals

         PushWord #$00FF
         PushWord #$0080
         _SetErrGlobals

         PushWord #0
         PushLong #3
         _SetInputDevice

         PushWord #0
         PushLong #3
         _SetOutputDevice

         PushWord #0
         PushLong #3
         _SetErrorDevice

         PushWord #0
         _InitTextDev
         PushWord #1
         _InitTextDev
         PushWord #2
         _InitTextDev

         PushWord #$000C
         _WriteChar
         rts

ShutTools
         lda   IMStarted
         beq   IMAlreadyStopped
         _IMShutDown
         stz   IMStarted

IMAlreadyStopped
         lda   TextStarted
         beq   TextAlreadyStopped
         _TextShutDown
         stz   TextStarted

TextAlreadyStopped
         lda   MTStarted
         beq   MTAlreadyStopped
         _MTShutDown
         stz   MTStarted

MTAlreadyStopped
         lda   MMStarted
         beq   MMAlreadyStopped
         lda   AppID
         pha
         _MMShutDown
         stz   MMStarted

MMAlreadyStopped
         lda   TLStarted
         beq   TLAlreadyStopped
         _TLShutDown
         stz   TLStarted

TLAlreadyStopped
         rts

*-------------------------------------------------
* State
*-------------------------------------------------

QuitPB
         dw    0

TLStarted      ds    2
MMStarted      ds    2
MTStarted      ds    2
TextStarted    ds    2
IMStarted      ds    2
AppID          ds    2

CurrentStatus  ds    2
CurrentMode    ds    2
LastError      ds    2
PatternFailIndex ds  2
RemainingPackets ds  2
SuccessfulPackets ds 2

CurrentTick    ds    4
StartTick      ds    4
ElapsedTicks   ds    4
TestNumerator  ds    4
BytesPerSecond ds    4
KbitPerSecond  ds    4
RateWork       ds    4
MetricValue    ds    4
HexValue       ds    2
DecimalBuffer  ds    16

FastBuffer     ds    512

*-------------------------------------------------
* Text
*-------------------------------------------------

BannerMsg
         asc   'FASTPROBE P0.2B - private Fast-IWM wire test'0d
         asc   'No ROM SmartPort calls during the fast packet'0d
         asc   'FujiNet responder required; TX target = 2us cells'0d0d00
ModeMsg
         asc   'Idle IWM: status=$'00
Mode2Msg
         asc   ' mode=$'00
ModeAbortMsg
         asc   'IWM fast bit is not set at idle; test aborted.'0d0d00
SingleMsg
         asc   'Single 512-byte fast packet + pattern verify ... '00
AckFailMsg
         asc   'FAILED: FujiNet fast responder did not assert ACK.'0d0d00
PacketFailMsg
         asc   'FAILED: timeout receiving fast IWM byte stream.'0d0d00
PatternFailMsg
         asc   'FAILED: payload pattern mismatch at index $'00
SingleOKMsg
         asc   'PASS'0d0d00
BenchMsg
         asc   'Benchmark: 256 x 512-byte private fast packets ...'0d00
BenchFailMsg
         asc   'Benchmark stopped. error=$'00
PacketsMsg
         asc   ' completed packets='00
ReportPacketsMsg
         asc   'packets='00
ReportBytesMsg
         asc   ' bytes='00
ReportTicksMsg
         asc   ' ticks='00
ReportBpsMsg
         asc   'bytes/sec='00
ReportKbitMsg
         asc   ' kbit/sec='00
AllDoneMsg
         asc   'FAST-IWM P0.2B wire test complete.'0d0d00
ExitMsg
         asc   'Press any key to return to GS/OS.'0d00
CRLFMsg
         asc   0d00
