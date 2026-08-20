from pathlib import Path
import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description='Fix P0.2C branch ranges after host overlay growth.')
    parser.add_argument('--project-root', default='.')
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    src = root / 'iigs' / 'spbench' / 'src' / 'SPBench.s'
    text = src.read_text(encoding='utf-8')

    old = '''         jsr   AllocateRawThunk
         bcs   RawPrepareFail

* Patch firmware JSR target in the source template.
'''
    new = '''         jsr   AllocateRawThunk
         bcc   FastCAllocOK
         brl   RawPrepareFail
FastCAllocOK

* Patch firmware JSR target in the source template.
'''

    if old in text:
        text = text.replace(old, new, 1)
        src.write_text(text, encoding='utf-8', newline='\n')
        print('Converted P0.2C RawPrepareFail branch to long-range-safe form.')
    elif new in text:
        print('P0.2C RawPrepareFail branch is already long-range safe.')
    else:
        raise SystemExit('Expected AllocateRawThunk/RawPrepareFail pattern not found.')


if __name__ == '__main__':
    main()
