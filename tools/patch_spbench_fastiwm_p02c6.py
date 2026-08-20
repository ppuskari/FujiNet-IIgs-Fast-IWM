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
        description='Apply P0.2C5 then remove post-arm text/phase latency for the C4 delayed packet.'
    )
    parser.add_argument('--project-root', default='.')
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    base = root / 'tools' / 'patch_spbench_fastiwm_p02c5.py'
    src = root / 'iigs' / 'spbench' / 'src' / 'SPBench.s'

    if not base.is_file():
        raise SystemExit(f'Missing P0.2C5 host transform: {base}')
    if not src.is_file():
        raise SystemExit(f'Missing SPBENCH source: {src}')

    subprocess.run(
        [sys.executable, str(base), '--project-root', str(root)],
        check=True,
    )

    text = src.read_text(encoding='utf-8')
    if 'FASTPROBE P0.2C6' in text:
        print('FASTPROBE P0.2C6 host overlay already applied.')
        return
    if 'FASTPROBE P0.2C5' not in text:
        raise SystemExit('P0.2C5 host transform did not apply.')

    text = replace_once(
        text,
        "         asc   'FASTPROBE P0.2C5 - drive-enabled Fast-IWM read'0d\n",
        "         asc   'FASTPROBE P0.2C6 - immediate delayed-packet read'0d\n",
        'P0.2C5 banner',
    )

    # C4 schedules the packet when the magic arm READBLOCK is recognized,
    # before the normal 4-us 512-byte arm reply has completed.  Do not spend
    # any time in TextTools after the ROM call returns; enter the receive loop
    # immediately.
    arm_old = '''FastArmReturned
         PushLong #FastArmOKMsg
         _WriteCString

         jsr   ReadFastPacketC
'''
    arm_new = '''FastArmReturned
* P0.2C6: no TextTools or other output here.  C4's 50-ms timer started
* before the ordinary arm reply was transmitted, so every millisecond
* between ROM return and Read Data polling matters.
         jsr   ReadFastPacketC
'''
    text = replace_once(text, arm_old, arm_new, 'post-arm ARM OK output')

    # C4 no longer depends on a manually generated 1010->1011 request.
    # Remove those phase writes entirely.  Leave whatever phase state the
    # standard SmartPort firmware established and change only the IWM
    # register-select state needed for Read Data.
    phase_old = '''* PH3..PH0 = 1010.
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
    phase_new = '''* P0.2C6: C4 delayed-autosend needs no GPIO/phase trigger.
* Preserve the phase state left by the proven ROM SmartPort arm call.
* Select only the IWM Read-Data register: DRIVE ENABLED, Q7=0, Q6=0.
         lda   >IWM_Q7_OFF
         lda   >IWM_Q6_OFF
         lda   >IWM_Q6_OFF

         ldx   #MarkerScan
'''
    text = replace_once(text, phase_old, phase_new, 'manual 1010/1011 trigger block')

    # On timeout/success ResetFastBusC is still used to return the interface
    # to a conservative state and, via the C5 overlay, disable the drive and
    # restore the exact IIgs Speed register.
    timeout_old = "         asc   'FAST FAILED: drive-enabled IWM read timed out.'0d00\n"
    timeout_new = "         asc   'FAST FAILED: immediate drive-enabled read timed out.'0d00\n"
    text = replace_once(text, timeout_old, timeout_new, 'C5 timeout message')

    required = (
        'FASTPROBE P0.2C6',
        'P0.2C6: no TextTools',
        'P0.2C6: C4 delayed-autosend needs no GPIO/phase trigger',
        'IWM_DRIVE_ON',
        'FastSpeedSaved',
    )
    for marker in required:
        if marker not in text:
            raise SystemExit(f'Missing P0.2C6 marker: {marker}')

    # Structural guards: the receive routine must no longer contain the
    # manual request phase writes after the P0.2C6 comment.
    start = text.index('ReadFastPacketC')
    end = text.index('FastFindD5C', start)
    receive_entry = text[start:end]
    for forbidden in ('IWM_PH3_ON', 'IWM_PH1_ON', 'IWM_PH0_ON'):
        if forbidden in receive_entry:
            raise SystemExit(f'P0.2C6 receive entry still contains {forbidden}.')

    src.write_text(text, encoding='utf-8', newline='\n')
    print('Applied FASTPROBE P0.2C6 immediate delayed-packet receive overlay.')
    print('FujiNet firmware remains P0.2C4; host enters Read Data immediately after arm return.')


if __name__ == '__main__':
    main()
