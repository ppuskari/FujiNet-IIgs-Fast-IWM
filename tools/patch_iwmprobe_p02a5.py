from pathlib import Path
import subprocess
import sys

repo = Path('.')
subprocess.run([sys.executable, str(repo / 'tools' / 'patch_iwmprobe_p02a3.py')], check=True)
subprocess.run([sys.executable, str(repo / 'tools' / 'patch_iwmprobe_p02a4.py')], check=True)

path = repo / 'iigs' / 'iwmprobe' / 'src' / 'IWMProbe.s'
text = path.read_text(encoding='utf-8')

if 'IWMPROBE P0.2A5' in text:
    print('IWMPROBE P0.2A5 patch already applied.')
    raise SystemExit(0)
if 'IWMPROBE P0.2A4' not in text:
    raise SystemExit('P0.2A5 expects the P0.2A4 patch first.')

# Add the IIgs Disk Interface register and documented 3.5-inch select bit.
needle = "IWM_FAST_BIT   equ   $0008\n"
replacement = (
    "IWM_FAST_BIT   equ   $0008\n"
    "DISK_IF_REG    equ   $00C031\n"
    "DISK_35_BIT    equ   $0040\n"
)
if needle not in text:
    raise SystemExit('IWM_FAST_BIT definition not found.')
text = text.replace(needle, replacement, 1)

# Initialize new state words so byte stores leave clean high bytes for printing.
needle = "         stz   DesiredMode\n"
replacement = (
    "         stz   DesiredMode\n"
    "         stz   OriginalDiskIF\n"
    "         stz   SelectedDiskIF\n"
    "         stz   RestoredDiskIF\n"
)
if needle not in text:
    raise SystemExit('DesiredMode initialization not found.')
text = text.replace(needle, replacement, 1)

# Select the 3.5-inch path only after the IWM motor-off wait is complete.
needle = """         PushLong #DoneMsg
         _WriteCString

         lda   InitialMode
"""
replacement = """         PushLong #DoneMsg
         _WriteCString

         jsr   Select35Disk
         PushLong #DiskSelectMsg
         _WriteCString
         lda   OriginalDiskIF
         jsr   WriteHexWord
         PushLong #DiskSelectedMsg
         _WriteCString
         lda   SelectedDiskIF
         jsr   WriteHexWord
         jsr   WriteCRLF

         lda   InitialMode
"""
if needle not in text:
    raise SystemExit('Post-timer insertion point not found.')
text = text.replace(needle, replacement, 1)

# Restore $C031 on both normal and failed IWM-restore exits before any disk I/O.
needle = """         PushLong #RestoreFailMsg
         _WriteCString
         bra   WaitAndQuit

RestoreOK
         PushLong #RestoreOKMsg
         _WriteCString
"""
replacement = """         PushLong #RestoreFailMsg
         _WriteCString
         jsr   RestoreDiskInterface
         jsr   PrintDiskRestore
         bra   WaitAndQuit

RestoreOK
         jsr   RestoreDiskInterface
         jsr   PrintDiskRestore
         PushLong #RestoreOKMsg
         _WriteCString
"""
if needle not in text:
    raise SystemExit('Restore exit block not found.')
text = text.replace(needle, replacement, 1)

# Add safe read-modify-write helpers.  No disk calls occur while bit 6 is set.
needle = """ReadIWMMode
         stz   CurrentStatus
"""
routines = """Select35Disk
         php
         sei
         sep   #$20
         lda   >DISK_IF_REG
         sta   OriginalDiskIF
         ora   #$40
         sta   >DISK_IF_REG
         lda   >DISK_IF_REG
         sta   SelectedDiskIF
         rep   #$20
         plp
         rts

RestoreDiskInterface
         php
         sei
         sep   #$20
         lda   OriginalDiskIF
         sta   >DISK_IF_REG
         lda   >DISK_IF_REG
         sta   RestoredDiskIF
         rep   #$20
         plp
         rts

PrintDiskRestore
         PushLong #DiskRestoreMsg
         _WriteCString
         lda   RestoredDiskIF
         jsr   WriteHexWord
         jsr   WriteCRLF
         rts

ReadIWMMode
         stz   CurrentStatus
"""
if needle not in text:
    raise SystemExit('ReadIWMMode insertion point not found.')
text = text.replace(needle, routines, 1)

# Add state storage.
needle = """ImmediateStatus ds   2
ImmediateMode  ds    2
"""
replacement = """ImmediateStatus ds   2
ImmediateMode  ds    2
OriginalDiskIF ds    2
SelectedDiskIF ds    2
RestoredDiskIF ds    2
"""
if needle not in text:
    raise SystemExit('P0.2A4 immediate state block not found.')
text = text.replace(needle, replacement, 1)

# Add visible diagnostics.
needle = """DoneMsg
         asc   'done'0d00
"""
replacement = """DoneMsg
         asc   'done'0d00
DiskSelectMsg
         asc   'Disk IF: original=$'00
DiskSelectedMsg
         asc   ' 35DISK selected=$'00
DiskRestoreMsg
         asc   'Disk IF restored=$'00
"""
if needle not in text:
    raise SystemExit('DoneMsg block not found.')
text = text.replace(needle, replacement, 1)

text = text.replace('IWMPROBE P0.2A4', 'IWMPROBE P0.2A5')
text = text.replace(
    'IWM bit 3 toggle/restore, immediate readback',
    '35DISK select + IWM bit 3 toggle/readback'
)

path.write_text(text, encoding='utf-8', newline='\n')
print('Applied IWMPROBE P0.2A5 35DISK-select probe.')
