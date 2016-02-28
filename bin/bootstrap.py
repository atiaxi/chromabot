#!/usr/bin/env python
import json
import sys
from pprint import pprint

import praw

sys.path.append(".") # For eclipse running
import chromabot

from chromabot import Config
from chromabot.db import DB, User, Region, TeamInfo
from stamp import stamp


def main():
    c = Config()
    reddit = c.praw()

    dbconn = DB(c)
    dbconn.drop_all()
    dbconn.create_all()
    
    sess = dbconn.session()
    
    source = sys.argv[1]
    regions = Region.create_from_json(sess, json_file=source)

    # Create team DB entries
    TeamInfo.create_defaults(sess, c)

    stamp()
    
if __name__ == '__main__':
    main()
