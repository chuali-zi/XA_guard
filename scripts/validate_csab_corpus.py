"""Validate an auditable CSAB corpus directory."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from bench.corpus import validate_corpus


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", type=Path)
    parser.add_argument("--profile", choices=("candidate", "formal"), default="formal")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = validate_corpus(args.corpus, profile=args.profile)
    encoded = json.dumps(result.as_dict(), ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0 if result.valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
