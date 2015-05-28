#!/usr/bin/env python
#!/usr/bin/env python
import sys
from os.path import realpath

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.append(".")
sys.path.append("./chromabot")

from chromabot.db import *


def codeword_dict(cw):
    return {
        'code': cw.code,
        'word': cw.word,
    }

def make_session(filename):
    full = "sqlite:///%s" % realpath(filename)
    engine = create_engine(full)
    sessionfactory = sessionmaker(bind=engine)
    return sessionfactory()


def transfer_users(read_from, write_to):
    query = read_from.query(User).all()
    users = { u.name: {
        'name': u.name,
        'team': u.team,
        'loyalists': 100,
        'leader': u.leader,
        'defectable': u.defectable,
        'recruited': u.recruited,
        'codewords': [codeword_dict(cw) for cw in u.codewords]
    } for u in query}

    caps = [Region.capital_for(team, write_to) for team in range(0,2)]

    for userdict in users.values():
        old_codewords = userdict['codewords']
        # So we don't try to persist those codewords
        del userdict['codewords']
        user = User(**userdict)
        user.region = caps[user.team]
        write_to.add(user)
        print user.name
        write_to.commit()

        for cw_dict in old_codewords:
            new_cw = CodeWord(**cw_dict)
            new_cw.user = user
            write_to.add(new_cw)
            print "\t%s\t%s" % (new_cw.word, new_cw.code)
        write_to.commit()


def main():
    if len(sys.argv) != 3:
        print "Usage: %s read_from.db write_to.db" % sys.argv[0]
        exit()
    assert(sys.argv[1] != sys.argv[2])
    read_from = make_session(sys.argv[1])
    write_to = make_session(sys.argv[2])

    transfer_users(read_from, write_to)


if __name__ == '__main__':
    main()
