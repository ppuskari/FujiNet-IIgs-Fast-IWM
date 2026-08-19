*
* IWMPROBE P0.2A
*
* Apple IIgs IWM mode-register probe.
*
* Safely proves host-side control of IWM mode bit 3
* (4 us -> 2 us bit cells) without transferring data
* while fast mode is active.
*

         lst   off
         rel
         typ   S16
         dsk   IWMPROBE.L
         lst   off

         use   4/Int.Macs
         use   4/Locator.Macs
         use   4/Mem.Macs
         use   4/Misc.Macs
         use   4/Text.Macs

         mx    %00

GSOS           equ   $E100A8
QuitCall       equ   $2029

IWM_MOTOR_OFF  equ   $00C0E8
IWM_Q6_ON      equ   $00C0ED
IWM_Q7_OFF     equ   $00C0EE
IWM_Q7_ON      equ   $00C0EF
IWM_MODE_MASK  equ   $001F
IWM_FAST_BIT   equ   $0008
ModeWaitTicks  equ   $0046
SettleTicks    equ   $0002

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
         stz   InitialStatus
         stz   InitialMode
         stz   CurrentStatus
         stz   CurrentMode
         stz   DesiredMode

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
         lda   CurrentStatus
         sta   InitialStatus
         lda   CurrentMode
         sta   InitialMode

         PushLong #InitialMsg
         _WriteCString
         lda   InitialStatus
         jsr   WriteHexWord
         PushLong #ModeMsg
         _WriteCString
         lda   InitialMode
         jsr   WriteHexWord
         jsr   WriteCRLF

         PushLong #TimerMsg
         _WriteCString
         jsr   ArmModeWrite
         lda   #ModeWaitTicks
         jsr   WaitTicks16
         PushLong #DoneMsg
         _WriteCString

         lda   InitialMode
         ora   #IWM_FAST_BIT
         and   #IWM_MODE_MASK
         sta   DesiredMode

         PushLong #FastRequestMsg
         _WriteCString
         lda   DesiredMode
         jsr   WriteHexWord
         jsr   WriteCRLF

         jsr   WriteIWMMode
         lda   #SettleTicks
         jsr   WaitTicks16
         jsr   ReadIWMMode

         PushLong #FastResultMsg
         _WriteCString
         lda   CurrentStatus
         jsr   WriteHexWord
         PushLong #ModeMsg
         _WriteCString
         lda   CurrentMode
         jsr   WriteHexWord
         jsr   WriteCRLF

         lda   CurrentMode
         and   #IWM_FAST_BIT
         beq   FastBitRejected

         PushLong #FastOKMsg
         _WriteCString
         bra   BeginRestore

FastBitRejected
         PushLong #FastFailMsg
         _WriteCString

BeginRestore
* Always restore the exact low five mode bits captured
* before the experiment, even if the fast write failed.

         lda   InitialMode
         and   #IWM_MODE_MASK
         sta   DesiredMode

         PushLong #RestoreRequestMsg
         _WriteCString
         lda   DesiredMode
         jsr   WriteHexWord
         jsr   WriteCRLF

         jsr   WriteIWMMode
         lda   #SettleTicks
         jsr   WaitTicks16
         jsr   ReadIWMMode
         jsr   PrintRestoreStatus

         lda   CurrentMode
         cmp   InitialMode
         beq   RestoreOK

* If the one-second timer prevented the immediate
* restore, re-arm motor-off, wait, and retry once.

         PushLong #RestoreRetryMsg
         _WriteCString
         jsr   ArmModeWrite
         lda   #ModeWaitTicks
         jsr   WaitTicks16
         jsr   WriteIWMMode
         lda   #SettleTicks
         jsr   WaitTicks16
         jsr   ReadIWMMode
         jsr   PrintRestoreStatus

         lda   CurrentMode
         cmp   InitialMode
         beq   RestoreOK

         PushLong #RestoreFailMsg
         _WriteCString
         bra   WaitAndQuit

RestoreOK
         PushLong #RestoreOKMsg
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
* IWM mode/status access
*
* Hardware reference states:
*   Q6=1, Q7=0 -> Status register read
*   motor off, Q6=1, Q7=1 -> Mode register write
*
* Mode register low five bits are reflected in status.
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

ArmModeWrite
         php
         sei
         sep   #$20
         lda   >IWM_MOTOR_OFF
         rep   #$20
         plp
         rts

WriteIWMMode
         php
         sei
         sep   #$20

         lda   >IWM_MOTOR_OFF
         lda   >IWM_Q6_ON
         lda   DesiredMode
         sta   >IWM_Q7_ON

* Leave Q7 deasserted after the write.
         lda   >IWM_Q7_OFF

         rep   #$20
         plp
         rts

*-------------------------------------------------
* 60 Hz timing helper
*-------------------------------------------------

WaitTicks16
         sta   WaitCount
         jsr   ReadSystemTick
         lda   CurrentTick
         sta   WaitStart

WaitTickLoop
         jsr   ReadSystemTick
         lda   CurrentTick
         sec
         sbc   WaitStart
         cmp   WaitCount
         bcc   WaitTickLoop
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
* Reports
*-------------------------------------------------

PrintRestoreStatus
         PushLong #RestoreResultMsg
         _WriteCString
         lda   CurrentStatus
         jsr   WriteHexWord
         PushLong #ModeMsg
         _WriteCString
         lda   CurrentMode
         jsr   WriteHexWord
         jsr   WriteCRLF
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
* GS/OS parameter block
*-------------------------------------------------

QuitPB
         dw    0

*-------------------------------------------------
* State
*-------------------------------------------------

TLStarted      ds    2
MMStarted      ds    2
MTStarted      ds    2
TextStarted    ds    2
IMStarted      ds    2
AppID          ds    2

InitialStatus  ds    2
InitialMode    ds    2
CurrentStatus  ds    2
CurrentMode    ds    2
DesiredMode    ds    2

CurrentTick    ds    4
WaitStart      ds    2
WaitCount      ds    2
HexValue       ds    2

*-------------------------------------------------
* Text
*-------------------------------------------------

BannerMsg
         asc   'IWMPROBE P0.2A - IIgs IWM mode control'0d
         asc   'Probe only: no disk I/O while FAST is active'0d
         asc   'IWM bit 3: 0=4us  1=2us'0d0d00

InitialMsg
         asc   'Initial: status=$'00
ModeMsg
         asc   ' mode=$'00
TimerMsg
         asc   'Motor off; waiting 70 ticks for mode-write timer ... '00
DoneMsg
         asc   'done'0d00
FastRequestMsg
         asc   'FAST request mode=$'00
FastResultMsg
         asc   'After FAST: status=$'00
FastOKMsg
         asc   'FAST BIT SET - host can select 2us cells.'0d0d00
FastFailMsg
         asc   'FAST BIT DID NOT SET.'0d0d00
RestoreRequestMsg
         asc   'Restore request mode=$'00
RestoreResultMsg
         asc   'After restore: status=$'00
RestoreRetryMsg
         asc   'Restore mismatch; waiting 70 ticks and retrying...'0d00
RestoreOKMsg
         asc   'RESTORE OK - original IWM mode is back.'0d0d00
RestoreFailMsg
         asc   'RESTORE FAILED - do not access disks; reboot now.'0d0d00
ExitMsg
         asc   'Press any key to return to GS/OS.'0d00
CRLFMsg
         asc   0d00
