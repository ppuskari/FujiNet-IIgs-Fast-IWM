from pathlib import Path

p = Path('iigs/spbench/src/SPBench.s')
s = p.read_text(encoding='utf-8')

s = s.replace('SPBENCH P0.1B - direct SmartPort baseline',
              'SPBENCH P0.1B2 - IIgs dispatcher correction')

old = '''         lda   SlotPageOffset
         clc
         adc   #$C003
         sta   DispatchAddress

         lda   DispatchOffset
         and   #$00FF
         clc
         adc   DispatchAddress
         sta   DispatchAddress
'''

new = '''* P0.1B2: first hardware run printed dispatch $C500.
* The IIgs built-in slot-5 SmartPort dispatcher is
* $C50D (C5FF=$0A, ProDOS entry $C50A, +3).
* Force that known IIgs entry for this one-variable
* correction experiment.  DispatchOffset is retained
* and printed so the machine tells us its actual C5FF.

         lda   #$C50D
         sta   DispatchAddress
'''

if old not in s:
    raise SystemExit('dispatcher calculation block not found')
s = s.replace(old, new, 1)

old = '''         PushLong #DispatchMsg
         _WriteCString
         lda   DispatchAddress
         jsr   WriteHexWord

         PushLong #ThunkMsg
'''
new = '''         PushLong #DispatchMsg
         _WriteCString
         lda   DispatchAddress
         jsr   WriteHexWord

         PushLong #CnFFMsg
         _WriteCString
         lda   DispatchOffset
         and   #$00FF
         jsr   WriteHexWord

         PushLong #ThunkMsg
'''
if old not in s:
    raise SystemExit('PrintRawInfo block not found')
s = s.replace(old, new, 1)

old = '''DispatchMsg
         asc   'SmartPort dispatch=$'00
ThunkMsg
'''
new = '''DispatchMsg
         asc   'SmartPort dispatch=$'00
CnFFMsg
         asc   ' CnFF=$'00
ThunkMsg
'''
if old not in s:
    raise SystemExit('DispatchMsg block not found')
s = s.replace(old, new, 1)

s = s.replace('SmartPort READBLOCK failed. error=$',
              'SmartPort B2 READBLOCK failed. error=$')

p.write_text(s, encoding='utf-8', newline='\n')
print('Applied SPBENCH P0.1B2 dispatcher correction.')
