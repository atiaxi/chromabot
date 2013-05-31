#!/usr/bin/env python
import json
import sys
from pprint import pprint

import praw

sys.path.append(".") # For eclipse running
import chromabot

from chromabot import Config
from chromabot.db import DB, User, Region

def main():
    c = Config()
    reddit = c.praw()

    dbconn = DB(c)
    dbconn.drop_all()
    dbconn.create_all()
    
    sess = dbconn.session()
    
    map = {}  # Because it holds regions, get it?
    
    source = sys.argv[1]
    with open(source) as srcfile:
        unconverted = json.load(srcfile)
    
    for region in unconverted:
        capital = None
        if 'capital' in region:
            capital = region['capital']
        created = Region(name=region['name'], srname=region['srname'],
                         capital=capital)
        sess.add(created)
        map[created.name] = created
    
    # Hook up the regions
    for region in unconverted:
        created = map[region['name']]
        for adjacent in region['connections']:
            created.add_border(map[adjacent])
    sess.commit()
    
    print map['Sapphire'].borders
    print Region.capital_for(1, sess)
    
if __name__ == '__main__':
    main()
