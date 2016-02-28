#!/usr/bin/env python
import json
import sys
from pprint import pprint

import praw

sys.path.append(".") # For eclipse running
import chromabot

from chromabot import Config
from chromabot.db import DB, User, Region, TeamInfo


def create():
    c = Config()

    dbconn = DB(c)

    sess = dbconn.session()

    # Create team DB entries
    TeamInfo.create_defaults(sess, c)


def update():
    c = Config()

    dbconn = DB(c)

    sess = dbconn.session()

    # Create team DB entries
    ora = sess.query(TeamInfo).filter_by(id=0).first()
    ora.greeting = """
    Your team welcomes you!
    """

    per = sess.query(TeamInfo).filter_by(id=1).first()
    per.greeting = """
    Your team welcomes you!
    """

    sess.commit()
    print "Greetings updated"

def usage():
    print "Usage: add_teaminfo <create|update>"

if __name__ == '__main__':
    if len(sys.argv) != 2:
        usage()
    else:
        if sys.argv[1] == 'create':
            create()
        elif sys.argv[1] == 'update':
            update()
        else:
            usage()
