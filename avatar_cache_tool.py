"""Operator-controlled inspection and transfer for the avatar video cache."""

import argparse
import logging

from avatar_cache import AvatarCache

logger = logging.getLogger("AvatarCacheTool")


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="data/avatar/library")
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--inspect", action="store_true")
    actions.add_argument("--export")
    actions.add_argument("--import-bundle")
    args = parser.parse_args()

    cache = AvatarCache(args.root)
    if args.inspect:
        for record in cache.inspect():
            logger.info("%s", record)
    elif args.export:
        logger.info("%s", cache.export_bundle(args.export))
    elif args.import_bundle:
        logger.info("%s", cache.import_bundle(args.import_bundle))


if __name__ == "__main__":
    main()
