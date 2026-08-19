*
* SPBENCH P0.1B
*
* Apple IIgs FujiNet direct SmartPort benchmark.
*
* P0.1B keeps the P0.1A transfer sizes and GetTick
* timing, but removes GS/OS DRead from the timed path.
* It calls the Apple IIgs SmartPort firmware dispatcher
* directly with extended READBLOCK command $41.
*
* The main S16 application remains in native mode.
* A tiny fixed/locked helper is allocated in bank $00,
* copied there, and entered with JSL for each SmartPort
* call.  The helper conditions the IIgs environment for
* 6502-compatible firmware, issues the JSR dispatcher
* call, then restores the native environment.
*
* Launch this program from the FujiNet-mounted SPBENCH
* ProDOS image.  It identifies the block device that
* owns prefix 1, obtains slot/unit information, locates
* the SmartPort dispatcher, warms with 256 block reads,
* then measures 1 MiB and 4 MiB sequential transfers.
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
QuitCall       equ   $2029

BlockDeviceBit equ   $0080
NoMoreDevices  equ   $0011
ProDOSFSID     equ   $0001
BlockSize      equ   $0200

ErrShortRead   equ   $FF01
ErrNoDevice    equ   $FF02
ErrSmallDevice equ   $FF03
ErrNoBankZero  equ   $FF04
ErrNotSmartPort equ  $FF05
ErrBadBankZero equ   $FF06

WarmStart      equ   $0000
WarmBlocks     equ   $0100
Test1Start     equ   $0400
Test1Blocks    equ   $0800
Test4Start     equ   $1000
Test4Blocks    equ   $2000
MinBlocks      equ   $3000

TextTool       equ   $000C
EmulStack      equ   $010100
RawThunkAttr   equ   $C001

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
         stz   RawHandle
         stz   RawHandle+2
         stz   RawCodePtr
         stz   RawCodePtr+2
         stz   RawTransferCount

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

         jsr   PrepareRawSmartPort
         bcc   RawSmartPortReady

         sta   LastError
         PushLong #RawSetupErrMsg
         _WriteCString
         lda   LastError
         jsr   WriteHexWord
         jsr   WriteCRLF
         brl   WaitAndQuit

RawSmartPortReady
         jsr   PrintRawInfo

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
* GS/OS is used only for discovery.  No DRead call is
* present in the timed transport path.
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

* Device found.  Preserve the SmartPort unit byte in
* the extended command list.

         sep   #$20
         lda   proDINFO+$10
         sta   RawCmdUnit
         rep   #$20

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
* Locate and prepare direct SmartPort firmware.
*-------------------------------------------------

PrepareRawSmartPort
* X = slot * $100 for long indexed reads of $Cnxx.

         lda   proDINFO+$0E
         and   #$00FF
         xba
         tax
         sta   SlotPageOffset

* Verify the standard ProDOS/SmartPort signature:
* Cn01=$20, Cn03=$00, Cn05=$03, Cn07=$00.

         sep   #$20

         lda   >$00C001,x
         cmp   #$20
         bne   NotSmartPort8

         lda   >$00C003,x
         cmp   #$00
         bne   NotSmartPort8

         lda   >$00C005,x
         cmp   #$03
         bne   NotSmartPort8

         lda   >$00C007,x
         cmp   #$00
         bne   NotSmartPort8

* CnFF is the offset to the ProDOS block entry.
* SmartPort dispatcher = $Cn00 + CnFF + 3.

         lda   >$00C0FF,x
         sta   DispatchOffset
         rep   #$20

         lda   SlotPageOffset
         clc
         adc   #$C003
         sta   DispatchAddress

         lda   DispatchOffset
         and   #$00FF
         clc
         adc   DispatchAddress
         sta   DispatchAddress

         jsr   AllocateRawThunk
         bcs   RawPrepareFail

* Patch only the JSR target in the source image.
* The extended command list uses a four-byte pointer,
* so its compiled address remains valid after the
* helper itself is copied to bank $00.

         lda   DispatchAddress
         sta   ThunkDispatch+1

         PushLong #ThunkTemplate
         PushLong RawCodePtr
         PushLong #ThunkSize
         _BlockMove

* Patch the application's long call to the allocated
* bank-zero helper.

         lda   RawCodePtr
         sta   RawSmartPortCall+1

         sep   #$20
         lda   RawCodePtr+2
         sta   RawSmartPortCall+3
         rep   #$20

         clc
         rts

NotSmartPort8
         rep   #$20
         lda   #ErrNotSmartPort
         sec
         rts

RawPrepareFail
         sec
         rts

*-------------------------------------------------
* Allocate tiny fixed/locked bank-zero helper.
*
* The stack dereference pattern is the standard IIgs
* technique for obtaining both a handle and its data
* pointer after NewHandle.
*-------------------------------------------------

AllocateRawThunk
         pha
         pha
         PushLong #ThunkSize
         PushWord MyID
         PushWord #RawThunkAttr
         PushLong #0
         _NewHandle
         bcc   RawHandleAllocated

         pla
         pla
         lda   #ErrNoBankZero
         sec
         rts

RawHandleAllocated
         phd
         tsc
         tcd

         lda   [3]
         sta   RawCodePtr

         ldy   #2
         lda   [3],y
         sta   RawCodePtr+2

         pld

         ply
         sty   RawHandle
         plx
         stx   RawHandle+2

* C001 + location zero requests bank $00.  Refuse to
* execute the helper if Memory Manager returned any
* other bank.

         lda   RawCodePtr+2
         and   #$00FF
         beq   RawHandleGood

         PushLong RawHandle
         _DisposeHandle
         stz   RawHandle
         stz   RawHandle+2
         stz   RawCodePtr
         stz   RawCodePtr+2

         lda   #ErrBadBankZero
         sec
         rts

RawHandleGood
         clc
         rts

*-------------------------------------------------
* Print selected device and raw firmware information.
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
         rts

PrintRawInfo
         PushLong #DispatchMsg
         _WriteCString
         lda   DispatchAddress
         jsr   WriteHexWord

         PushLong #ThunkMsg
         _WriteCString
         lda   RawCodePtr+2
         jsr   WriteHexWord
         lda   RawCodePtr
         jsr   WriteHexWord

         PushLong #RawModeMsg
         _WriteCString
         jsr   WriteCRLF
         jsr   WriteCRLF
         rts

*-------------------------------------------------
* Run one timed sequential direct SmartPort test.
*
* TestStartBlock = 32-bit starting block
* TestBlockCount = number of 512-byte reads
*
* The timed loop issues no GS/OS calls and performs
* no screen output.
*-------------------------------------------------

RunTimedReadTest
         lda   TestStartBlock
         sta   CurrentBlock
         lda   TestStartBlock+2
         sta   CurrentBlock+2

         lda   TestBlockCount
         sta   RemainingBlocks
         stz   SuccessfulBlocks
         stz   LastError

         jsr   ReadSystemTick
         lda   CurrentTick
         sta   StartTick
         lda   CurrentTick+2
         sta   StartTick+2

RawReadLoop
         lda   CurrentBlock
         sta   RawCmdBlock
         lda   CurrentBlock+2
         sta   RawCmdBlock+2

RawSmartPortCall
         jsl   $000000
         bcc   RawReadReturned

         sta   LastError
         jsr   FinishTiming
         sec
         rts

RawReadReturned
* SmartPort ReadBlock reports bytes transferred in X/Y.
* The bank-zero helper records them as a 16-bit count.

         lda   RawTransferCount
         cmp   #BlockSize
         beq   RawTransferComplete

         lda   #ErrShortRead
         sta   LastError
         jsr   FinishTiming
         sec
         rts

RawTransferComplete
         inc   SuccessfulBlocks

         lda   CurrentBlock
         clc
         adc   #1
         sta   CurrentBlock
         lda   CurrentBlock+2
         adc   #0
         sta   CurrentBlock+2

         dec   RemainingBlocks
         bne   RawReadLoop

         jsr   FinishTiming
         clc
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
         lda   RawHandle
         ora   RawHandle+2
         beq   RawAlreadyDisposed

         PushLong RawHandle
         _DisposeHandle

         stz   RawHandle
         stz   RawHandle+2
         stz   RawCodePtr
         stz   RawCodePtr+2

RawAlreadyDisposed
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
* Bank-zero SmartPort helper image.
*
* This routine is copied to Memory Manager-owned bank
* $00 RAM.  The caller enters it with JSL, giving PBR
* $00.  It preserves caller P/D/DBR and native S.
*
* The SmartPort firmware requires:
*   decimal off
*   emulation mode
*   D=$0000
*   DBR=$00
*   PBR=$00
*   S=$01xx
*
* The extended command form places a four-byte pointer
* to RawCmdList inline after command $41, allowing the
* command list and 512-byte target buffer to remain in
* the normal S16 application bank.
*-------------------------------------------------

ThunkTemplate
         php
         phd
         phb
         rep   #$30

* Save native stack pointer in X.  If it is not already
* in page $01, switch temporarily to the system's saved
* emulation stack pointer.

         tsc
         tax
         and   #$FF00
         cmp   #$0100
         beq   ThunkStackReady

         sep   #$20
         lda   >EmulStack
         rep   #$20
         and   #$00FF
         ora   #$0100
         tcs

ThunkStackReady
         phx

* Establish 6502-compatible D and DBR while still in
* native mode, then enter emulation mode.

         lda   #$0000
         tcd
         phk
         plb

         sec
         xce
         cld

ThunkDispatch
         jsr   $FFFF
         db    $41
         adrl  RawCmdList

         bcc   ThunkSuccess
         tay
         bra   ThunkResultReady

ThunkSuccess
* ReadBlock returns the transferred byte count in X/Y.
* In emulation mode X is the low byte and Y is the high
* byte.  Save both directly into the application bank.

         txa
         sta   >RawTransferCount
         tya
         sta   >RawTransferCount+1
         ldy   #$00

ThunkResultReady
* Return to native mode.  XCE exchanges E into carry,
* so the SmartPort result has already been captured in
* Y before this point.

         clc
         xce
         rep   #$30

* Recover native S, then update the system emulation
* stack byte before leaving page $01.

         plx
         tsc
         sep   #$20
         sta   >EmulStack
         rep   #$20

         txa
         tcs

         plb
         pld
         plp

* Return A=0/C=0 for success or A=SmartPort error/C=1.

         tya
         and   #$00FF
         beq   ThunkReturnOK

         sec
         rtl

ThunkReturnOK
         clc
         rtl

ThunkEnd
ThunkSize      equ   ThunkEnd-ThunkTemplate

*-------------------------------------------------
* SmartPort extended READBLOCK parameter list.
*
* count=3, unit byte, 4-byte buffer pointer,
* 4-byte block number.
*-------------------------------------------------

RawCmdList
         db    $03
RawCmdUnit
         db    $00
         adrl  ReadBuffer
RawCmdBlock
         adrl  $00000000

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

RawHandle      ds    4
RawCodePtr     ds    4
SlotPageOffset ds    2
DispatchOffset ds    2
DispatchAddress ds   2
RawTransferCount ds 2

TestStartBlock ds    4
CurrentBlock   ds    4
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
         asc   'SPBENCH P0.1B - direct SmartPort baseline'0d
         asc   'Raw extended READBLOCK $41, 512 bytes/call'0d
         asc   'Timing source: Misc Tool GetTick, 60 Hz'0d0d00

DeviceMsg
         asc   'Device=$'00
SlotMsg
         asc   '  Slot=$'00
UnitMsg
         asc   '  Unit=$'00
BlocksMsg
         asc   '  Blocks='00

DispatchMsg
         asc   'SmartPort dispatch=$'00
ThunkMsg
         asc   '  bank0 thunk=$'00
RawModeMsg
         asc   '  mode=EXT $41'00

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
RawSetupErrMsg
         asc   'Direct SmartPort setup failed. error=$'00
ReadFailureMsg
         asc   'SmartPort READBLOCK failed. error=$'00
FailureBlocksMsg
         asc   '  completed blocks='00
FailureTicksMsg
         asc   '  elapsed ticks='00

AllDoneMsg
         asc   'Direct SmartPort baseline complete.'0d00
ExitMsg
         asc   'Press any key to return to GS/OS.'0d00
CRLFMsg
         asc   0d00

* END
