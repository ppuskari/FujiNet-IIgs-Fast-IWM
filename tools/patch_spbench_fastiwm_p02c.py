from pathlib import Path
import argparse


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f'Expected {label} pattern not found.')
    return text.replace(old, new, 1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Transform already-patched SPBENCH P0.1B3 into FASTPROBE P0.2C.'
    )
    parser.add_argument('--project-root', default='.')
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    src = root / 'iigs' / 'spbench' / 'src' / 'SPBench.s'
    if not src.is_file():
        raise SystemExit(f'SPBENCH source not found: {src}')

    text = src.read_text(encoding='utf-8')
    if 'FASTPROBE P0.2C' in text:
        print('FASTPROBE P0.2C host patch already applied.')
        return
    if 'SPBENCH P0.1B3' not in text:
        raise SystemExit('Apply the validated SPBENCH P0.1B3 standard SmartPort patch first.')

    # Constants for the normal SmartPort-enable trigger and direct IWM receive.
    const_anchor = 'RawThunkAttr   equ   $C001\n'
    const_insert = '''RawThunkAttr   equ   $C001

* P0.2C reserved arm block: 24-bit $7FA55A.
FastArmBlockLo  equ   $A55A
FastArmBlockHi  equ   $7F
FastPayload     equ   $0200
MarkerScan      equ   $0100
ByteTimeout     equ   $FFFF

IWM_PH0_OFF     equ   $00C0E0
IWM_PH0_ON      equ   $00C0E1
IWM_PH1_OFF     equ   $00C0E2
IWM_PH1_ON      equ   $00C0E3
IWM_PH2_OFF     equ   $00C0E4
IWM_PH2_ON      equ   $00C0E5
IWM_PH3_OFF     equ   $00C0E6
IWM_PH3_ON      equ   $00C0E7
IWM_Q6_OFF      equ   $00C0EC
IWM_Q7_OFF      equ   $00C0EE
'''
    text = replace_once(text, const_anchor, const_insert, 'RawThunkAttr constant')

    # Replace banner text only; the executable can still use the proven
    # SPBENCH source/link path internally.
    text = replace_once(
        text,
        "         asc   'SPBENCH P0.1B3 - standard SmartPort baseline'0d\n"
        "         asc   'Raw READBLOCK $01, bank0 512-byte stage'0d\n",
        "         asc   'FASTPROBE P0.2C - SmartPort-armed Fast-IWM'0d\n"
        "         asc   '4us arm READBLOCK then 2us one-shot response'0d\n",
        'B3 banner text',
    )

    # Divert execution after the proven device/dispatcher setup. The old
    # benchmark remains in the file but is unreachable in P0.2C.
    entry_old = '''RawSmartPortReady
         jsr   PrintRawInfo

* The 4 MiB test starts at block $1000 and consumes
'''
    entry_new = '''RawSmartPortReady
         jsr   PrintRawInfo

         jsr   RunFastArmTest
         brl   WaitAndQuit

* The original B3 throughput code remains below as an inactive reference.
* The 4 MiB test starts at block $1000 and consumes
'''
    text = replace_once(text, entry_old, entry_new, 'RawSmartPortReady entry')

    # Set the third block-number byte in the bank-zero command template before
    # BlockMove. The normal B3 timed tests kept it at zero.
    high_old = '''         sep   #$20
         lda   RawCmdUnit
         sta   RawCmdUnitTemplate
         rep   #$20

* Copy thunk + standard command list + 512-byte stage into bank zero.
'''
    high_new = '''         sep   #$20
         lda   RawCmdUnit
         sta   RawCmdUnitTemplate
         lda   #FastArmBlockHi
         sta   RawCmdBlockTemplate+2
         rep   #$20

* Copy thunk + standard command list + 512-byte stage into bank zero.
'''
    text = replace_once(text, high_old, high_new, 'bank-zero unit template patch')

    # Patch a second JSL used by the one-shot arm call.
    call_old = '''         lda   RawCodePtr
         sta   RawSmartPortCall+1

         sep   #$20
         lda   RawCodePtr+2
         sta   RawSmartPortCall+3
         rep   #$20
'''
    call_new = '''         lda   RawCodePtr
         sta   RawSmartPortCall+1
         sta   ArmSmartPortCall+1

         sep   #$20
         lda   RawCodePtr+2
         sta   RawSmartPortCall+3
         sta   ArmSmartPortCall+3
         rep   #$20
'''
    text = replace_once(text, call_old, call_new, 'raw SmartPort JSL patch')

    # Patch a second long store for the arm block low word.
    block_old = '''         lda   RawCodePtr
         clc
         adc   #RawCmdBlockTemplate-ThunkTemplate
         sta   RawBlockStore+1

         sep   #$20
         lda   #$00
         sta   RawBlockStore+3
         rep   #$20
'''
    block_new = '''         lda   RawCodePtr
         clc
         adc   #RawCmdBlockTemplate-ThunkTemplate
         sta   RawBlockStore+1
         sta   ArmBlockStore+1

         sep   #$20
         lda   #$00
         sta   RawBlockStore+3
         sta   ArmBlockStore+3
         rep   #$20
'''
    text = replace_once(text, block_old, block_new, 'raw block long-store patch')

    # Insert the entire P0.2C host experiment before the old B3 timed loop.
    routine_anchor = '''*-------------------------------------------------
* Run one timed sequential direct SmartPort test.
'''
    routine = r'''*-------------------------------------------------
* P0.2C one-shot SmartPort arm + normal-enable trigger.
*-------------------------------------------------

RunFastArmTest
         PushLong #FastArmMsg
         _WriteCString

         lda   #FastArmBlockLo
ArmBlockStore
         sta   >$000000

ArmSmartPortCall
         jsl   $000000
         bcc   FastArmReturned

         sta   LastError
         PushLong #FastArmFailMsg
         _WriteCString
         lda   LastError
         jsr   WriteHexWord
         jsr   WriteCRLF
         rts

FastArmReturned
         PushLong #FastArmOKMsg
         _WriteCString

         jsr   ReadFastPacketC
         bcc   FastPacketReceivedC

         PushLong #FastTimeoutMsg
         _WriteCString
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

* Enter the actual upstream SmartPort enable state 1010, configure the
* IWM Read-Data latch, then raise PH0 to produce 1011. The armed FujiNet
* firmware intercepts 1011 before its normal command-packet receive path.
* Keep interrupts disabled until the packet completes or times out.

ReadFastPacketC
         php
         sei
         sep   #$20

* PH3..PH0 = 1010.
         lda   >IWM_PH0_OFF
         lda   >IWM_PH2_OFF
         lda   >IWM_PH3_ON
         lda   >IWM_PH1_ON

* Q6=0/Q7=0: direct IWM Read-Data polling.
         lda   >IWM_Q7_OFF
         lda   >IWM_Q6_OFF
         lda   >IWM_Q6_OFF

* PH3..PH0 = 1011. This is the one-shot fast request.
         lda   >IWM_PH0_ON

         ldx   #MarkerScan

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

* M=8, X/Y remain 16-bit. A valid IWM byte has bit 7 set.
ReadIWMByteC
         ldy   #ByteTimeout
FastByteWaitC
         lda   >IWM_Q6_OFF
         bmi   FastByteReadyC
         dey
         bne   FastByteWaitC
         sec
         rts
FastByteReadyC
         clc
         rts

* Pulse the documented SmartPort reset state 0101, then leave phases low.
* M=8 on entry/return.
ResetFastBusC
         lda   >IWM_PH0_OFF
         lda   >IWM_PH1_OFF
         lda   >IWM_PH3_OFF
         lda   >IWM_PH2_ON
         lda   >IWM_PH0_ON

         ldy   #$0800
FastResetDelayC
         dey
         bne   FastResetDelayC

         lda   >IWM_PH0_OFF
         lda   >IWM_PH2_OFF
         rts

ValidateFastBufferC
         php
         sep   #$20
         ldx   #$0000
FastValidateLoopC
         txa
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

*-------------------------------------------------
* Run one timed sequential direct SmartPort test.
'''
    text = replace_once(text, routine_anchor, routine, 'timed test section anchor')

    # Add state immediately before the existing raw-state variables.
    state_anchor = '''RawHandle      ds    4
'''
    state_insert = '''FastPatternFail ds   2
FastBufferC     ds    512

RawHandle      ds    4
'''
    text = replace_once(text, state_anchor, state_insert, 'raw state block')

    # Add user-facing experiment messages before the existing CRLF string.
    msg_anchor = '''CRLFMsg
         asc   0d00
'''
    msg_insert = '''FastArmMsg
         asc   'Arm via standard READBLOCK $7FA55A ... '00
FastArmOKMsg
         asc   'ARM OK'0d00
FastArmFailMsg
         asc   'ARM SmartPort call failed. error=$'00
FastTimeoutMsg
         asc   'FAST FAILED: timeout waiting for 2us IWM stream.'0d00
FastPatternFailMsg
         asc   'FAST FAILED: payload mismatch at index $'00
FastPassMsg
         asc   'FAST PASS: exact 512-byte 2us payload verified.'0d00
CRLFMsg
         asc   0d00
'''
    text = replace_once(text, msg_anchor, msg_insert, 'CRLF message')

    required = (
        'FASTPROBE P0.2C',
        'FastArmBlockLo',
        'ArmSmartPortCall',
        'ArmBlockStore',
        'ReadFastPacketC',
        '0x',  # harmless generic source marker check below is not relied on
        'FastBufferC',
        "FAST PASS: exact 512-byte 2us payload verified.",
    )
    for item in required:
        if item not in text:
            raise SystemExit(f'Missing P0.2C host marker: {item}')

    src.write_text(text, encoding='utf-8', newline='\n')
    print('Applied FASTPROBE P0.2C SmartPort-arm host patch.')
    print('Arm block: $7FA55A; trigger states: 1010 -> 1011.')


if __name__ == '__main__':
    main()
