#!/usr/bin/env python
import logging
from pprint import pprint

import praw

from config import Config
from db import DB, Region, User


def base36decode(number):
    return int(number, 36)


def num_to_team(number):
    return ('Orangered', 'Periwinkle')[number]


class Bot(object):
    def __init__(self, config, reddit):
        self.config = config
        self.reddit = reddit
        self.db = DB(config)

        reddit.login(c.username, c.password)

    def check_hq(self):
        hq = self.reddit.get_subreddit(self.config.headquarters)
        submissions = hq.get_new()
        for submission in submissions:
            # TODO: Check for invasion announcements
            if "[Recruitment]" in submission.title:
                #pprint(submission.comments)
                self.recruit_from_post(submission)

    def check_pms(self):
        unread = reddit.get_unread(True, True)
        for comment in unread:
            # Only pay attention to PMs, for now
            if not comment.was_comment:
                if 'status' in comment.body:
                    reply = self.status_for(comment.author.name)
                    comment.reply(reply)
            comment.mark_as_read()

    def recruit_from_post(self, post):
        flat_comments = praw.helpers.flatten_tree(post.comments)
        session = self.db.session()
        for comment in flat_comments:
            base10_id = base36decode(comment.author.id)
            # Is this author already one of us?
            found = session.query(User).filter_by(
                name=comment.author.name).first()
            if not found:
                newbie = User(name=comment.author.name,
                              team=base10_id % 2,
                              loyalists=100)
                session.add(newbie)

                cap = Region.capital_for(newbie.team, session)
                newbie.region = cap

                session.commit()
                logging.info("Created combatant %s", newbie)

                reply = """
Welcome to Chroma!  You are now a general in the %s army,
commanding a force of loyalists %d people strong.  You are currently encamped
at [%s](/r/%s).
""" % (num_to_team(newbie.team), newbie.loyalists, cap.name, cap.srname)

                comment.reply(reply)
            else:
                logging.info("Already registered %s", comment.author.name)

    def run(self):
        logging.info("Bot started up")
        logging.info("Checking headquarters")
        #self.check_hq()
        logging.info("Checking PMs")
        self.check_pms()
        # TODO: Check hotspots
        # TODO: Sleep

    def status_for(self, username):
        session = self.db.session()
        found = session.query(User).filter_by(name=username).first()
        if found:
            result = """
You are a general in the %s army.

Your forces number %d loyalists strong.

You are currently encamped at [%s](/r/%s).
""" % (num_to_team(found.team), found.loyalists, found.region.name,
       found.region.srname)
        else:
            result = """
You don't have a status because, as far as I can tell, you're not playing!
Comment in the latest recruitment thread in /r/%s and change that!
""" % self.config.headquarters
            pass

        return result

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    c = Config()
    reddit = c.praw()

    bot = Bot(c, reddit)
    bot.run()
