#!/usr/bin/env python
import logging
from pprint import pprint

import praw
from pyparsing import ParseException

from config import Config
from db import DB, Battle, Region, User, MarchingOrder
from parser import parse
from commands import Command, Context
from utils import base36decode, num_to_team


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

    def check_messages(self):
        unread = reddit.get_unread(True, True)
        session = self.db.session()
        for comment in unread:
            # Only pay attention to PMs, for now
            if not comment.was_comment:
                player = session.query(User).filter_by(
                    name=comment.author.name).first()
                if player:
                    context = Context(player, self.config, session,
                                               comment, self.reddit)
                    self.command(comment.body, context)
                else:
                    comment.reply(Command.FAIL_NOT_PLAYER %
                                  self.config.headquarters)
            comment.mark_as_read()

    def command(self, text, context):
        try:
            parsed = parse(text)
            parsed.execute(context)
        except ParseException as pe:
            result = (
                "I'm sorry, I couldn't understand your command:"
                "\n\n"
                "> %s\n"
                "\nThe parsing error is below:\n\n"
                "    %s") % (text, pe)
            context.comment.reply(result)

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
                              loyalists=100,
                              leader=True)
                session.add(newbie)

                cap = Region.capital_for(newbie.team, session)
                if not cap:
                    logging.fatal("Could not find capital for %d" %
                                  newbie.team)
                newbie.region = cap

                session.commit()
                logging.info("Created combatant %s", newbie)

                reply = ("Welcome to Chroma!  You are now a %s "
                         "in the %s army, commanding a force of loyalists "
                         "%d people strong. You are currently encamped at %s"
                ) % (newbie.rank, num_to_team(newbie.team), newbie.loyalists,
                     cap.markdown())

                comment.reply(reply)
            else:
                logging.info("Already registered %s", comment.author.name)

    def update_game(self):
        session = self.db.session()
        MarchingOrder.update_all(session)
        results = Battle.update_all(session)
        for ready in results['begin']:
            title = "[Battle] The invaders have arrived!"
            text = ("War is now at your doorstep!  Mobilize your armies!\n\n"
                    "    Enter your commands in this thread")
            submitted = self.reddit.submit(ready.region.srname,
                                           title=title,
                                           text=text)
            ready.submission_id = submitted.id
            session.commit()

    def run(self):
        logging.info("Bot started up")
        logging.info("Checking headquarters")
        self.check_hq()
        logging.info("Checking Messages")
        self.check_messages()
        # TODO: Check hotspots
        logging.info("Updating game state")
        self.update_game()
        # TODO: Sleep

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    c = Config()
    reddit = c.praw()

    bot = Bot(c, reddit)
    bot.run()
