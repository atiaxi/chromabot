#!/usr/bin/env python

import json
import sys
from os.path import realpath

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.append(".") # For eclipse running
from chromabot.db import User

def main():
    full = "sqlite:///%s" % realpath(sys.argv[1])
    engine = create_engine(full)
    sessionfactory = sessionmaker(bind=engine)
    
    session = sessionfactory()
    
    users = session.query(User).all()
    results = [
        { 'id': u.id,
         'name': u.name,
         'team': u.team,
         'loyalists': u.loyalists + 15,
         'defectable': False
        } for u in users
    ]
    j = json.dumps(results)
    print j

if __name__ == '__main__':
    main()