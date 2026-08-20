from pathlib import Path
import re

path = Path('iigs/spbench/src/SPBench.s')
text = path.read_text(encoding='utf-8')

if 'SPBENCH P0.1B3' in text:
    print('SPBENCH source is already P0.1B3.')
    raise SystemExit(0)

if 'SPBENCH P0.1B' not in text:
    raise SystemExit('Expected P0.1B source baseline.')

# ------------------------------------------------------------------
# Identity / comments / visible diagnostics.
# ------------------------------------------------------------------
text = text.replace('* SPBENCH P0.1B\n', '* SPBENCH P0.1B3\n', 1)
text = text.replace(
    '* It calls the Apple IIgs SmartPort firmware dispatcher\n'
    '* directly with extended READBLOCK command $41.\n',
    '* It calls the Apple IIgs SmartPort firmware dispatcher\n'
    '* directly with standard READBLOCK command $01.\n'
    '* The command list and 512-byte staging buffer are both\n'
    '* inside the same fixed/locked bank-$00 allocation.\n',
    1
)
text = text.replace(
    "         asc   'SPBENCH P0.1B - direct SmartPort baseline'0d\n"
    "         asc   'Raw extended READBLOCK $41, 512 bytes/call'0d\n",
    "         asc   'SPBENCH P0.1B3 - standard SmartPort baseline'0d\n"
    "         asc   'Raw READBLOCK $01, bank0 512-byte stage'0d\n",
    1
)
text = text.replace(
    "         asc   '  mode=EXT $41'00",
    "         asc   '  mode=STD $01 BANK0'00",
    1
)
text = text.replace(
    "         asc   'SmartPort READBLOCK failed. error=$'00",
    "         asc   'SmartPort B3 READBLOCK failed. error=$'00",
    1
)

# ------------------------------------------------------------------
# Device discovery: keep the SmartPort unit as ordinary app state.
# RawCmdUnit used to live in the extended app-bank command list; B3
# relocates the actual command list into bank 0.
# ------------------------------------------------------------------
text = text.replace(
    '* Device found.  Preserve the SmartPort unit byte in\n'
    '* the extended command list.\n',
    '* Device found.  Preserve the SmartPort unit byte so\n'
    '* PrepareRawSmartPort can patch the bank-zero list.\n',
    1
)

# ------------------------------------------------------------------
# Replace PrepareRawSmartPort as one atomic block.  For this IIgs
# experiment we deliberately force the confirmed slot-5 dispatcher
# $C50D while retaining C5FF as a diagnostic.  The source template is
# patched before copying the complete thunk/list/buffer region to bank 0.
# ------------------------------------------------------------------
prepare_pattern = re.compile(
    r'PrepareRawSmartPort\n.*?\nNotSmartPort8\n',
    re.S
)
prepare_replacement = r'''PrepareRawSmartPort
* X = slot * $100 for long indexed reads of $Cnxx.

         lda   proDINFO+$0E
         and   #$00FF
         xba
         tax
         sta   SlotPageOffset

* Verify the standard ProDOS/SmartPort signature.

         sep   #$20

         lda   >$00C001,x
         cmp   #$20
         bne   NotSmartPort8

         lda   >$00C003,x
         cmp   #$00
         bne   NotSmartPort8

         lda   >$00C005,x
         cmp   #$03
         bne   NotSmartPort8

         lda   >$00C007,x
         cmp   #$00
         bne   NotSmartPort8

* Preserve the real C5FF value for the result screen.

         lda   >$00C0FF,x
         sta   CnFFValue
         rep   #$20

* P0.1B2 proved this ROM 3 slot-5 dispatcher is $C50D.
* Keep B3 fixed to that known-good entry so the only variable here is
* extended $41 versus standard $01 command framing.

         lda   #$C50D
         sta   DispatchAddress

         jsr   AllocateRawThunk
         bcs   RawPrepareFail

* Patch firmware JSR target in the source template.

         lda   DispatchAddress
         sta   ThunkDispatch+1

* Compute the bank-zero addresses of the copied standard parameter list
* and 512-byte staging buffer.  Standard SmartPort pointers are 16-bit,
* which is exactly why both objects are carried in this bank-zero region.

         lda   RawCodePtr
         clc
         adc   #RawCmdListTemplate-ThunkTemplate
         sta   RawCmdListPtr
         sta   ThunkCmdPtr

         lda   RawCodePtr
         clc
         adc   #RawStageBuffer-ThunkTemplate
         sta   RawStagePtr
         sta   RawCmdBufferTemplate

         sep   #$20
         lda   RawCmdUnit
         sta   RawCmdUnitTemplate
         rep   #$20

* Copy thunk + standard command list + 512-byte stage into bank zero.

         PushLong #ThunkTemplate
         PushLong RawCodePtr
         pea   $0000
         pea   RawRegionSize
         _BlockMove

* Patch application's long call to the allocated bank-zero helper.

         lda   RawCodePtr
         sta   RawSmartPortCall+1

         sep   #$20
         lda   RawCodePtr+2
         sta   RawSmartPortCall+3
         rep   #$20

* Patch one long store in the timed loop so each requested block number
* goes directly into the copied bank-zero 24-bit block field.  All test
* block numbers fit in 16 bits; the third byte remains zero.

         lda   RawCodePtr
         clc
         adc   #RawCmdBlockTemplate-ThunkTemplate
         sta   RawBlockStore+1

         sep   #$20
         lda   #$00
         sta   RawBlockStore+3
         rep   #$20

         clc
         rts

NotSmartPort8
'''
text, n = prepare_pattern.subn(prepare_replacement, text, count=1)
if n != 1:
    raise SystemExit('Unable to replace PrepareRawSmartPort block.')

# ------------------------------------------------------------------
# Allocate the whole bank-zero raw region, not just the code thunk.
# ------------------------------------------------------------------
# The B1 source may be either original PushLong #ThunkSize form or the
# Merlin32-safe PEA form committed by CI.  Normalize both occurrences.
text = text.replace('         PushLong #ThunkSize', '         pea   $0000\n         pea   RawRegionSize')
text = text.replace('         pea   $0000\n         pea   ThunkSize',
                    '         pea   $0000\n         pea   RawRegionSize')

# ------------------------------------------------------------------
# Timed loop: write the low 16 bits of the block number directly into
# the bank-zero standard command list, then call SmartPort.  Standard
# READBLOCK is fixed at 512 bytes, so carry-clear itself is the success
# condition; no X/Y transfer-count interpretation is required.
# ------------------------------------------------------------------
loop_old = '''RawReadLoop
         lda   CurrentBlock
         sta   RawCmdBlock
         lda   CurrentBlock+2
         sta   RawCmdBlock+2

RawSmartPortCall
         jsl   $000000
         bcc   RawReadReturned
'''
loop_new = '''RawReadLoop
         lda   CurrentBlock
RawBlockStore
         sta   >$000000

RawSmartPortCall
         jsl   $000000
         bcc   RawReadReturned
'''
if loop_old not in text:
    raise SystemExit('Unable to locate P0.1B RawReadLoop.')
text = text.replace(loop_old, loop_new, 1)

short_pattern = re.compile(
    r'RawReadReturned\n\* SmartPort ReadBlock reports bytes transferred in X/Y\.\n'
    r'\* The bank-zero helper records them as a 16-bit count\.\n\n'
    r'         lda   RawTransferCount\n'
    r'         cmp   #BlockSize\n'
    r'         beq   RawTransferComplete\n\n'
    r'         lda   #ErrShortRead\n'
    r'         sta   LastError\n'
    r'         jsr   FinishTiming\n'
    r'         sec\n'
    r'         rts\n\n'
    r'RawTransferComplete\n',
    re.S
)
text, n = short_pattern.subn(
    'RawReadReturned\n* Standard READBLOCK is exactly one 512-byte block.\n',
    text,
    count=1
)
if n != 1:
    raise SystemExit('Unable to remove extended transfer-count check.')

# ------------------------------------------------------------------
# Standard SmartPort inline command format:
#   JSR dispatcher
#   db $01
#   dw parameter-list-address
# ------------------------------------------------------------------
old_inline = '''ThunkDispatch
         jsr   $FFFF
         db    $41
         adrl  RawCmdList
'''
new_inline = '''ThunkDispatch
         jsr   $FFFF
         db    $01
ThunkCmdPtr
         dw    $FFFF
'''
if old_inline not in text:
    raise SystemExit('Unable to locate extended SmartPort inline call.')
text = text.replace(old_inline, new_inline, 1)

# On standard READBLOCK success we do not need to interpret X/Y.
old_success = '''ThunkSuccess
* ReadBlock returns the transferred byte count in X/Y.
* In emulation mode X is the low byte and Y is the high
* byte.  Save both directly into the application bank.

         txa
         sta   >RawTransferCount
         tya
         sta   >RawTransferCount+1
         ldy   #$00
'''
new_success = '''ThunkSuccess
* Standard READBLOCK success is fixed at one 512-byte block.
         ldy   #$00
'''
if old_success not in text:
    raise SystemExit('Unable to locate extended success-count block.')
text = text.replace(old_success, new_success, 1)

# ------------------------------------------------------------------
# Replace the old app-bank extended parameter list with the bank-zero
# standard list and its 512-byte staging area, appended to the copied
# template region.
# ------------------------------------------------------------------
region_pattern = re.compile(
    r'ThunkEnd\nThunkSize\s+equ\s+ThunkEnd-ThunkTemplate\n\n'
    r'\*-------------------------------------------------\n'
    r'\* SmartPort extended READBLOCK parameter list\.\n'
    r'.*?RawCmdBlock\n\s+adrl\s+\$00000000\n',
    re.S
)
region_replacement = r'''ThunkEnd

*-------------------------------------------------
* Standard SmartPort READBLOCK bank-zero data.
*
* FujiNet's own Apple SmartPort driver uses:
*   byte  parameter count = 3
*   byte  unit
*   word  data buffer pointer
*   3-byte block number
*-------------------------------------------------

RawCmdListTemplate
         db    $03
RawCmdUnitTemplate
         db    $00
RawCmdBufferTemplate
         dw    $0000
RawCmdBlockTemplate
         db    $00,$00,$00

RawStageBuffer
         ds    512

RawRegionEnd
ThunkSize      equ   ThunkEnd-ThunkTemplate
RawRegionSize  equ   RawRegionEnd-ThunkTemplate
'''
text, n = region_pattern.subn(region_replacement, text, count=1)
if n != 1:
    raise SystemExit('Unable to replace extended parameter-list region.')

# ------------------------------------------------------------------
# App state required by B3.
# ------------------------------------------------------------------
state_old = '''RawHandle      ds    4
RawCodePtr     ds    4
SlotPageOffset ds    2
DispatchOffset ds    2
DispatchAddress ds   2
RawTransferCount ds 2
'''
state_new = '''RawHandle      ds    4
RawCodePtr     ds    4
SlotPageOffset ds    2
DispatchOffset ds    2
DispatchAddress ds   2
CnFFValue      ds    2
RawCmdUnit     ds    2
RawCmdListPtr  ds    2
RawStagePtr    ds    2
RawTransferCount ds 2
'''
if state_old not in text:
    raise SystemExit('Unable to locate raw state block.')
text = text.replace(state_old, state_new, 1)

# ------------------------------------------------------------------
# Print the C5FF diagnostic so B2/B3 runs remain self-describing.
# ------------------------------------------------------------------
print_old = '''         lda   DispatchAddress
         jsr   WriteHexWord

         PushLong #ThunkMsg
'''
print_new = '''         lda   DispatchAddress
         jsr   WriteHexWord

         PushLong #CnFFMsg
         _WriteCString
         lda   CnFFValue
         and   #$00FF
         jsr   WriteHexWord

         PushLong #ThunkMsg
'''
if print_old not in text:
    raise SystemExit('Unable to patch raw diagnostic output.')
text = text.replace(print_old, print_new, 1)

msg_old = "DispatchMsg\n         asc   'SmartPort dispatch=$'00\nThunkMsg\n"
msg_new = "DispatchMsg\n         asc   'SmartPort dispatch=$'00\nCnFFMsg\n         asc   ' CnFF=$'00\nThunkMsg\n"
if msg_old not in text:
    raise SystemExit('Unable to add CnFF message.')
text = text.replace(msg_old, msg_new, 1)

# ------------------------------------------------------------------
# Sanity guards.
# ------------------------------------------------------------------
for forbidden in ('db    $41', 'adrl  RawCmdList'):
    if forbidden in text:
        raise SystemExit(f'Extended-call residue remains: {forbidden}')

required = (
    'SPBENCH P0.1B3',
    'db    $01',
    'ThunkCmdPtr',
    'RawCmdListTemplate',
    'RawStageBuffer',
    'RawRegionSize',
    'RawBlockStore',
    "mode=STD $01 BANK0",
)
for item in required:
    if item not in text:
        raise SystemExit(f'Missing required B3 marker: {item}')

path.write_text(text, encoding='utf-8', newline='\n')
print('Applied SPBENCH P0.1B3 standard READBLOCK/bank-zero-stage patch.')
