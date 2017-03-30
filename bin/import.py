#!/usr/bin/env python

import json
import sys
from os.path import realpath

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.append(".") # For eclipse running
from chromabot.db import Region, User


def main():
    full = "sqlite:///%s" % realpath(sys.argv[1])
    print full
    engine = create_engine(full)
    sessionfactory = sessionmaker(bind=engine)
    
    session = sessionfactory()
    
    with open(sys.argv[2], 'r') as f:
        text = f.read()
        print text
        j = json.loads(text)
        for user in j:
            u = User(**user)
            u.region = Region.capital_for(u.team, session)
            session.add(u)
            print "Imported %s" % u.name
        session.commit()

if __name__ == '__main__':
    main()
