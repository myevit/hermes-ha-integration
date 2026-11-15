"""Explicitly install the packaged shim into a named owning profile, never activate."""
import argparse
import shutil
from pathlib import Path


def install(home):
    home = Path(home).resolve(strict=True)
    if home.parent.name != 'profiles' or home.name == 'default':
        raise ValueError('explicit named profile home required')
    target = home / 'plugins' / 'hermes-ha-native-engine'
    # Never replace an existing owner/plugin silently.
    if target.exists():
        raise FileExistsError(target)
    shutil.copytree(Path(__file__).parent / 'plugin', target,
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home', type=Path, required=True)
    args = parser.parse_args()
    print(install(args.home))


if __name__ == '__main__':
    main()
