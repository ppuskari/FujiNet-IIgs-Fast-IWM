from pathlib import Path
import argparse


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f'Expected {label} pattern not found.')
    return text.replace(old, new, 1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Patch FASTPROBE P0.2B into P0.2B2 ACK-bypass wire test.'
    )
    parser.add_argument(
        '--project-root',
        default='.',
        help='FujiNet-IIgs-Fast-IWM project checkout.'
    )
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    src = root / 'iigs' / 'fastprobe' / 'src' / 'FastProbe.s'
    if not src.is_file():
        raise SystemExit(f'FASTPROBE source not found: {src}')

    text = src.read_text(encoding='utf-8')
    if 'FASTPROBE P0.2B2' in text:
        print('FASTPROBE P0.2B2 patch already applied.')
        return

    text = replace_once(
        text,
        '* FASTPROBE P0.2B\n',
        '* FASTPROBE P0.2B2\n',
        'source version header'
    )
    text = replace_once(
        text,
        "         asc   'FASTPROBE P0.2B - private Fast-IWM wire test'0d\n",
        "         asc   'FASTPROBE P0.2B2 - direct Fast-IWM wire test'0d\n",
        'screen banner'
    )

    single_old = '''         jsr   EnterFastPhase
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
'''
    single_new = '''         jsr   EnterFastPhase

* P0.2B2 deliberately does not gate on ACK.  P0.2B proved only that
* our host did not observe ACK through the assumed IWM SENSE path.
* Request the private packet directly and let marker/data reception
* tell us whether the FujiNet responder is active.
         PushLong #AckBypassMsg
         _WriteCString
         jsr   ReadFastPacket
'''
    text = replace_once(text, single_old, single_new, 'single-packet ACK gate')

    bench_old = '''BenchLoop
         jsr   WaitAckLow
         bcc   BenchArmed
         lda   #ErrAckTimeout
         sta   LastError
         brl   BenchFailed

BenchArmed
         jsr   ReadFastPacket
'''
    bench_new = '''BenchLoop
* PH0 was returned low by the previous packet, so the host is back
* at private arm state 1110.  Raise PH0 inside ReadFastPacket and
* request the next packet directly; ACK is not a benchmark gate.
         jsr   ReadFastPacket
'''
    text = replace_once(text, bench_old, bench_new, 'benchmark ACK gate')

    text = replace_once(
        text,
        "AckFailMsg\n         asc   'FAILED: FujiNet fast responder did not assert ACK.'0d0d00\n",
        "AckFailMsg\n         asc   'FAILED: FujiNet fast responder did not assert ACK.'0d0d00\nAckBypassMsg\n         asc   'ACK gate bypassed; requesting 2us packet directly ... '00\n",
        'ACK message block'
    )

    src.write_text(text, encoding='utf-8', newline='\n')
    print('Applied FASTPROBE P0.2B2 ACK-bypass host patch.')


if __name__ == '__main__':
    main()
