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
            'Apply P0.2C10, then explicitly select the IIgs internal Slot 6 '
            'IWM and use the always-present bank E1 I/O mirror.'
        )
    )
    parser.add_argument('--project-root', default='.')
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    base = root / 'tools' / 'patch_spbench_fastiwm_p02c10.py'
    src = root / 'iigs' / 'spbench' / 'src' / 'SPBench.s'
    if not src.is_file():
        raise SystemExit('Missing SPBENCH source.')

    text = src.read_text(encoding='utf-8')
    if 'FASTPROBE P0.2C11' in text:
        print('FASTPROBE P0.2C11 host overlay already applied.')
        return
    if 'FASTPROBE P0.2C10' not in text and 'FASTPROBE P0.2C9' in text:
        text = replace_once(
            text,
            "         asc   'FASTPROBE P0.2C9 - host-ready IWM 2us link'0d\n",
            "         asc   'FASTPROBE P0.2C10 - live-C fast READY link'0d\n",
            'P0.2C9 banner',
        )
        text = replace_once(
            text,
            '''         lda   #IWMFastMode
         jsr   SetIWMModeC

* P0.2C9: an exact $0F write is preferred, but observed mode $0C is also
* a valid 2-us receive configuration: C=1 selects 2-us cells, and the
* short data latch remains long enough for this interrupt-free polling loop.
* Never hang here if the SmartPort-selected IWM refuses the H/L mode bits.
         lda   FastModeObserved
         sta   FastModeReceive
         and   #IWMCell2usMask
         bne   FastModeUsableC
         brl   FastPacketTimeoutC

FastModeUsableC
''',
            '''* P0.2C10: C8 proved the live mode is $0C. Its C bit already selects
* 2-us cells, so do not spend the host-ready interval trying to change only
* H/L. Attempt the bounded ROM-style $0F write only if C is not already set.
         lda   FastModeSaved
         sta   FastModeObserved
         and   #IWMCell2usMask
         bne   FastModeLiveC

         lda   #IWMFastMode
         jsr   SetIWMModeC

FastModeLiveC
         lda   FastModeObserved
         sta   FastModeReceive
         and   #IWMCell2usMask
         bne   FastModeUsableC
         brl   FastPacketTimeoutC

FastModeUsableC
''',
            'P0.2C9 unconditional exact-mode attempt',
        )
        text = replace_once(
            text,
            "         asc   'FAST FAILED: ready-triggered 2us IWM read timed out.'0d00\n",
            "         asc   'FAST FAILED: C10 READY 2us IWM read timed out.'0d00\n",
            'P0.2C9 timeout message',
        )
        src.write_text(text, encoding='utf-8', newline='\n')
    elif 'FASTPROBE P0.2C10' not in text and base.is_file():
        subprocess.run(
            [sys.executable, str(base), '--project-root', str(root)],
            check=True,
        )
        text = src.read_text(encoding='utf-8')
    if 'FASTPROBE P0.2C10' not in text:
        raise SystemExit('P0.2C10 host transform did not apply.')

    text = replace_once(
        text,
        "         asc   'FASTPROBE P0.2C10 - live-C fast READY link'0d\n",
        "         asc   'FASTPROBE P0.2C11 - routed internal-IWM link'0d\n",
        'P0.2C10 banner',
    )

    io_lines = {
        '$00C0E0': '$E1C0E0',
        '$00C0E1': '$E1C0E1',
        '$00C0E2': '$E1C0E2',
        '$00C0E3': '$E1C0E3',
        '$00C0E4': '$E1C0E4',
        '$00C0E5': '$E1C0E5',
        '$00C0E6': '$E1C0E6',
        '$00C0E7': '$E1C0E7',
        '$00C0E8': '$E1C0E8',
        '$00C0E9': '$E1C0E9',
        '$00C0EC': '$E1C0EC',
        '$00C0ED': '$E1C0ED',
        '$00C0EE': '$E1C0EE',
        '$00C0EF': '$E1C0EF',
        '$00C036': '$E1C036',
    }
    for old, new in io_lines.items():
        if old not in text:
            raise SystemExit(f'Missing P0.2C10 I/O address: {old}')
        text = text.replace(old, new)

    text = replace_once(
        text,
        '''IIGS_SPEED      equ   $E1C036
Slot6DetectMask equ   $04
''',
        '''IIGS_SPEED      equ   $E1C036
IIGS_SLTROMSEL  equ   $E1C02D
IIGS_DISKREG    equ   $E1C031
IWM_SELECT_1    equ   $E1C0EA
Slot6DetectMask equ   $04
InternalSlot6Mask equ $40
SmartPortSelectMask equ $40
''',
        'P0.2C10 IIgs system constants',
    )

    text = replace_once(
        text,
        '''* Preserve the IIgs Speed register and temporarily disable only the
* Slot-6 Disk II motor-on detector.  This prevents the required $C0E9
* drive-enable access from forcing the CPU down to 1.024 MHz.
         lda   >IIGS_SPEED
''',
        '''* P0.2C11: the ROM arm call restores the user's Slot register before
* returning. Force internal Slot 6 hardware so $C0Ex reaches the IWM rather
* than an external/empty Slot 6, and select SmartPort rather than the 3.5
* mechanism. Bank $E1 is the unconditional IIgs I/O mirror.
         lda   >IIGS_SLTROMSEL
         sta   FastSlotRegSaved
         and   #$BF
         sta   >IIGS_SLTROMSEL
         lda   >IIGS_DISKREG
         sta   FastDiskRegSaved
         and   #$BF
         sta   >IIGS_DISKREG

* Preserve the IIgs Speed register and temporarily disable only the
* Slot-6 Disk II motor-on detector. This prevents the required ENABLE+1
* access from forcing the CPU down to 1.024 MHz.
         lda   >IIGS_SPEED
''',
        'P0.2C10 direct-IWM entry',
    )

    text = replace_once(
        text,
        '''* Technical Note #30: Read Data is DRIVE ENABLED, Q7=0, Q6=0.
         lda   >IWM_DRIVE_ON
''',
        '''* Select unit/drive 1 explicitly, then enter Read Data with the
* drive enabled and Q7=0/Q6=0.
         lda   >IWM_SELECT_1
         lda   >IWM_DRIVE_ON
''',
        'P0.2C10 drive-enable sequence',
    )

    text = replace_once(
        text,
        '''* Leave the disk interface, IWM mode, and machine speed exactly as found.
         lda   >IWM_DRIVE_OFF
         lda   FastModeSaved
         jsr   SetIWMModeC
         lda   FastSpeedSaved
         sta   >IIGS_SPEED
         rts
''',
        '''* Restore the IWM while internal Slot 6 is still selected, then put
* every IIgs mapping/control register back exactly as it was on entry.
         lda   >IWM_DRIVE_OFF
         lda   FastModeSaved
         jsr   SetIWMModeC
         lda   FastDiskRegSaved
         sta   >IIGS_DISKREG
         lda   FastSlotRegSaved
         sta   >IIGS_SLTROMSEL
         lda   FastSpeedSaved
         sta   >IIGS_SPEED
         rts
''',
        'P0.2C10 cleanup tail',
    )

    text = replace_once(
        text,
        '''FastPatternFail ds   2
FastSpeedSaved ds    2
FastModeSaved  ds    2
''',
        '''FastPatternFail ds   2
FastSpeedSaved ds    2
FastSlotRegSaved ds  2
FastDiskRegSaved ds  2
FastModeSaved  ds    2
''',
        'P0.2C10 direct-IWM saved state',
    )

    text = replace_once(
        text,
        "         asc   'FAST FAILED: C10 READY 2us IWM read timed out.'0d00\n",
        "         asc   'FAST FAILED: C11 routed 2us IWM read timed out.'0d00\n",
        'P0.2C10 timeout message',
    )

    required = (
        'FASTPROBE P0.2C11',
        'IIGS_SLTROMSEL  equ   $E1C02D',
        'IIGS_DISKREG    equ   $E1C031',
        'IWM_PH0_ON      equ   $E1C0E1',
        'IWM_SELECT_1    equ   $E1C0EA',
        'and   #$BF',
        'sta   >IIGS_SLTROMSEL',
        'sta   >IIGS_DISKREG',
        'lda   >IWM_SELECT_1',
        'FastSlotRegSaved',
        'FastDiskRegSaved',
    )
    for marker in required:
        if marker not in text:
            raise SystemExit(f'Missing P0.2C11 host marker: {marker}')

    receive_start = text.index('\nReadFastPacketC\n')
    mode_start = text.index('lda   >IWM_DRIVE_OFF', receive_start)
    trigger = text.index('lda   >IWM_PH0_ON', mode_start)
    slot_select = text.index('sta   >IIGS_SLTROMSEL', receive_start)
    drive_select = text.index('lda   >IWM_SELECT_1', mode_start)
    if not (slot_select < mode_start < drive_select < trigger):
        raise SystemExit('Unsafe P0.2C11 Slot/IWM/READY ordering.')

    cleanup = text[text.index('\nResetFastBusC\n'):text.index('\nValidateFastBufferC\n')]
    if cleanup.index('jsr   SetIWMModeC') > cleanup.index('sta   >IIGS_SLTROMSEL'):
        raise SystemExit('P0.2C11 restores Slot 6 mapping before the IWM mode.')

    src.write_text(text, encoding='utf-8', newline='\n')
    print('Applied FASTPROBE P0.2C11 internal-Slot-6/bank-E1 IWM overlay.')


if __name__ == '__main__':
    main()
