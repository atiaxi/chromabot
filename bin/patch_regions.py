#!/usr/bin/env python
import json
import sys
from pprint import pprint

import praw

sys.path.append(".") # For eclipse running
import chromabot

from chromabot import Config
from chromabot.db import DB, User, Region
from stamp import stamp

def main():
    c = Config()
    reddit = c.praw()

    dbconn = DB(c)
    
    sess = dbconn.session()
    
    source = sys.argv[1]
    regions = Region.patch_from_json(sess, json_file=source, verbose=True)
    
if __name__ == '__main__':
    main()
