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
            'Apply P0.2C14 and record the first eight bytes for which the '
            'IWM Read Data register presents bit 7, without doing any I/O '
            'until after the fast bus has been reset.'
        )
    )
    parser.add_argument('--project-root', default='.')
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    base = root / 'tools' / 'patch_spbench_fastiwm_p02c14.py'
    src = root / 'iigs' / 'spbench' / 'src' / 'SPBench.s'
    if not base.is_file() or not src.is_file():
        raise SystemExit('Missing P0.2C14 host transform or SPBENCH source.')

    text = src.read_text(encoding='utf-8')
    if 'FASTPROBE P0.2C15' in text:
        print('FASTPROBE P0.2C15 host overlay already applied.')
        return
    if 'FASTPROBE P0.2C14' not in text:
        subprocess.run(
            [sys.executable, str(base), '--project-root', str(root)],
            check=True,
        )
        text = src.read_text(encoding='utf-8')
    if 'FASTPROBE P0.2C14' not in text:
        raise SystemExit('P0.2C14 host transform did not apply.')

    text = replace_once(
        text,
        "         asc   'FASTPROBE P0.2C14 - 0.5us-pulse 3.5 route'0d\n",
        "         asc   'FASTPROBE P0.2C15 - IWM byte observability'0d\n",
        'P0.2C14 banner',
    )

    text = replace_once(
        text,
        '''         jsr   ReadFastPacketC
         bcc   FastPacketReceivedC

         PushLong #FastTimeoutMsg
''',
        '''         jsr   ReadFastPacketC
         bcs   FastPacketFailedC
         brl   FastPacketReceivedC
FastPacketFailedC
         PushLong #FastTimeoutMsg
''',
        'P0.2C14 short receive-result branch',
    )

    text = replace_once(
        text,
        '''FastModeUsableC
* Establish the proven SmartPort enable state 1010 only after the receiver
''',
        '''FastModeUsableC
* P0.2C15: clear the bounded in-memory receive trace before READY. No tool
* calls or screen output occur while the physical packet is on the wire.
         stz   FastReadyCount
         stz   FastReadyCount+1
         ldx   #FastReadySampleLimit-1
         lda   #$00
FastReadyClearC
         sta   FastReadySamples,x
         dex
         bpl   FastReadyClearC

* Establish the proven SmartPort enable state 1010 only after the receiver
''',
        'P0.2C14 receive-trace initialization',
    )

    text = replace_once(
        text,
        '''FastByteReadyC
         clc
         rts
''',
        '''FastByteReadyC
* Record at most eight ready bytes. Once full, this path only preserves A;
* the sixteen leading sync bytes leave the marker scanner time to settle.
         mx    %10
         pha
         lda   FastReadyCount
         cmp   #FastReadySampleLimit
         bcs   FastByteReadyNoSampleC
         rep   #$20
         mx    %00
         lda   FastReadyCount
         and   #$00FF
         tay
         sep   #$20
         mx    %10
         pla
         sta   FastReadySamples,y
         pha
         inc   FastReadyCount
FastByteReadyNoSampleC
         pla
         clc
         rts
''',
        'P0.2C14 byte-ready return',
    )

    old_disk_report = '''         PushLong #FastDiskDiagMsg
         _WriteCString
         lda   FastDiskRegSaved
         and   #$00FF
         jsr   WriteHexWord
         PushLong #FastModeArrowMsg
         _WriteCString
         lda   FastDiskRegActive
         and   #$00FF
         jsr   WriteHexWord
         jsr   WriteCRLF
         rts
'''
    sample_report = ''.join(
        f'''         lda   FastReadySamples+{offset}\n'''
        '''         and   #$00FF\n'''
        '''         jsr   WriteHexWord\n'''
        '''         PushLong #FastReadySpaceMsg\n'''
        '''         _WriteCString\n'''
        for offset in range(8)
    )
    new_disk_report = '''         PushLong #FastDiskDiagMsg
         _WriteCString
         lda   FastDiskRegSaved
         and   #$00FF
         jsr   WriteHexWord
         PushLong #FastModeArrowMsg
         _WriteCString
         lda   FastDiskRegActive
         and   #$00FF
         jsr   WriteHexWord
         jsr   WriteCRLF
         PushLong #FastReadyDiagMsg
         _WriteCString
         lda   FastReadyCount
         and   #$00FF
         jsr   WriteHexWord
         PushLong #FastReadyDataMsg
         _WriteCString
''' + sample_report + '''         jsr   WriteCRLF
         rts
'''
    text = replace_once(
        text,
        old_disk_report,
        new_disk_report,
        'P0.2C14 timeout diagnostics',
    )

    text = replace_once(
        text,
        '''FastModeReceive ds   2
FastBufferC     ds    512
''',
        '''FastModeReceive ds   2
FastReadyCount ds     2
FastReadySamples ds   8
FastBufferC     ds    512
''',
        'P0.2C14 receive state',
    )

    text = replace_once(
        text,
        "         asc   'FAST FAILED: C14 0.5us-pulse IWM read timed out.'0d00\n",
        "         asc   'FAST FAILED: C15 IWM byte trace timed out.'0d00\n",
        'P0.2C14 timeout message',
    )

    text = replace_once(
        text,
        "FastDiskDiagMsg\n         asc   'DISKREG saved/active=$'00\n",
        "FastDiskDiagMsg\n         asc   'DISKREG saved/active=$'00\n"
        "FastReadyDiagMsg\n         asc   'IWM ready samples=$'00\n"
        "FastReadyDataMsg\n         asc   ' data='00\n"
        "FastReadySpaceMsg\n         asc   ' '00\n",
        'P0.2C14 diagnostic messages',
    )

    text = replace_once(
        text,
        '''FastPayload     equ   $0200
MarkerScan      equ   $0100
''',
        '''FastPayload     equ   $0200
FastReadySampleLimit equ 8
MarkerScan      equ   $0100
''',
        'P0.2C14 receive constants',
    )

    required = (
        'FASTPROBE P0.2C15',
        'FAST FAILED: C15 IWM byte trace timed out.',
        'IWM ready samples=$',
        'FastReadySampleLimit equ 8',
        'sta   FastReadySamples,y',
        'rep   #$20\n         mx    %00',
        'sep   #$20\n         mx    %10',
        'brl   FastPacketReceivedC',
        'P0.2C13: DISKREG bit 6 selects the IIgs 3.5-inch path',
        'cmp   #IWMFastMode',
        'IWM_PH0_ON      equ   $E1C0E1',
    )
    for marker in required:
        if marker not in text:
            raise SystemExit(f'Missing P0.2C15 host marker: {marker}')

    receive = text[text.index('\nReadFastPacketC\n'):text.index('\nResetFastBusC\n')]
    clear = receive.index('stz   FastReadyCount')
    ready = receive.index('lda   >IWM_PH0_ON')
    capture = receive.index('sta   FastReadySamples,y')
    if not (clear < ready < capture):
        raise SystemExit('Unsafe P0.2C15 trace/READY/capture ordering.')
    if '_WriteCString' in receive:
        raise SystemExit('P0.2C15 performs TextTools I/O in the receive path.')

    src.write_text(text, encoding='utf-8', newline='\n')
    print('Applied FASTPROBE P0.2C15 in-memory IWM byte trace overlay.')


if __name__ == '__main__':
    main()
