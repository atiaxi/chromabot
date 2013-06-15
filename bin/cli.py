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

def by_id(cls, id):
    return query(cls, id=id).first()

def by_name(cls, name):
    return query(cls, name=name).first()

def commit():
    return sess.commit()

def first(cls, **kw):
    return query(cls, **kw).first()

def query(cls, **kw):
    return sess.query(cls).filter_by(**kw)

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