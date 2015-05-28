#!/usr/bin/env python

import sys
from collections import defaultdict

sys.path.append(".")
sys.path.append("./chromabot")

from chromabot.config import Config
from chromabot.db import *


def main():
    config = Config()
    dbconn = DB(config)
    sess = dbconn.session()

    aliases = {
        region.name: [a.name for a in region.aliases]
            for region in sess.query(Region).all()
    }

    for region_name in sorted(aliases.keys()):
        print "  * **%s**: %s" % (region_name, ", ".join(aliases[region_name]))

if __name__ == '__main__':
    main()
