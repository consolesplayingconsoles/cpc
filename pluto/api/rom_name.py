#!/usr/bin/env python3
"""Print the file name a homebrew build writes its ROM under.

It is the catalogue name Pluto publishes the build as (homebrew.lab_filename):
"<game> [<mod> by CPC v<version>]<ext>" for a mod, the title for a standalone game or
tool. A build that writes this name is never renamed on its way to Lab or a card.

    rom_name.py <build folder> <ext>      e.g. rom_name.py "$HERE" .bin
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "modules"))
from homebrew import service as homebrew  # noqa: E402

REPO = os.path.dirname(os.path.dirname(HERE))


def main(argv):
    if len(argv) != 3:
        sys.exit("usage: rom_name.py <build folder> <ext>")
    folder, ext = os.path.realpath(argv[1]), argv[2]
    item = next((i for i in homebrew.discover(REPO)
                 if os.path.realpath(os.path.join(REPO, i["path"])) == folder), None)
    if item is None:
        sys.exit("[ERROR] rom_name.py: %s is not a homebrew item (no build.sh under nodes/local/<node>/homebrew)" % folder)
    print(homebrew.lab_filename(item, "x" + ext))


if __name__ == "__main__":
    main(sys.argv)
