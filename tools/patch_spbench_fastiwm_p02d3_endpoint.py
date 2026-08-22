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
            'Add a regular-streamer-style provider host/port prompt and send '
            'the selected endpoint to FujiNet before starting P0.2D3.'
        )
    )
    parser.add_argument('--project-root', default='.')
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    base = root / 'tools' / 'patch_spbench_fastiwm_p02d2_softreturn.py'
    src = root / 'iigs' / 'spbench' / 'src' / 'SPBench.s'
    if not base.is_file() or not src.is_file():
        raise SystemExit('Missing P0.2D2 transform or SPBENCH source.')

    text = src.read_text(encoding='utf-8')
    if 'FASTPROBE P0.2D3' in text:
        print('FASTPROBE P0.2D3 endpoint overlay already applied.')
        return
    if 'FASTPROBE P0.2D2' not in text:
        subprocess.run(
            [sys.executable, str(base), '--project-root', str(root)],
            check=True,
        )
        text = src.read_text(encoding='utf-8')
    if 'FASTPROBE P0.2D2' not in text:
        raise SystemExit('P0.2D2 host transform did not apply.')

    text = replace_once(
        text,
        "         asc   'FASTPROBE P0.2D2 - reset-free provider stream'0d\n",
        "         asc   'FASTPROBE P0.2D3 - app-configured provider'0d\n",
        'D2 banner',
    )

    text = replace_once(
        text,
        '''D1ProviderStopBlockLo equ $A557
D1ProviderReadyBytes equ $4000
''',
        '''D1ProviderStopBlockLo equ $A557
D3ProviderConfigBlockLo equ $A556
D3DefaultPort equ   22510
D3ErrCancel   equ   $00FC
D3ErrInput    equ   $00FD
D1ProviderReadyBytes equ $4000
''',
        'provider constants',
    )

    text = replace_once(
        text,
        '''D0DOCPrepared
         PushLong #D0ReadyMsg
         _WriteCString
         PushLong #D1ConnectMsg
         _WriteCString
         jsr   RunProviderStreamD1
''',
        '''D0DOCPrepared
         PushLong #D0ReadyMsg
         _WriteCString

D3EndpointPrompt
         PushLong #D3EndpointPromptMsg
         _WriteCString
         jsr   PromptEndpointD3
         bcc   D3EndpointReady
         cmp   #D3ErrCancel
         beq   D3EndpointCancelled
         PushLong #D3EndpointInputErrorMsg
         _WriteCString
         brl   D3EndpointPrompt

D3EndpointCancelled
         brl   WaitAndQuit

D3EndpointReady
         jsr   BuildEndpointConfigD3
         jsr   SendEndpointConfigD3
         bcc   D3EndpointConfigured
         sta   LastError
         PushLong #D3EndpointSendErrorMsg
         _WriteCString
         lda   LastError
         jsr   WriteHexWord
         jsr   WriteCRLF
         brl   WaitAndQuit

D3EndpointConfigured
         PushLong #D1ConnectMsg
         _WriteCString
         jsr   RunProviderStreamD1
''',
        'D2 provider entry',
    )

    endpoint_routines = r'''
PromptEndpointD3
         PushLong #D3HostPromptMsg
         _WriteCString
         lda   #63
         ldx   #D3HostBuffer
         ldy   #^D3HostBuffer
         jsr   ReadTextLineD3
         bcc   D3HostLineReady
         rts

D3HostLineReady
         lda   D3HostBuffer
         and   #$00FF
         bne   D3HostValueReady
         jsr   CopyDefaultHostD3

D3HostValueReady
         PushLong #D3PortPromptMsg
         _WriteCString
         lda   #5
         ldx   #D3PortBuffer
         ldy   #^D3PortBuffer
         jsr   ReadTextLineD3
         bcc   D3PortLineReady
         rts

D3PortLineReady
         lda   D3PortBuffer
         and   #$00FF
         beq   D3UseDefaultPort
         brl   ParsePortNumberD3
D3UseDefaultPort
         lda   #D3DefaultPort
         sta   D3DestinationPort
         clc
         rts

CopyDefaultHostD3
         sep   #$20
         mx    %10
         ldx   #$0000
D3CopyDefaultHostLoop
         lda   D3DefaultHostPString,x
         sta   D3HostBuffer,x
         inx
         cpx   #$000E
         bcc   D3CopyDefaultHostLoop
         rep   #$20
         mx    %00
         rts

* Entry: A=max length, X=buffer low, Y=bank. The result is a Pascal
* string with a one-byte length. ESC returns D3ErrCancel with carry set.
ReadTextLineD3
         sta   D3InputMaxLength
         stx   D3InputStore+1
         stx   D3InputLengthStore+1
         sep   #$20
         mx    %10
         tya
         sta   D3InputStore+3
         sta   D3InputLengthStore+3
         rep   #$20
         mx    %00
         stz   D3InputLength

D3ReadTextChar
         PushWord #0
         PushWord #0
         _ReadChar
         pla
         and   #$007F
         cmp   #$000D
         beq   D3FinishTextLine
         cmp   #$001B
         beq   D3CancelTextLine
         cmp   #$0008
         beq   D3BackspaceTextLine
         cmp   #$007F
         beq   D3BackspaceTextLine
         cmp   #$0020
         bcc   D3ReadTextChar
         cmp   #$007F
         bcs   D3ReadTextChar
         ldx   D3InputLength
         cpx   D3InputMaxLength
         bcs   D3ReadTextChar
         sta   D3InputChar
         pha
         _WriteChar
         lda   D3InputChar
         ldx   D3InputLength
         inx
         sep   #$20
         mx    %10
D3InputStore
         sta   >$000000,x
         rep   #$20
         mx    %00
         inc   D3InputLength
         bra   D3ReadTextChar

D3BackspaceTextLine
         lda   D3InputLength
         beq   D3ReadTextChar
         dec   D3InputLength
         PushWord #$0008
         _WriteChar
         PushWord #$0020
         _WriteChar
         PushWord #$0008
         _WriteChar
         bra   D3ReadTextChar

D3CancelTextLine
         PushLong #CRLFMsg
         _WriteCString
         lda   #D3ErrCancel
         sec
         rts

D3FinishTextLine
         sep   #$20
         mx    %10
         lda   D3InputLength
D3InputLengthStore
         sta   >$000000
         rep   #$20
         mx    %00
         PushLong #CRLFMsg
         _WriteCString
         clc
         rts

ParsePortNumberD3
         stz   D3ParsedPort
         lda   D3PortBuffer
         and   #$00FF
         sta   D3ParseLength
         ldy   #1
D3ParsePortDigit
         sep   #$20
         mx    %10
         lda   D3PortBuffer,y
         rep   #$20
         mx    %00
         and   #$00FF
         cmp   #$0030
         bcc   D3BadPortNumber
         cmp   #$003A
         bcs   D3BadPortNumber
         sec
         sbc   #$0030
         sta   D3ParseDigit
         lda   D3ParsedPort
         cmp   #6553
         bcc   D3PortMultiply
         bne   D3BadPortNumber
         lda   D3ParseDigit
         cmp   #6
         bcs   D3BadPortNumber
D3PortMultiply
         lda   D3ParsedPort
         asl
         sta   D3ParseTimesTwo
         lda   D3ParsedPort
         asl
         asl
         asl
         clc
         adc   D3ParseTimesTwo
         adc   D3ParseDigit
         sta   D3ParsedPort
         iny
         dec   D3ParseLength
         bne   D3ParsePortDigit
         lda   D3ParsedPort
         beq   D3BadPortNumber
         sta   D3DestinationPort
         clc
         rts
D3BadPortNumber
         lda   #D3ErrInput
         sec
         rts

BuildEndpointConfigD3
         lda   D3HostBuffer
         and   #$00FF
         tax
         sep   #$20
         mx    %10
         lda   D3HostBuffer
         sta   D3EndpointConfig+5
         ldy   #$0000
D3CopyEndpointHost
         lda   D3HostBuffer+1,y
         sta   D3EndpointConfig+8,y
         iny
         dex
         bne   D3CopyEndpointHost
         rep   #$20
         mx    %00
         lda   D3DestinationPort
         sta   D3EndpointConfig+6
         rts

SendEndpointConfigD3
* Copy the D3EP command into the existing bank-zero stage, switch the copied
* SmartPort thunk to WRITEBLOCK for one private $7FA556 transaction, then
* restore READBLOCK before START/status/arm calls.
         PushLong #D3EndpointConfig
         PushLong RawStagePtr
         pea   $0000
         pea   $0200
         _BlockMove
         lda   #$0002
         jsr   SetSmartPortCommandD3
         lda   #D3ProviderConfigBlockLo
         jsr   CallProviderBlockD1
         php
         pha
         lda   #$0001
         jsr   SetSmartPortCommandD3
         pla
         plp
         rts

SetSmartPortCommandD3
         sep   #$20
D3CommandStore
         sta   >$000000
         rep   #$20
         rts

'''
    text = replace_once(
        text,
        '\nRunProviderStreamD1\n',
        endpoint_routines + 'RunProviderStreamD1\n',
        'provider controller anchor',
    )

    text = replace_once(
        text,
        '''         sta   ArmBlockStore+3
         rep   #$20

         clc
''',
        '''         sta   ArmBlockStore+3
         rep   #$20

* Patch the D3 application's one-byte command store to the copied thunk's
* inline SmartPort command byte. The helper normally remains READBLOCK $01.
         lda   RawCodePtr
         clc
         adc   #ThunkCommandTemplate-ThunkTemplate
         sta   D3CommandStore+1
         sep   #$20
         lda   #$00
         sta   D3CommandStore+3
         rep   #$20

         clc
''',
        'raw thunk patching',
    )

    text = replace_once(
        text,
        '''ThunkDispatch
         jsr   $FFFF
         db    $01
ThunkCmdPtr
''',
        '''ThunkDispatch
         jsr   $FFFF
ThunkCommandTemplate
         db    $01
ThunkCmdPtr
''',
        'SmartPort command template',
    )

    text = replace_once(
        text,
        '''D1ProviderStatus ds  32

RawHandle      ds    4
''',
        '''D1ProviderStatus ds  32
D3InputMaxLength ds 2
D3InputLength  ds    2
D3InputChar    ds    2
D3ParsedPort   ds    2
D3ParseLength  ds    2
D3ParseDigit   ds    2
D3ParseTimesTwo ds   2
D3DestinationPort ds 2
D3HostBuffer   ds    65
D3PortBuffer   ds    7
D3DefaultHostPString
         str   '192.168.5.235'
D3EndpointConfig
         asc   'D3EP'
         dfb   $01,$00
         dw    D3DefaultPort
         ds    504

RawHandle      ds    4
''',
        'D3 endpoint variables',
    )

    text = replace_once(
        text,
        '''D1ConnectMsg
         asc   'Connecting FujiNet to configured 22-mono provider ...'0d00
D1ProviderErrorMsg
''',
        '''D1ConnectMsg
         asc   'FujiNet endpoint set; connecting to 22-mono provider ...'0d00
D3EndpointPromptMsg
         asc   'Choose provider endpoint; ESC exits.'0d00
D3HostPromptMsg
         asc   'Server IP or DNS name [192.168.5.235]: '00
D3PortPromptMsg
         asc   'TCP port [22510]: '00
D3EndpointInputErrorMsg
         asc   'Input rejected; enter a host and TCP port 1-65535.'0d00
D3EndpointSendErrorMsg
         asc   'FujiNet endpoint command failed. error=$'00
D1ProviderErrorMsg
''',
        'D3 endpoint messages',
    )

    required = (
        'FASTPROBE P0.2D3 - app-configured provider',
        'D3ProviderConfigBlockLo equ $A556',
        'D3DefaultPort equ   22510',
        "str   '192.168.5.235'",
        'PromptEndpointD3',
        'ReadTextLineD3',
        'SendEndpointConfigD3',
        'SetSmartPortCommandD3',
        'ThunkCommandTemplate',
        "asc   'D3EP'",
        'Server IP or DNS name [192.168.5.235]:',
        'TCP port [22510]:',
        'LeaveFastBusD2',
    )
    for marker in required:
        if marker not in text:
            raise SystemExit(f'Missing P0.2D3 host marker: {marker}')
    if 'configured 22-mono provider' in text:
        raise SystemExit('Obsolete hidden-config provider message remains.')

    src.write_text(text, encoding='utf-8', newline='\n')
    print('Applied FASTPROBE P0.2D3 app-configured provider endpoint overlay.')


if __name__ == '__main__':
    main()
