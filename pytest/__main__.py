from __future__ import annotations

import argparse
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
            suite.addTests(loader.discover(path if path != "." else "tests"))
    else:
        suite.addTests(loader.discover("tests"))

    verbosity = 1 if known.q else 2
    result = unittest.TextTestRunner(verbosity=verbosity).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
