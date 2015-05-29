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

    source = sys.argv[1]

    with open(source) as srcfile:
        unconverted = json.load(srcfile)

    for region_dict in unconverted:
        name = region_dict['name'].lower()
        region = sess.query(cls).filter_by(name=name).first()
        print "\t%s" % name
        aliases = region_dict.get("aliases", [])

        for alias in aliases:
            prev = sess.query(Alias).filter_by(name=alias).first()
            if prev:
                print "\t\t[old] %s" % prev.name
            else:
                new_alias = region.create_alias(alias)
                print "\t\t[NEW] %s" % new_alias.name

if __name__ == '__main__':
    main()
