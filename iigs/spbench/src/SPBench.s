*
* SPBENCH P0.1A
*
* Apple IIgs FujiNet SmartPort baseline benchmark.
*
* This first executable intentionally measures the
* GS/OS Device Manager DRead path, one 512-byte block
* per call.  It gives us a safe, reproducible baseline
* before P0.1B moves underneath GS/OS to direct
* SmartPort firmware calls.
*
* Launch this program from the FujiNet-mounted SPBENCH
* ProDOS image.  It identifies the block device that
* owns prefix 1, warms it with 256 block reads, then
* measures 1 MiB and 4 MiB sequential transfers.
*
* Timed loops contain no screen output and use the
* 60 Hz Misc Tool GetTick counter.
*

         lst   off
         rel
         typ   S16
         dsk   SPBENCH.L
         lst   off

         use   4/Int.Macs
         use   4/Locator.Macs
         use   4/Mem.Macs
         use   4/Misc.Macs
         use   4/Text.Macs
         use   4/Util.Macs

         mx    %00

GSOS           equ   $E100A8
GetPrefixCall  equ   $200A
VolumeCall     equ   $2008
DInfoCall      equ   $202C
DReadCall      equ   $202F
QuitCall       equ   $2029

BlockDeviceBit equ   $0080
NoMoreDevices  equ   $0011
ProDOSFSID     equ   $0001
BlockSize      equ   $0200

ErrShortRead   equ   $FF01
ErrNoDevice    equ   $FF02
ErrSmallDevice equ   $FF03

WarmStart      equ   $0000
WarmBlocks     equ   $0100
Test1Start     equ   $0400
Test1Blocks    equ   $0800
Test4Start     equ   $1000
Test4Blocks    equ   $2000
MinBlocks      equ   $3000

TextTool       equ   $000C

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
         ora   #$0100
         sta   MyID
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

         jsr   FindCurrentBlockDevice
         bcc   DeviceReady

         sta   LastError
         PushLong #FindDeviceErrMsg
         _WriteCString
         lda   LastError
         jsr   WriteHexWord
         jsr   WriteCRLF
         brl   WaitAndQuit

DeviceReady
         jsr   PrintDeviceInfo

* The 4 MiB test starts at block $1000 and consumes
* $2000 blocks, so the device must contain at least
* $3000 blocks.

         lda   proDINFO+$0C
         bne   DeviceLargeEnough
         lda   proDINFO+$0A
         cmp   #MinBlocks
         bcs   DeviceLargeEnough

         lda   #ErrSmallDevice
         sta   LastError
         PushLong #SmallDeviceMsg
         _WriteCString
         lda   LastError
         jsr   WriteHexWord
         jsr   WriteCRLF
         brl   WaitAndQuit

DeviceLargeEnough
         PushLong #WarmupMsg
         _WriteCString

         lda   #WarmStart
         sta   TestStartBlock
         stz   TestStartBlock+2
         lda   #WarmBlocks
         sta   TestBlockCount
         stz   TestNumerator
         stz   TestNumerator+2

         jsr   RunTimedReadTest
         bcc   WarmupDone
         jsr   PrintReadFailure
         brl   WaitAndQuit

WarmupDone
         PushLong #WarmupDoneMsg
         _WriteCString

* 1 MiB = 2048 * 512 bytes.
* bytes * 60 = $03C00000 for B/s calculation.

         PushLong #Test1Msg
         _WriteCString

         lda   #Test1Start
         sta   TestStartBlock
         stz   TestStartBlock+2
         lda   #Test1Blocks
         sta   TestBlockCount
         stz   TestNumerator
         lda   #$03C0
         sta   TestNumerator+2

         jsr   RunTimedReadTest
         bcc   Test1Done
         jsr   PrintReadFailure
         brl   WaitAndQuit

Test1Done
         jsr   ComputeRate
         jsr   PrintTestReport

* 4 MiB = 8192 * 512 bytes.
* bytes * 60 = $0F000000 for B/s calculation.

         PushLong #Test4Msg
         _WriteCString

         lda   #Test4Start
         sta   TestStartBlock
         stz   TestStartBlock+2
         lda   #Test4Blocks
         sta   TestBlockCount
         stz   TestNumerator
         lda   #$0F00
         sta   TestNumerator+2

         jsr   RunTimedReadTest
         bcc   Test4Done
         jsr   PrintReadFailure
         brl   WaitAndQuit

Test4Done
         jsr   ComputeRate
         jsr   PrintTestReport

         PushLong #AllDoneMsg
         _WriteCString

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
* Text console
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

*-------------------------------------------------
* Locate the GS/OS block device that owns prefix 1.
*
* This follows the same DInfo/Volume technique used
* by BenchmarkeD: reduce prefix 1 to its volume name,
* enumerate readable block devices, and compare the
* mounted volume name.
*-------------------------------------------------

FindCurrentBlockDevice
         jsl   GSOS
         dw    GetPrefixCall
         adrl  proGETPREFIX
         bcc   PrefixReturned
         rts

PrefixReturned
         sep   #$20
         lda   pfxNAMEopen
         beq   PrefixBad8

* Remove the final colon, then stop at the next colon
* after the leading volume-name colon.

         dec   pfxNAMEopen
         ldx   #1

PrefixScan
         lda   pfxNAMEopen2,x
         cmp   #':'
         beq   PrefixVolumeReady8
         inx
         cpx   pfxNAMEopen
         bne   PrefixScan

PrefixVolumeReady8
         stx   pfxNAMEopen
         rep   #$20
         bra   BeginDeviceScan

PrefixBad8
         rep   #$20
         lda   #ErrNoDevice
         sec
         rts

BeginDeviceScan
         lda   #1
         sta   proDINFO+2

DeviceScanLoop
         jsl   GSOS
         dw    DInfoCall
         adrl  proDINFO
         bcc   DeviceInfoReturned

         cmp   #NoMoreDevices
         beq   DeviceNotFound

NextDevice
         inc   proDINFO+2
         bra   DeviceScanLoop

DeviceInfoReturned
         lda   proDINFO+8
         and   #BlockDeviceBit
         beq   NextDevice

         jsl   GSOS
         dw    VolumeCall
         adrl  proVOLUME
         bcs   NextDevice

         lda   proVOLUME+$12
         cmp   #ProDOSFSID
         bne   NextDevice

         lda   proVOLUME+$14
         cmp   #BlockSize
         bne   NextDevice

* Compare the two class-one strings byte-for-byte.

         sep   #$20
         lda   pfxNAMEopen
         cmp   volNAMEopen
         bne   VolumeMismatch8

         rep   #$20
         ldx   #0

VolumeCompareLoop
         sep   #$20
         lda   pfxNAMEopen2,x
         cmp   volNAMEopen2,x
         bne   VolumeMismatch8
         rep   #$20
         inx
         cpx   pfxNAMEopen
         bne   VolumeCompareLoop

         lda   proDINFO+2
         sta   proDREAD+2
         clc
         rts

VolumeMismatch8
         rep   #$20
         bra   NextDevice

DeviceNotFound
         lda   #ErrNoDevice
         sec
         rts

*-------------------------------------------------
* Print selected device information.
*-------------------------------------------------

PrintDeviceInfo
         PushLong #DeviceMsg
         _WriteCString
         lda   proDINFO+2
         jsr   WriteHexWord

         PushLong #SlotMsg
         _WriteCString
         lda   proDINFO+$0E
         jsr   WriteHexWord

         PushLong #UnitMsg
         _WriteCString
         lda   proDINFO+$10
         jsr   WriteHexWord

         PushLong #BlocksMsg
         _WriteCString
         lda   proDINFO+$0A
         sta   MetricValue
         lda   proDINFO+$0C
         sta   MetricValue+2
         jsr   PrintMetricDecimal
         jsr   WriteCRLF
         jsr   WriteCRLF
         rts

*-------------------------------------------------
* Run one timed sequential DRead test.
*
* TestStartBlock = 32-bit starting block
* TestBlockCount = 16-bit number of 512-byte reads
*
* Returns C=0 on success.
* Returns C=1 with LastError set on GS/OS error or
* a short transfer.
*-------------------------------------------------

RunTimedReadTest
         lda   TestStartBlock
         sta   proDREAD+$0C
         lda   TestStartBlock+2
         sta   proDREAD+$0E

         lda   TestBlockCount
         sta   RemainingBlocks
         stz   SuccessfulBlocks
         stz   LastError

         jsr   ReadSystemTick
         lda   CurrentTick
         sta   StartTick
         lda   CurrentTick+2
         sta   StartTick+2

ReadTestLoop
         stz   proDREAD+$12
         stz   proDREAD+$14

         jsl   GSOS
         dw    DReadCall
         adrl  proDREAD
         bcc   DReadReturned

         sta   LastError
         jsr   FinishTiming
         sec
         rts

DReadReturned
         lda   proDREAD+$12
         cmp   #BlockSize
         bne   ShortTransfer
         lda   proDREAD+$14
         bne   ShortTransfer

         inc   SuccessfulBlocks

         lda   proDREAD+$0C
         clc
         adc   #1
         sta   proDREAD+$0C
         lda   proDREAD+$0E
         adc   #0
         sta   proDREAD+$0E

         dec   RemainingBlocks
         bne   ReadTestLoop

         jsr   FinishTiming
         clc
         rts

ShortTransfer
         lda   #ErrShortRead
         sta   LastError
         jsr   FinishTiming
         sec
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

         rts

ReadSystemTick
         pha
         pha
         _GetTick
         pla
         sta   CurrentTick
         pla
         sta   CurrentTick+2
         rts

*-------------------------------------------------
* Rate calculation.
*
* TestNumerator is total expected bytes * 60.
* B/s = TestNumerator / elapsed 60 Hz ticks.
* kbit/s = (B/s * 8) / 1000.
*-------------------------------------------------

ComputeRate
         stz   BytesPerSecond
         stz   BytesPerSecond+2
         stz   KbitPerSecond
         stz   KbitPerSecond+2

         lda   ElapsedTicks
         ora   ElapsedTicks+2
         beq   RateDone

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

RateDone
         rts

*-------------------------------------------------
* Reports
*-------------------------------------------------

PrintTestReport
         jsr   ComputeTransferredBytes

         PushLong #BlocksOKMsg
         _WriteCString
         lda   SuccessfulBlocks
         sta   MetricValue
         stz   MetricValue+2
         jsr   PrintMetricDecimal

         PushLong #BytesMsg
         _WriteCString
         lda   BytesTransferred
         sta   MetricValue
         lda   BytesTransferred+2
         sta   MetricValue+2
         jsr   PrintMetricDecimal

         PushLong #TicksMsg
         _WriteCString
         lda   ElapsedTicks
         sta   MetricValue
         lda   ElapsedTicks+2
         sta   MetricValue+2
         jsr   PrintMetricDecimal
         jsr   WriteCRLF

         PushLong #BpsMsg
         _WriteCString
         lda   BytesPerSecond
         sta   MetricValue
         lda   BytesPerSecond+2
         sta   MetricValue+2
         jsr   PrintMetricDecimal

         PushLong #KbitMsg
         _WriteCString
         lda   KbitPerSecond
         sta   MetricValue
         lda   KbitPerSecond+2
         sta   MetricValue+2
         jsr   PrintMetricDecimal
         jsr   WriteCRLF
         jsr   WriteCRLF
         rts

PrintReadFailure
         PushLong #ReadFailureMsg
         _WriteCString
         lda   LastError
         jsr   WriteHexWord

         PushLong #FailureBlocksMsg
         _WriteCString
         lda   SuccessfulBlocks
         sta   MetricValue
         stz   MetricValue+2
         jsr   PrintMetricDecimal

         PushLong #FailureTicksMsg
         _WriteCString
         lda   ElapsedTicks
         sta   MetricValue
         lda   ElapsedTicks+2
         sta   MetricValue+2
         jsr   PrintMetricDecimal
         jsr   WriteCRLF
         rts

ComputeTransferredBytes
         lda   SuccessfulBlocks
         sta   BytesTransferred
         stz   BytesTransferred+2

         ldx   #9
ByteShiftLoop
         asl   BytesTransferred
         rol   BytesTransferred+2
         dex
         bne   ByteShiftLoop
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
* Shutdown
*-------------------------------------------------

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
* GS/OS parameter blocks
*-------------------------------------------------

QuitPB
         dw    0

proGETPREFIX
         dw    2
         dw    1
         adrl  pfxOPEN

proDINFO
         dw    8
         ds    2
         adrl  devOPEN
         ds    2
         ds    4
         ds    2
         ds    2
         ds    2
         ds    2

proDREAD
         dw    6
         ds    2
         adrl  ReadBuffer
         adrl  $00000200
         ds    4
         dw    512
         ds    4

proVOLUME
         dw    6
         adrl  devNAMEopen
         adrl  volOPEN
         ds    4
         ds    4
         ds    2
         ds    2

*-------------------------------------------------
* Class-one GS/OS string buffers
*-------------------------------------------------

devOPEN
         dw    $0032
devNAMEopen
         db    $00
devNAMEopen1
         db    $00
devNAMEopen2
         ds    $30

pfxOPEN
         dw    $00C2
pfxNAMEopen
         db    $00
pfxNAMEopen1
         db    $00
pfxNAMEopen2
         ds    $C0

volOPEN
         dw    $0032
volNAMEopen
         db    $00
volNAMEopen1
         db    $00
volNAMEopen2
         ds    $30

*-------------------------------------------------
* State
*-------------------------------------------------

TLStarted      ds    2
MMStarted      ds    2
MTStarted      ds    2
TextStarted    ds    2
IMStarted      ds    2

AppID          ds    2
MyID           ds    2

TestStartBlock ds    4
TestBlockCount ds    2
TestNumerator  ds    4
RemainingBlocks ds  2
SuccessfulBlocks ds 2

CurrentTick    ds    4
StartTick      ds    4
ElapsedTicks   ds    4

BytesTransferred ds 4
BytesPerSecond ds    4
KbitPerSecond  ds    4
RateWork       ds    4
MetricValue    ds    4

LastError      ds    2
HexValue       ds    2
DecimalBuffer  ds    16

ReadBuffer     ds    512

*-------------------------------------------------
* Text
*-------------------------------------------------

BannerMsg
         asc   'SPBENCH P0.1A - GS/OS DRead baseline'0d
         asc   'FujiNet/SmartPort 512-byte sequential reads'0d
         asc   'Timing source: Misc Tool GetTick, 60 Hz'0d0d00

DeviceMsg
         asc   'Device=$'00
SlotMsg
         asc   '  Slot=$'00
UnitMsg
         asc   '  Unit=$'00
BlocksMsg
         asc   '  Blocks='00

WarmupMsg
         asc   'Warm-up: 256 blocks / 128 KiB ... '00
WarmupDoneMsg
         asc   'done'0d0d00

Test1Msg
         asc   'TEST 1: 2048 blocks / 1 MiB'0d00
Test4Msg
         asc   'TEST 2: 8192 blocks / 4 MiB'0d00

BlocksOKMsg
         asc   '  blocks='00
BytesMsg
         asc   '  bytes='00
TicksMsg
         asc   '  ticks='00
BpsMsg
         asc   '  bytes/sec='00
KbitMsg
         asc   '  kbit/sec='00

FindDeviceErrMsg
         asc   'Unable to identify prefix block device. error=$'00
SmallDeviceMsg
         asc   'Device is smaller than required test range. error=$'00
ReadFailureMsg
         asc   'DRead failed. error=$'00
FailureBlocksMsg
         asc   '  completed blocks='00
FailureTicksMsg
         asc   '  elapsed ticks='00

AllDoneMsg
         asc   'Baseline run complete.'0d00
ExitMsg
         asc   'Press any key to return to GS/OS.'0d00
CRLFMsg
         asc   0d00

* END
