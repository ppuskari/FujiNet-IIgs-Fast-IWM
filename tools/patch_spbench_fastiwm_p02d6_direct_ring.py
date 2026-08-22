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
            'Remove live Memory Manager BlockMove calls by decoding PCM '
            'directly into the Tool225 ring.'
        )
    )
    parser.add_argument('--project-root', default='.')
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    base = root / 'tools' / 'patch_spbench_fastiwm_p02d5_thunk_flags.py'
    src = root / 'iigs' / 'spbench' / 'src' / 'SPBench.s'
    if not base.is_file() or not src.is_file():
        raise SystemExit('Missing P0.2D5 transform or SPBENCH source.')

    text = src.read_text(encoding='utf-8')
    if 'FASTPROBE P0.2D6' in text:
        print('FASTPROBE P0.2D6 direct-ring overlay already applied.')
        return
    if 'FASTPROBE P0.2D5' not in text:
        subprocess.run(
            [sys.executable, str(base), '--project-root', str(root)],
            check=True,
        )
        text = src.read_text(encoding='utf-8')
    if 'FASTPROBE P0.2D5' not in text:
        raise SystemExit('P0.2D5 host transform did not apply.')

    text = replace_once(
        text,
        "         asc   'FASTPROBE P0.2D5 - safe SmartPort return'0d\n",
        "         asc   'FASTPROBE P0.2D6 - direct ring decode'0d\n",
        'D5 banner',
    )

    text = replace_once(
        text,
        '''         PushLong RawStagePtr
         PushLong #D1ProviderStatus
         pea   $0000
         pea   D1ProviderStatusSize
         _BlockMove

* Status begins "D1FS", then version/state/error, then little-endian FIFO
''',
        '''         jsr   CopyProviderStatusD6

* Status begins "D1FS", then version/state/error, then little-endian FIFO
''',
        'live provider status BlockMove',
    )

    status_copy = r'''CopyProviderStatusD6
* P0.2D6: copy the 32-byte bank-zero SmartPort reply without entering the
* Memory Manager while Tool225 interrupts are active. The source operand is
* patched from the allocated RawStagePtr; the destination is application data.
         php
         phb
         rep   #$30
         mx    %00
         lda   RawStagePtr
         sta   D6StatusLoad+1
         lda   RawStagePtr+2
         sep   #$20
         mx    %10
         sta   D6StatusLoad+3
         phk
         plb
         ldx   #D1ProviderStatusSize-1
D6StatusCopyLoop
D6StatusLoad
         lda   >$000000,x
         sta   D1ProviderStatus,x
         dex
         bpl   D6StatusCopyLoop
         rep   #$30
         mx    %00
         plb
         plp
         rts

'''
    text = replace_once(
        text,
        '\nWaitProviderBatchD1\n',
        '\n' + status_copy + 'WaitProviderBatchD1\n',
        'provider status-copy routine anchor',
    )

    text = replace_once(
        text,
        '''DecodeFastPacketD1
* 73 complete 8-to-7 groups carry 511 PCM bytes in 584 physical bytes.
* The final PCM byte uses one low-7 byte plus one packed-MSB byte, for an
* exact 586-byte IWM-safe payload -> 512 chronological provider bytes.
         php
         sep   #$20
         mx    %10
         ldx   #$0000
''',
        '''DecodeFastPacketD1
* 73 complete 8-to-7 groups carry 511 PCM bytes in 584 physical bytes.
* The final PCM byte uses one low-7 byte plus one packed-MSB byte, for an
* exact 586-byte IWM-safe payload -> 512 chronological provider bytes.
* P0.2D6 patches two long stores to the current ring destination and decodes
* there directly. This removes 29,000+ live Memory Manager calls per session.
         php
         rep   #$30
         mx    %00
         lda   D0PCMWritePtr
         sta   D6PCMStore+1
         sta   D6FinalPCMStore+1
         lda   D0PCMWritePtr+2
         sep   #$20
         mx    %10
         sta   D6PCMStore+3
         sta   D6FinalPCMStore+3
         ldx   #$0000
''',
        'decode entry',
    )

    text = replace_once(
        text,
        '''D1DecodeGroup
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
''',
        '''D1DecodeGroup
         lda   FastBufferC+7,y
         and   #$7F
         sta   D0HighBits
         lda   #$07
         sta   D1LaneRemaining
D1DecodeByte
         lda   FastBufferC,y
         and   #$7F
         lsr   D0HighBits
         bcc   D1DecodedLow
         ora   #$80
D1DecodedLow
D6PCMStore
         sta   >$000000,x
         iny
         inx
         dec   D1LaneRemaining
         bne   D1DecodeByte
         iny
         dec   D0GroupRemaining
         bne   D1DecodeGroup
''',
        'decoder index roles and direct destination store',
    )

    text = replace_once(
        text,
        '''         lda   FastBufferC+584
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
''',
        '''         lda   FastBufferC+584
         and   #$7F
         sta   D0HighBits
         lda   FastBufferC+585
         and   #$01
         beq   D1FinalPCMReady
         lda   D0HighBits
         ora   #$80
         sta   D0HighBits
D1FinalPCMReady
         lda   D0HighBits
D6FinalPCMStore
         sta   >$000000,x
         rep   #$20
         mx    %00

         inc   D1RingPacketIndex
''',
        'final-byte staging and live BlockMove',
    )

    required = (
        'FASTPROBE P0.2D6 - direct ring decode',
        'CopyProviderStatusD6',
        'D6StatusLoad',
        'D6PCMStore',
        'D6FinalPCMStore',
        'sta   >$000000,x',
        'P0.2D5: remain M=0/X=0',
    )
    for marker in required:
        if marker not in text:
            raise SystemExit(f'Missing P0.2D6 host marker: {marker}')

    src.write_text(text, encoding='utf-8', newline='\n')
    print('Applied FASTPROBE P0.2D6 direct-ring decode overlay.')


if __name__ == '__main__':
    main()
