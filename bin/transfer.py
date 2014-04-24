#!/usr/bin/env python
#!/usr/bin/env python
import sys
from os.path import realpath

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.append(".")
sys.path.append("./chromabot")

from chromabot.db import *

def read_users(filename):
    full = "sqlite:///%s" % realpath(filename)
    engine = create_engine(full)
    sessionfactory = sessionmaker(bind=engine)
    
    session = sessionfactory() 

    query = session.query(User).all()
    users = { u.name: {
        'name': u.name,
        'team': u.team,
        'loyalists': 100,
        'leader': u.leader,
        'defectable': u.defectable,
        'recruited': u.recruited,
    } for u in query}
    return users

def write_users(users, filename):
    full = "sqlite:///%s" % realpath(filename)
    engine = create_engine(full)
    sessionfactory = sessionmaker(bind=engine)
    
    session = sessionfactory()
    
    caps = [Region.capital_for(team, session) for team in range(0,2)]
    for userdict in users.values():
        user = User(**userdict)
        user.region = caps[user.team]
        session.add(user)
        print user.name
    session.commit()

def main():
    assert(sys.argv[1] != sys.argv[2])
    users = read_users(sys.argv[1])
    write_users(users, sys.argv[2])


if __name__ == '__main__':
    main()
