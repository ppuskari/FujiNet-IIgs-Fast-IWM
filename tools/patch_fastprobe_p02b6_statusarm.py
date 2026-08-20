from pathlib import Path
import argparse


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f'Expected {label} pattern not found.')
    return text.replace(old, new, 1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Patch FASTPROBE P0.2B into P0.2B6 STATUS-$AA armed autosend test.'
    )
    parser.add_argument('--project-root', default='.')
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    src = root / 'iigs' / 'fastprobe' / 'src' / 'FastProbe.s'
    if not src.is_file():
        raise SystemExit(f'FASTPROBE source not found: {src}')

    text = src.read_text(encoding='utf-8')
    if 'FASTPROBE P0.2B6' in text:
        print('FASTPROBE P0.2B6 patch already applied.')
        return
    if 'FASTPROBE P0.2B' not in text:
        raise SystemExit('Expected FASTPROBE P0.2B baseline source.')

    text = replace_once(
        text,
        '* FASTPROBE P0.2B\n',
        '* FASTPROBE P0.2B6\n',
        'version header',
    )

    text = replace_once(
        text,
        '* First private IIgs/FujiNet Fast-IWM wire experiment.\n',
        '* Standard-SmartPort-arm + delayed private 2-us wire experiment.\n',
        'description header',
    )

    text = replace_once(
        text,
        'ByteTimeout    equ   $6000\n\nErrModeNotFast',
        'ByteTimeout    equ   $6000\n\n'
        'EmulStack      equ   $010100\n'
        'RawThunkAttr   equ   $C001\n\n'
        'ErrArmNoBank0  equ   $F205\n'
        'ErrArmBadBank0 equ   $F206\n'
        'ErrArmNotSP    equ   $F207\n\n'
        'ErrModeNotFast',
        'arm helper constants',
    )

    text = replace_once(
        text,
        '         stz   LastError\n\n         _TLStartUp',
        '         stz   LastError\n'
        '         stz   ArmHandle\n'
        '         stz   ArmHandle+2\n'
        '         stz   ArmCodePtr\n'
        '         stz   ArmCodePtr+2\n'
        '         stz   ArmStatusCount\n\n'
        '         _TLStartUp',
        'startup raw-arm state',
    )

    text = replace_once(
        text,
        '         pla\n         sta   AppID\n         lda   #1\n         sta   MMStarted\n',
        '         pla\n'
        '         sta   AppID\n'
        '         ora   #$0100\n'
        '         sta   MyID\n'
        '         lda   #1\n'
        '         sta   MMStarted\n',
        'Memory Manager application ID',
    )

    start = text.index('ModeFast\n')
    end = text.index('WaitAndQuit\n', start)
    replacement = '''ModeFast
         PushLong #ArmPrepMsg
         _WriteCString

         jsr   PrepareArmSmartPort
         bcc   ArmPrepared

         sta   LastError
         PushLong #ArmPrepFailMsg
         _WriteCString
         lda   LastError
         jsr   WriteHexWord
         jsr   WriteCRLF
         brl   WaitAndQuit

ArmPrepared
         PushLong #ArmCallMsg
         _WriteCString

* Standard SmartPort STATUS $AA.  FujiNet returns its ordinary
* HELLO WORLD response at 4-us timing and arms one delayed 2-us
* packet.  This ROM transaction is the only negotiation required.
ArmSmartPortCall
         jsl   $000000
         bcc   ArmCallOK

         sta   LastError
         PushLong #ArmCallFailMsg
         _WriteCString
         lda   LastError
         jsr   WriteHexWord
         jsr   WriteCRLF
         brl   WaitAndQuit

ArmCallOK
         PushLong #ArmOKMsg
         _WriteCString
         lda   ArmStatusCount
         jsr   WriteHexWord
         jsr   WriteCRLF

* Confirm that after the ordinary ROM SmartPort transaction returns,
* the shared IWM is back in the observed idle state with bit 3 set.
         jsr   ReadIWMMode
         PushLong #AfterArmModeMsg
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
         bne   ArmModeFast

         lda   #ErrModeNotFast
         sta   LastError
         PushLong #ModeAbortMsg
         _WriteCString
         brl   WaitAndQuit

ArmModeFast
         PushLong #AutoReceiveMsg
         _WriteCString

* FujiNet sends automatically 20 ms after the STATUS $AA arm.
* No undocumented phase signature and no second ROM call occur here.
         jsr   ReadFastPacket
         bcc   SingleReceived

         lda   #ErrByteTimeout
         sta   LastError
         PushLong #PacketFailMsg
         _WriteCString
         brl   WaitAndQuit

SingleReceived
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
         PushLong #B6DoneMsg
         _WriteCString
         brl   WaitAndQuit

'''
    text = text[:start] + replacement + text[end:]

    # The B6 packet is timer-driven by FujiNet after a legal STATUS call.
    # Remove the old private PH0 request/deassert accesses from the receive path.
    text = replace_once(
        text,
        '''ReadFastPacket
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
''',
        '''ReadFastPacket
* P0.2B6: FujiNet was armed by a legal SmartPort STATUS $AA call and
* will transmit after a 20-ms delay.  Enter IWM Read-Data state and
* wait directly for the marker; do not manipulate private phase codes.

         php
         sei
         sep   #$20

         lda   >IWM_Q7_OFF
         lda   >IWM_Q6_OFF
         lda   >IWM_Q6_OFF

         ldx   #MarkerScan
''',
        'timer-driven ReadFastPacket entry',
    )

    text = replace_once(
        text,
        '''* PH0 low returns 1111 -> 1110, arming the next packet.
         lda   >IWM_PH0_OFF
         rep   #$20
         plp
         clc
         rts

FastPacketTimeout8
         lda   >IWM_PH0_OFF
         rep   #$20
''',
        '''         rep   #$20
         plp
         clc
         rts

FastPacketTimeout8
         rep   #$20
''',
        'remove private PH0 deasserts',
    )

    # Insert the standard SmartPort arm helper before the obsolete private
    # phase routines.  Keeping the old routines assembled is harmless; B6
    # simply never calls them.
    anchor = '*-------------------------------------------------\n* Private Fast-IWM phase/ACK protocol.\n*-------------------------------------------------\n\n'
    helper = r'''*-------------------------------------------------
* Standard SmartPort STATUS $AA arm helper.
*
* The current experiment is deliberately fixed to the proven FujiNet
* slot-5/unit-1 setup.  C5FF is still read and the dispatcher is derived
* normally; the standard STATUS parameter list and return buffer are
* copied with the helper into Memory Manager-owned bank $00 RAM.
*-------------------------------------------------

PrepareArmSmartPort
         sep   #$20

         lda   >$00C501
         cmp   #$20
         bne   ArmNotSmartPort8
         lda   >$00C503
         cmp   #$00
         bne   ArmNotSmartPort8
         lda   >$00C505
         cmp   #$03
         bne   ArmNotSmartPort8
         lda   >$00C507
         cmp   #$00
         bne   ArmNotSmartPort8

         lda   >$00C5FF
         sta   ArmCnFF
         rep   #$20

         lda   ArmCnFF
         and   #$00FF
         clc
         adc   #$C503
         sta   ArmDispatch

         jsr   AllocateArmThunk
         bcs   ArmPrepareFail

* Patch source template fields using the actual bank-zero allocation,
* then copy the complete helper/list/buffer region.
         lda   ArmDispatch
         sta   ArmThunkDispatch+1

         lda   ArmCodePtr
         clc
         adc   #ArmCmdListTemplate-ArmThunkTemplate
         sta   ArmThunkCmdPtr

         lda   ArmCodePtr
         clc
         adc   #ArmStatusBuffer-ArmThunkTemplate
         sta   ArmStatusPtrTemplate

         sep   #$20
         lda   #$01
         sta   ArmUnitTemplate
         rep   #$20

         PushLong #ArmThunkTemplate
         PushLong ArmCodePtr
         pea   $0000
         pea   ArmRegionSize
         _BlockMove

         lda   ArmCodePtr
         sta   ArmSmartPortCall+1
         sep   #$20
         lda   ArmCodePtr+2
         sta   ArmSmartPortCall+3
         rep   #$20

         clc
         rts

ArmNotSmartPort8
         rep   #$20
         lda   #ErrArmNotSP
         sec
         rts

ArmPrepareFail
         sec
         rts

AllocateArmThunk
         pha
         pha
         pea   $0000
         pea   ArmRegionSize
         PushWord MyID
         PushWord #RawThunkAttr
         PushLong #0
         _NewHandle
         bcc   ArmHandleAllocated

         pla
         pla
         lda   #ErrArmNoBank0
         sec
         rts

ArmHandleAllocated
         phd
         tsc
         tcd

         lda   [3]
         sta   ArmCodePtr
         ldy   #2
         lda   [3],y
         sta   ArmCodePtr+2
         pld

         ply
         sty   ArmHandle
         plx
         stx   ArmHandle+2

         lda   ArmCodePtr+2
         and   #$00FF
         beq   ArmHandleGood

         PushLong ArmHandle
         _DisposeHandle
         stz   ArmHandle
         stz   ArmHandle+2
         stz   ArmCodePtr
         stz   ArmCodePtr+2

         lda   #ErrArmBadBank0
         sec
         rts

ArmHandleGood
         clc
         rts

'''
    if anchor not in text:
        raise SystemExit('Unable to locate private-protocol insertion anchor.')
    text = text.replace(anchor, helper + anchor, 1)

    # Dispose the bank-zero helper before shutting down Memory Manager.
    text = replace_once(
        text,
        'ShutTools\n         lda   IMStarted\n',
        '''ShutTools
         lda   ArmHandle
         ora   ArmHandle+2
         beq   ArmAlreadyDisposed
         PushLong ArmHandle
         _DisposeHandle
         stz   ArmHandle
         stz   ArmHandle+2
         stz   ArmCodePtr
         stz   ArmCodePtr+2
ArmAlreadyDisposed
         lda   IMStarted
''',
        'arm helper shutdown',
    )

    # Insert bank-zero helper image before state storage.
    state_anchor = '*-------------------------------------------------\n* State\n*-------------------------------------------------\n\n'
    thunk = r'''*-------------------------------------------------
* Bank-zero standard SmartPort STATUS helper image.
*-------------------------------------------------

ArmThunkTemplate
         php
         phd
         phb
         rep   #$30

         tsc
         tax
         and   #$FF00
         cmp   #$0100
         beq   ArmThunkStackReady

         sep   #$20
         lda   >EmulStack
         rep   #$20
         and   #$00FF
         ora   #$0100
         tcs

ArmThunkStackReady
         phx
         lda   #$0000
         tcd
         phk
         plb

         sec
         xce
         cld

ArmThunkDispatch
         jsr   $FFFF
         db    $00
ArmThunkCmdPtr
         dw    $FFFF

         bcc   ArmThunkSuccess
         tay
         bra   ArmThunkResultReady

ArmThunkSuccess
* STATUS returns transferred byte count in X(low)/Y(high).
         txa
         sta   >ArmStatusCount
         tya
         sta   >ArmStatusCount+1
         ldy   #$00

ArmThunkResultReady
         clc
         xce
         rep   #$30

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

         tya
         and   #$00FF
         beq   ArmThunkReturnOK
         sec
         rtl

ArmThunkReturnOK
         clc
         rtl

ArmThunkEnd

ArmCmdListTemplate
         db    $03
ArmUnitTemplate
         db    $01
ArmStatusPtrTemplate
         dw    $0000
ArmStatusCodeTemplate
         db    $AA

ArmStatusBuffer
         ds    16

ArmRegionEnd
ArmRegionSize  equ   ArmRegionEnd-ArmThunkTemplate

'''
    if state_anchor not in text:
        raise SystemExit('Unable to locate state insertion anchor.')
    text = text.replace(state_anchor, thunk + state_anchor, 1)

    text = replace_once(
        text,
        'AppID          ds    2\n\nCurrentStatus',
        'AppID          ds    2\n'
        'MyID           ds    2\n'
        'ArmHandle      ds    4\n'
        'ArmCodePtr     ds    4\n'
        'ArmDispatch    ds    2\n'
        'ArmCnFF        ds    2\n'
        'ArmStatusCount ds    2\n\n'
        'CurrentStatus',
        'arm helper state',
    )

    text = replace_once(
        text,
        "BannerMsg\n         asc   'FASTPROBE P0.2B - private Fast-IWM wire test'0d\n"
        "         asc   'No ROM SmartPort calls during the fast packet'0d\n"
        "         asc   'FujiNet responder required; TX target = 2us cells'0d0d00\n",
        "BannerMsg\n"
        "         asc   'FASTPROBE P0.2B6 - STATUS-arm Fast-IWM test'0d\n"
        "         asc   'Legal SmartPort STATUS $AA arms one delayed packet'0d\n"
        "         asc   'Fast payload uses direct IWM read; TX target=2us'0d0d00\n",
        'screen banner',
    )

    text = replace_once(
        text,
        "SingleMsg\n         asc   'Single 512-byte fast packet + pattern verify ... '00\n",
        "SingleMsg\n         asc   'Single 512-byte fast packet + pattern verify ... '00\n"
        "ArmPrepMsg\n         asc   'Preparing standard SmartPort STATUS $AA arm ... '00\n"
        "ArmPrepFailMsg\n         asc   'FAILED setup error=$'00\n"
        "ArmCallMsg\n         asc   'Arming FujiNet via standard STATUS $AA ... '00\n"
        "ArmCallFailMsg\n         asc   'FAILED SmartPort error=$'00\n"
        "ArmOKMsg\n         asc   'OK bytes=$'00\n"
        "AfterArmModeMsg\n         asc   'After STATUS arm: status=$'00\n"
        "AutoReceiveMsg\n         asc   'Waiting for delayed 2us packet ... '00\n"
        "B6DoneMsg\n         asc   'STATUS-arm 2us single-packet proof complete.'0d0d00\n",
        'B6 messages',
    )

    required = (
        'FASTPROBE P0.2B6',
        'PrepareArmSmartPort',
        'ArmSmartPortCall',
        'ArmThunkTemplate',
        'ArmStatusCodeTemplate',
        'db    $AA',
        'Waiting for delayed 2us packet',
    )
    for marker in required:
        if marker not in text:
            raise SystemExit(f'Missing required B6 host marker: {marker}')

    src.write_text(text, encoding='utf-8', newline='\n')
    print('Applied FASTPROBE P0.2B6 standard STATUS $AA arm + delayed receive patch.')


if __name__ == '__main__':
    main()
