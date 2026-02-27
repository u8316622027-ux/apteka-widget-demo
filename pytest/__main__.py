from __future__ import annotations

import argparse
from pathlib import Path
import unittest


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("paths", nargs="*")
    parser.add_argument("-q", action="store_true")
    known, _ = parser.parse_known_args()

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    if known.paths:
        for path in known.paths:
            if path == ".":
                suite.addTests(loader.discover("tests"))
                continue

            resolved = Path(path)
            if resolved.is_file():
                if resolved.is_absolute():
                    try:
                        start_dir = str(resolved.parent.relative_to(Path.cwd()))
                    except ValueError:
                        start_dir = str(resolved.parent)
                else:
                    start_dir = str(resolved.parent) if str(resolved.parent) else "."
                pattern = resolved.name
                suite.addTests(loader.discover(start_dir=start_dir, pattern=pattern, top_level_dir="."))
                continue

            suite.addTests(loader.discover(str(resolved)))
    else:
        suite.addTests(loader.discover("tests"))

    verbosity = 1 if known.q else 2
    result = unittest.TextTestRunner(verbosity=verbosity).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
