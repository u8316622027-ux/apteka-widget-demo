from __future__ import annotations

import argparse


def main() -> int:
    parser = argparse.ArgumentParser(prog="ruff", add_help=False)
    parser.add_argument("command", nargs="?")
    parser.add_argument("rest", nargs="*")
    parser.parse_known_args()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
