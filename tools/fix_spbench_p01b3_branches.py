from pathlib import Path

path = Path('iigs/spbench/src/SPBench.s')
text = path.read_text(encoding='utf-8')

replacements = [
    (
        '''         lda   >$00C001,x
         cmp   #$20
         bne   NotSmartPort8
''',
        '''         lda   >$00C001,x
         cmp   #$20
         beq   B3Sig01OK
         brl   NotSmartPort8
B3Sig01OK
'''
    ),
    (
        '''         lda   >$00C003,x
         cmp   #$00
         bne   NotSmartPort8
''',
        '''         lda   >$00C003,x
         cmp   #$00
         beq   B3Sig03OK
         brl   NotSmartPort8
B3Sig03OK
'''
    ),
    (
        '''         lda   >$00C005,x
         cmp   #$03
         bne   NotSmartPort8
''',
        '''         lda   >$00C005,x
         cmp   #$03
         beq   B3Sig05OK
         brl   NotSmartPort8
B3Sig05OK
'''
    ),
    (
        '''         lda   >$00C007,x
         cmp   #$00
         bne   NotSmartPort8
''',
        '''         lda   >$00C007,x
         cmp   #$00
         beq   B3Sig07OK
         brl   NotSmartPort8
B3Sig07OK
'''
    ),
]

changed = 0
for old, new in replacements:
    if old in text:
        text = text.replace(old, new, 1)
        changed += 1
    elif new not in text:
        raise SystemExit('Expected signature-branch pattern not found.')

if changed == 0:
    print('P0.1B3 signature branches are already long-range safe.')
else:
    if changed != 4:
        raise SystemExit(f'Expected 4 branch fixes; applied {changed}.')
    path.write_text(text, encoding='utf-8', newline='\n')
    print('Applied 4 P0.1B3 long-range signature branch fixes.')
