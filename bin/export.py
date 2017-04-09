#!/usr/bin/env python

import json
import sys
from collections import Counter
from os.path import realpath

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.append(".") # For eclipse running
from chromabot.db import User


CRIMSONS = [name.lower() for name in (
    "AberrantWhovian",
    "CubedCubie",
    "Sahdee",
    "Szkieletor",
    "Rokiux",
    "nothedarkweb",
)]


EMERALDS = [name.lower() for name in (
    "DBCrumpets",
    "a_flock_of_goats",
    "RansomWolf",
    "toworn",
    "Arrem_",
    "Lolzrfunni",
    "the_masked_redditor",
)]


TEAM_COUNT = {
    0: 0,
    1: 0,
}


def determine_team(user):
    if user.name in EMERALDS:
        print "Autoassigned %s to emerald" % user.name
        return 1
    if user.name in CRIMSONS:
        print "Autoassigned %s to crimson" % user.name
        return 0
    if TEAM_COUNT[0] < TEAM_COUNT[1]:
        TEAM_COUNT[0] += 1
        print "Assigned %s to crimson" % user.name
        return 0
    TEAM_COUNT[1] += 1
    print "Assigned %s to emerald" % user.name
    return 1


def main():
    full = "sqlite:///%s" % realpath(sys.argv[1])
    if len(sys.argv) < 3:
        raise ValueError("Usage: export.py <dbfile> <outfile>")
    engine = create_engine(full)
    sessionfactory = sessionmaker(bind=engine)
    
    session = sessionfactory()
    
    users = session.query(User).all()
    results = [
        { 'id': u.id,
         'name': u.name,
         'team': u.team,
         'loyalists': 300,
         'defectable': True
        } for u in users
    ]
    with open(sys.argv[2], "w") as outfile:
        #j = json.dumps(results)
        json.dump(results, outfile)

if __name__ == '__main__':
    main()
