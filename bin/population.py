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

def tierreport(sess):
    query = sess.query(User)
    orange = query.filter_by(team=0)
    peri = query.filter_by(team=1)

    tiers = [(100, 101), (101, 150), (150, 200), (200, 300), (300, 500),
             (500, 750), (750, 751)]
    for min_p, max_p in tiers:
        q = (query.filter(User.loyalists >= min_p).
                  filter(User.loyalists < max_p))
        orange = q.filter_by(team=0)
        peri = q.filter_by(team=1)
        print "\nBetween %d and %d:\n" % (min_p, max_p)
        print "OR: %d\n" % orange.count()
        print "PW: %d\n" % peri.count()

def popreport(query):
    orange = query.filter_by(team=0)
    peri = query.filter_by(team=1)
    print "* Orangered Players: %d\n" % orange.count()
    print "* Orangered Troops: %d\n" % sum(player.loyalists for player in orange)
    print "* Periwinkle Players: %d\n" % peri.count()
    print "* Periwinkle: %d\n" % sum(player.loyalists for player in peri)

def main():
    config = Config()
    dbconn = DB(config)
    sess = dbconn.session()

    unfiltered = sess.query(User)
    print "Total number of all troops:\n"
    popreport(unfiltered)
    print "Total number of troops for players in at least 1 battle:\n"
    popreport(unfiltered.filter(User.loyalists > 100))

    tierreport(sess)
        

if __name__ == '__main__':
    main()