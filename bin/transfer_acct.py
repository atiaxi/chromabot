#!/usr/bin/env python
import sys

sys.path.append(".")
sys.path.append("./chromabot")

from chromabot.config import Config
from chromabot.db import DB, User


def by_name(name, sess):
    result = sess.query(User).filter_by(name=name).first()
    if not result:
        print "Could not locate user %s" % name
    return result


def main():
    if len(sys.argv) < 3:
        print "Usage: transfter_acct.py <old_username> <new_username>"
        raise SystemExit
    config = Config()
    dbconn = DB(config)
    sess = dbconn.session()

    old = by_name(sys.argv[1].lower(), sess)
    newb = by_name(sys.argv[2].lower(), sess)

    newb.team = old.team
    newb.loyalists = old.loyalists
    newb.leader = old.leader
    newb.defectable = old.defectable
    newb.recruited = old.recruited
    newb.sector = old.sector

    newb.region = old.region

    sess.commit()


if __name__ == "__main__":
    main()
