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
            'Add bounded, observable retries around idempotent provider '
            'SmartPort control calls without changing the proven fast loop.'
        )
    )
    parser.add_argument('--project-root', default='.')
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    base = root / 'tools' / 'patch_spbench_fastiwm_p02d7_guarded_exit.py'
    src = root / 'iigs' / 'spbench' / 'src' / 'SPBench.s'
    if not base.is_file() or not src.is_file():
        raise SystemExit('Missing P0.2D7 transform or SPBENCH source.')

    text = src.read_text(encoding='utf-8')
    if 'FASTPROBE P0.2D8' in text:
        print('FASTPROBE P0.2D8 control-retry overlay already applied.')
        return
    if 'FASTPROBE P0.2D7' not in text:
        subprocess.run(
            [sys.executable, str(base), '--project-root', str(root)],
            check=True,
        )
        text = src.read_text(encoding='utf-8')
    if 'FASTPROBE P0.2D7' not in text:
        raise SystemExit('P0.2D7 host transform did not apply.')

    text = replace_once(
        text,
        "         asc   'FASTPROBE P0.2D7 - guarded SPI/GSOS exit'0d\n",
        "         asc   'FASTPROBE P0.2D8 - control-call recovery'0d\n",
        'D7 banner',
    )

    text = replace_once(
        text,
        '''D1ProviderTimeoutTicks equ $0E10
KBD             equ   $E1C000
''',
        '''D1ProviderTimeoutTicks equ $0E10
D8ControlAttempts equ  $0008
KBD             equ   $E1C000
''',
        'provider constants',
    )

    text = replace_once(
        text,
        '''D1ProviderStatus ds  32
D3InputMaxLength ds 2
''',
        '''D1ProviderStatus ds  32
D8ControlBlock ds    2
D8ControlRemaining ds 2
D8ControlRetryTick ds 4
D8ControlRetries ds  4
D3InputMaxLength ds 2
''',
        'D3/D8 provider state',
    )

    text = replace_once(
        text,
        '''         stz   FastBurstError
         stz   D1ProviderError
         stz   D1UserStop
''',
        '''         stz   FastBurstError
         stz   D1ProviderError
         stz   LastError
         stz   D8ControlRetries
         stz   D8ControlRetries+2
         stz   D1UserStop
''',
        'stream retry initialization',
    )

    for old, new, label in (
        (
            '''         lda   #D1ProviderStartBlockLo
         jsr   CallProviderBlockD1
         bcs   D1ProviderCallFailed
''',
            '''         lda   #D1ProviderStartBlockLo
         jsr   CallProviderBlockRetryD8
         bcs   D1ProviderCallFailed
''',
            'provider START call',
        ),
        (
            '''         lda   #FastArmBlockLo
         jsr   CallProviderBlockD1
         bcs   D1ProviderCallFailed
''',
            '''         lda   #FastArmBlockLo
         jsr   CallProviderBlockRetryD8
         bcs   D1ProviderCallFailed
''',
            'provider ARM call',
        ),
        (
            '''         lda   #D1ProviderStatusBlockLo
         jsr   CallProviderBlockD1
         bcs   D1ProviderStatusCallFailed
''',
            '''         lda   #D1ProviderStatusBlockLo
         jsr   CallProviderBlockRetryD8
         bcs   D1ProviderStatusCallFailed
''',
            'provider STATUS call',
        ),
    ):
        text = replace_once(text, old, new, label)

    text = replace_once(
        text,
        '''CallProviderBlockD1
ArmBlockStore
''',
        '''CallProviderBlockRetryD8
* P0.2D8: START, STATUS, and not-yet-triggered ARM are idempotent. Retry a
* transient SmartPort carry for at most eight 60-Hz ticks while the 512-KiB
* DOC source ring continues to drain. Preserve the final SmartPort error.
         sta   D8ControlBlock
         lda   #D8ControlAttempts
         sta   D8ControlRemaining
D8ControlTry
         lda   D8ControlBlock
         jsr   CallProviderBlockD1
         bcc   D8ControlSucceeded
         sta   LastError
         dec   D8ControlRemaining
         beq   D8ControlFailed
         inc   D8ControlRetries
         bne   D8ControlRetryCounted
         inc   D8ControlRetries+2
D8ControlRetryCounted
         jsr   ReadSystemTick
         lda   CurrentTick
         sta   D8ControlRetryTick
         lda   CurrentTick+2
         sta   D8ControlRetryTick+2
D8ControlWaitTick
         jsr   ReadSystemTick
         lda   CurrentTick
         cmp   D8ControlRetryTick
         bne   D8ControlTry
         lda   CurrentTick+2
         cmp   D8ControlRetryTick+2
         beq   D8ControlWaitTick
         bra   D8ControlTry
D8ControlFailed
         lda   LastError
         sec
         rts
D8ControlSucceeded
         clc
         rts

CallProviderBlockD1
ArmBlockStore
''',
        'provider call primitive',
    )

    text = replace_once(
        text,
        '''         lda   D1ProviderError
         jsr   WriteHexWord
         jsr   WriteCRLF
         brl   WaitAndQuit
''',
        '''         lda   D1ProviderError
         jsr   WriteHexWord
         PushLong #D8SmartPortErrorMsg
         _WriteCString
         lda   LastError
         jsr   WriteHexWord
         PushLong #D8ControlRetriesMsg
         _WriteCString
         lda   D8ControlRetries
         sta   MetricValue
         lda   D8ControlRetries+2
         sta   MetricValue+2
         jsr   PrintMetricDecimal
         jsr   WriteCRLF
         brl   WaitAndQuit
''',
        'stream failure diagnostics',
    )

    text = replace_once(
        text,
        '''D1ProviderErrorMsg
         asc   ' provider=$'00
D1BatchesMsg
''',
        '''D1ProviderErrorMsg
         asc   ' provider=$'00
D8SmartPortErrorMsg
         asc   ' smartport=$'00
D8ControlRetriesMsg
         asc   ' retries='00
D1BatchesMsg
''',
        'D8 failure messages',
    )

    required = (
        'FASTPROBE P0.2D8 - control-call recovery',
        'D8ControlAttempts equ  $0008',
        'CallProviderBlockRetryD8',
        'D8ControlWaitTick',
        'smartport=$',
        'D8ControlRetries',
        'sta   >IIGS_DISKREG',
        'sta   >IIGS_SLTROMSEL',
        'P0.2D6 patches two long stores',
    )
    for marker in required:
        if marker not in text:
            raise SystemExit(f'Missing P0.2D8 host marker: {marker}')

    if text.count('jsr   CallProviderBlockRetryD8') != 3:
        raise SystemExit('P0.2D8 did not wrap exactly START/ARM/STATUS.')
    if 'jsr   CallProviderBlockRetryD8\n         rts\n\nWaitProvider' in text:
        raise SystemExit('P0.2D8 unexpectedly retries STOP.')

    src.write_text(text, encoding='utf-8', newline='\n')
    print('Applied FASTPROBE P0.2D8 bounded control-call retry overlay.')


if __name__ == '__main__':
    main()
