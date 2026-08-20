from pathlib import Path
import argparse


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f'Expected {label} pattern not found.')
    return text.replace(old, new, 1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Patch FASTPROBE P0.2B/P0.2B2 into P0.2B3 motor-on read-data test.'
    )
    parser.add_argument('--project-root', default='.')
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    src = root / 'iigs' / 'fastprobe' / 'src' / 'FastProbe.s'
    if not src.is_file():
        raise SystemExit(f'FASTPROBE source not found: {src}')

    text = src.read_text(encoding='utf-8')

    # B3 is applied after the B2 ACK-bypass overlay in the builder.
    if 'FASTPROBE P0.2B3' in text:
        print('FASTPROBE P0.2B3 patch already applied.')
        return
    if 'FASTPROBE P0.2B2' not in text:
        raise SystemExit('P0.2B2 host overlay must be applied before P0.2B3.')

    text = replace_once(
        text,
        '* FASTPROBE P0.2B2\n',
        '* FASTPROBE P0.2B3\n',
        'source version header'
    )
    text = replace_once(
        text,
        "         asc   'FASTPROBE P0.2B2 - direct Fast-IWM wire test'0d\n",
        "         asc   'FASTPROBE P0.2B3 - motor-on Fast-IWM read test'0d\n",
        'screen banner'
    )

    # Add motor soft-switch constants.
    text = replace_once(
        text,
        'IWM_PH3_ON     equ   $00C0E7\nIWM_Q6_OFF',
        'IWM_PH3_ON     equ   $00C0E7\n'
        'IWM_MOTOR_OFF  equ   $00C0E8\n'
        'IWM_MOTOR_ON   equ   $00C0E9\n'
        'IWM_Q6_OFF',
        'IWM motor constants'
    )

    # Enter private phase state first, then enable the IWM spindle state.
    # Capture status while motor is on. Status bit 5 should become set if
    # the IWM reports a selected/enabled drive.
    enter_old = '''         lda   >IWM_PH0_OFF
         lda   >IWM_PH2_ON
         lda   >IWM_PH3_ON
         lda   >IWM_PH1_ON

         rep   #$20
'''
    enter_new = '''         lda   >IWM_PH0_OFF
         lda   >IWM_PH2_ON
         lda   >IWM_PH3_ON
         lda   >IWM_PH1_ON

* P0.2B3: Q6=0/Q7=0 addresses the IWM Read-Data register only
* while the spindle/drive-enable state is ON.  B2 omitted this.
         lda   >IWM_MOTOR_ON

* Capture status for post-transfer diagnostics.  Q6=1/Q7=0 selects
* Status; bit 5 indicates that a drive is selected and enabled.
         lda   >IWM_Q6_ON
         lda   >IWM_Q7_OFF
         sta   FastMotorStatus

         rep   #$20
'''
    text = replace_once(text, enter_old, enter_new, 'EnterFastPhase body')

    # Always disable the IWM drive state before leaving the private session.
    exit_old = '''         lda   >IWM_PH0_OFF
         lda   >IWM_PH2_OFF
         lda   >IWM_Q7_OFF
         lda   >IWM_Q6_OFF

         rep   #$20
'''
    exit_new = '''         lda   >IWM_PH0_OFF
         lda   >IWM_PH2_OFF
         lda   >IWM_Q7_OFF
         lda   >IWM_Q6_OFF
         lda   >IWM_MOTOR_OFF

         rep   #$20
'''
    text = replace_once(text, exit_old, exit_new, 'ExitFastPhase body')

    # Add diagnostic state storage.
    text = replace_once(
        text,
        'CurrentMode    ds    2\nLastError',
        'CurrentMode    ds    2\nFastMotorStatus ds  2\nLastError',
        'FastMotorStatus storage'
    )

    # On byte timeout print the captured motor-on status before returning.
    fail_old = '''         PushLong #PacketFailMsg
         _WriteCString
         brl   WaitAndQuit
'''
    fail_new = '''         PushLong #PacketFailMsg
         _WriteCString
         PushLong #MotorStatusMsg
         _WriteCString
         lda   FastMotorStatus
         jsr   WriteHexWord
         jsr   WriteCRLF
         jsr   WriteCRLF
         brl   WaitAndQuit
'''
    text = replace_once(text, fail_old, fail_new, 'single packet timeout report')

    # On success also print the motor-on status once before benchmark.
    success_old = '''SingleValid
         PushLong #SingleOKMsg
         _WriteCString

*-------------------------------------------------
'''
    success_new = '''SingleValid
         PushLong #SingleOKMsg
         _WriteCString
         PushLong #MotorStatusMsg
         _WriteCString
         lda   FastMotorStatus
         jsr   WriteHexWord
         jsr   WriteCRLF
         jsr   WriteCRLF

*-------------------------------------------------
'''
    text = replace_once(text, success_old, success_new, 'single packet success report')

    text = replace_once(
        text,
        "PacketFailMsg\n         asc   'FAILED: timeout receiving fast IWM byte stream.'0d0d00\n",
        "PacketFailMsg\n         asc   'FAILED: timeout receiving fast IWM byte stream.'0d00\n"
        "MotorStatusMsg\n         asc   'IWM status captured with motor ON=$'00\n",
        'motor diagnostic message'
    )

    src.write_text(text, encoding='utf-8', newline='\n')
    print('Applied FASTPROBE P0.2B3 motor-on Read-Data patch.')


if __name__ == '__main__':
    main()
