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

def now():
    result = time.mktime(time.localtime())
    return (result, timestr(result))

def query(cls, **kw):
    return sess.query(cls).filter_by(**kw)

def timestr(self, secs=None):
    if secs is None:
        secs = time.mktime(time.localtime())
    return time.strftime("%Y-%m-%d %H:%M:%S GMT",
                          time.gmtime(secs))

def main():
    global sess
    logging.basicConfig(level=logging.DEBUG)
    
    # Some handy locals
    config = Config()
    dbconn = DB(config)
    sess = dbconn.session()
    
    
    vars = globals().copy()
    vars.update(locals())
    shell = code.InteractiveConsole(vars)
    shell.interact("Chromabot CLI ready")

if __name__ == "__main__":
    main()