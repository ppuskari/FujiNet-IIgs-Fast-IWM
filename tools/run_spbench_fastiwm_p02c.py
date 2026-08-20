from pathlib import Path
import argparse


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Run the P0.2C SPBENCH transform with the corrected structural checks.'
    )
    parser.add_argument('--project-root', default='.')
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    patch = root / 'tools' / 'patch_spbench_fastiwm_p02c.py'
    if not patch.is_file():
        raise SystemExit(f'P0.2C patch not found: {patch}')

    code = patch.read_text(encoding='utf-8')
    bad = "        '0x',  # harmless generic source marker check below is not relied on\n"
    if bad in code:
        code = code.replace(bad, '', 1)

    import sys
    old_argv = sys.argv
    try:
        sys.argv = [str(patch), '--project-root', str(root)]
        scope = {
            '__name__': '__main__',
            '__file__': str(patch),
        }
        exec(compile(code, str(patch), 'exec'), scope, scope)
    finally:
        sys.argv = old_argv


if __name__ == '__main__':
    main()
