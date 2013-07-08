#!/usr/bin/env python

import code
import logging
import readline
import sys

sys.path.append(".")
sys.path.append("./chromabot")

from config import Config
from db import *
from utils import *
from chromabot.commands import InvadeCommand

def all(cls, **kw):
    return query(cls, **kw).all()

def all_as_dict(cls):
    result = {}
    for item in all(cls):
        result[item.name] = item
    return result

def battle_adopt(battle, postid):
    battle.ends = battle.begins + 10800
    battle.submission_id="t3_%s" % postid
    sess.commit()

def end_battle(battle):
    battle.ends = battle.begins + 1
    sess.commit()

def fast_battle(named='snooland'):
    where = by_name(Region, named)
    battle = where.new_battle_here(now() + 60)
    post = InvadeCommand.post_invasion("Fast battle go!", battle,
        reddit)
    print "Posted as: %s" % post
    battle.submission_id=post.name
    
    for user in all(User):
        user.region = where
    sess.commit()

def by_id(cls, id):
    result = query(cls, id=id).first()
    print result
    return result

def by_name(cls, name):
    result = query(cls, name=name).first()
    print result
    return result

def commit():
    return sess.commit()

def first(cls, **kw):
    return query(cls, **kw).first()

def query(cls, **kw):
    return sess.query(cls).filter_by(**kw)

def timestr(self, secs=None):
    if secs is None:
        secs = time.mktime(time.localtime())
    return time.strftime("%Y-%m-%d %H:%M:%S GMT",
                          time.gmtime(secs))

def main():
    global reddit
    global sess
    logging.basicConfig(level=logging.DEBUG)
    
    # Some handy locals
    config = Config()
    dbconn = DB(config)
    sess = dbconn.session()
    reddit = config.praw()
    reddit.login(config.username, config.password)
    
    vars = globals().copy()
    vars.update(locals())
    shell = code.InteractiveConsole(vars)
    shell.interact("Chromabot CLI ready")

if __name__ == "__main__":
    main()