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
from chromabot.commands import Context, InvadeCommand


def alias(region, name):
    return region.create_alias(name)


def all(cls, **kw):
    return query(cls, **kw).all()


def all_as_dict(cls):
    result = {}
    for item in all(cls):
        result[item.name] = item
    return result


def battle_adopt(battle, postid):
    battle.ends = battle.begins + 10800
    battle.display_ends = battle.ends
    battle.submission_id="t3_%s" % postid
    sess.commit()


def cancel_battle(battle):
    global reddit

    post = reddit.get_submission(
        submission_id=name_to_id(battle.submission_id))
    post.edit("*This battle has been canceled*")
    sess.delete(battle)
    sess.commit()


def context(player=None, comment=None):
    if not player:
        player = by_id(User, 1)
    return Context(player, config, sess, comment, reddit)


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
    return battle


def by_id(cls, id):
    result = query(cls, id=id).first()
    print result
    return result


def by_name(cls, name):
    if cls == User:
        name = name.lower()
    result = query(cls, name=name).first()
    print result
    return result


def by_alias(name):
    result = query(Alias, name=name).first()
    print result
    return result.region


def commit():
    return sess.commit()


def create_user(name, team):
    newbie = User(name=name, team=team, loyalists=100, leader=True)
    sess.add(newbie)
    cap = Region.capital_for(team, sess)
    newbie.region = cap
    sess.commit()
    return newbie


def defect(player):
    other_team = [0, 1][player.team - 1]
    player.team = other_team
    player.region = Region.capital_for(other_team, sess)
    sess.commit()


def first(cls, **kw):
    return query(cls, **kw).first()


def query(cls, **kw):
    return sess.query(cls).filter_by(**kw)


def timestr(self, secs=None):
    if secs is None:
        secs = time.mktime(time.localtime())
    return time.strftime("%Y-%m-%d %H:%M:%S GMT",
                          time.gmtime(secs))


def login(self):
    reddit.login(config.username, config.password)


def main():
    global reddit
    global sess
    global config
    logging.basicConfig(level=logging.DEBUG)
    
    # Some handy locals
    config = Config()
    dbconn = DB(config)
    sess = dbconn.session()
    reddit = config.praw()
    #reddit.login(config.username, config.password)
    
    vars = globals().copy()
    vars.update(locals())
    shell = code.InteractiveConsole(vars)
    shell.interact("Chromabot CLI ready")

if __name__ == "__main__":
    main()
