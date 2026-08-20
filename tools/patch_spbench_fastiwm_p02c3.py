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
        description='Apply P0.2C host then remove the unproven 1010->1011 trigger for C3 autosend.'
    )
    parser.add_argument('--project-root', default='.')
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    c_patch = root / 'tools' / 'run_spbench_fastiwm_p02c.py'
    c_fix = root / 'tools' / 'fix_fastiwm_p02c_branches.py'
    src = root / 'iigs' / 'spbench' / 'src' / 'SPBench.s'

    subprocess.run(
        [sys.executable, str(c_patch), '--project-root', str(root)],
        check=True,
    )
    subprocess.run(
        [sys.executable, str(c_fix), '--project-root', str(root)],
        check=True,
    )

    text = src.read_text(encoding='utf-8')
    if 'FASTPROBE P0.2C3' in text:
        print('FASTPROBE P0.2C3 host overlay already applied.')
        return

    text = replace_once(
        text,
        "         asc   'FASTPROBE P0.2C - SmartPort-armed Fast-IWM'0d\n"
        "         asc   '4us arm READBLOCK then 2us one-shot response'0d\n",
        "         asc   'FASTPROBE P0.2C3 - SmartPort-arm autosend'0d\n"
        "         asc   '4us arm READBLOCK; FujiNet auto-sends 2us packet'0d\n",
        'P0.2C banner',
    )

    text = replace_once(
        text,
        "         asc   'ARM OK'0d00\n",
        "         asc   'ARM OK; waiting for delayed 2us autosend'0d00\n",
        'P0.2C arm success message',
    )

    old_read_setup = '''* Enter the actual upstream SmartPort enable state 1010, configure the
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
'''

    new_read_setup = '''* P0.2C3 removes the second, unproven manual SmartPort phase trigger.
* The standard $7FA55A arm transaction has already completed through ROM.
* FujiNet schedules one delayed 2-us transmit autonomously.  The IIgs only
* selects the IWM Read-Data latch and waits for the marker/data stream.
* Keep interrupts disabled until the packet completes or times out.

ReadFastPacketC
         php
         sei
         sep   #$20

* Q6=0/Q7=0: direct IWM Read-Data polling.  Do not touch PH0..PH3 here.
         lda   >IWM_Q7_OFF
         lda   >IWM_Q6_OFF
         lda   >IWM_Q6_OFF

         ldx   #MarkerScan
'''

    text = replace_once(
        text,
        old_read_setup,
        new_read_setup,
        'P0.2C manual 1010/1011 read setup',
    )

    required = (
        'FASTPROBE P0.2C3',
        'waiting for delayed 2us autosend',
        'Do not touch PH0..PH3 here',
        'ReadFastPacketC',
        'FAST PASS: exact 512-byte 2us payload verified.',
    )
    for item in required:
        if item not in text:
            raise SystemExit(f'Missing P0.2C3 host marker: {item}')

    src.write_text(text, encoding='utf-8', newline='\n')
    print('Applied FASTPROBE P0.2C3 autonomous-send host overlay.')
    print('Host no longer generates manual 1010 -> 1011 after the arm call.')


if __name__ == '__main__':
    main()
