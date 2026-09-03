"""Operator-controlled Princess cache management; never generates implicitly."""
from __future__ import annotations
import argparse, json
from pathlib import Path
from princess_cache import PrincessCache

def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect/export/import the Princess media library")
    parser.add_argument("--root", default="data/princess/library")
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--inspect", action="store_true")
    actions.add_argument("--export")
    actions.add_argument("--import-bundle", metavar="ZIP")
    args = parser.parse_args()
    cache = PrincessCache(args.root)
    if args.inspect:
        print(json.dumps(cache.inspect(), indent=2))
    elif args.export:
        print(cache.export_bundle(args.export))
    else:
        print(json.dumps({"imported": cache.import_bundle(args.import_bundle)}))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
