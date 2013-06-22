#!/usr/bin/env python
import logging
import time

import praw
from pyparsing import ParseException

from config import Config
from db import DB, Battle, Region, User, MarchingOrder, Processed
from parser import parse
from commands import Command, Context
from utils import base36decode, extract_command, num_to_team, name_to_id


class Bot(object):
    def __init__(self, config, reddit):
        self.config = config
        self.reddit = reddit
        self.db = DB(config)
        self.db.create_all()

        reddit.login(c.username, c.password)

    def attempt_post(self, srname, title, text):
        try:
            result = self.reddit.submit(srname, title=title, text=text)
            return result
        except praw.errors.APIException:
            return None

    def check_battles(self):
        session = self.db.session()
        battles = session.query(Battle).all()
        for battle in battles:
            post = self.reddit.get_submission(
                submission_id=name_to_id(battle.submission_id))
            self.process_post_for_battle(post, battle, session)

    def check_hq(self):
        hq = self.reddit.get_subreddit(self.config.headquarters)
        submissions = hq.get_new()
        for submission in submissions:
            if "[Recruitment]" in submission.title:
                self.recruit_from_post(submission)
                break  # Only recruit from the first one

    def check_messages(self):
        unread = reddit.get_unread(True, True)
        session = self.db.session()
        for comment in unread:
            # Only PMs, we deal with comment replies in process_post_for_battle
            if not comment.was_comment:
                player = self.find_player(comment, session)
                if player:
                    context = Context(player, self.config, session,
                                      comment, self.reddit)
                    self.command(comment.body, context)

            comment.mark_as_read()

    def command(self, text, context):
        text = text.lower()
        logging.info("Processing command: '%s' by %s" %
                     (text, context.player.name))
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

    def find_player(self, comment, session):
        player = session.query(User).filter_by(
        name=comment.author.name).first()
        if not player and getattr(comment, 'was_comment', None):
            comment.reply(Command.FAIL_NOT_PLAYER %
                              self.config.headquarters)
        return player

    def process_post_for_battle(self, post, battle, sess):
        p = sess.query(Processed).filter_by(battle=battle).all()
        seen = [entry.id36 for entry in p]

        post.replace_more_comments(threshold=0)
        flat_comments = praw.helpers.flatten_tree(
            post.comments)

        for comment in flat_comments:
            if comment.name in seen:
                continue
            if comment.author.name == self.config.username:
                continue
            cmd = extract_command(comment.body)
            if cmd:
                player = self.find_player(comment, sess)
                if player:
                    context = Context(player, self.config, sess,
                                          comment, self.reddit)
                    self.command(cmd, context)
            sess.add(Processed(id36=comment.name, battle=battle))
            sess.commit()

    def recruit_from_post(self, post):
        flat_comments = praw.helpers.flatten_tree(post.comments)
        session = self.db.session()
        for comment in flat_comments:
            name = comment.author.name
            if name == self.config.username:
                continue

            # Is this author already one of us?
            found = session.query(User).filter_by(
                name=name).first()
            if not found:
                base10_id = base36decode(comment.author.id)
                newbie = User(name=name,
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
                #logging.info("Already registered %s", comment.author.name)
                pass

    def update_game(self):
        session = self.db.session()
        MarchingOrder.update_all(session)
        results = Battle.update_all(session)

        for ready in results['begin']:
            ready.ends = ready.begins + self.config["game"]["battle_time"]
            text = ("War is now at your doorstep!  Mobilize your armies! "
                    "The battle has begun now, and will end at %s.\n\n"
                    "> Enter your commands in this thread, prefixed with "
                    "'>'") % ready.ends_str()
            post = self.reddit.get_submission(
                submission_id=name_to_id(ready.submission_id))
            post.edit(text)
            session.commit()

        for done in results['ended']:
            report = ["The battle is complete...\n"]
            for skirmish in done.skirmishes:
                if skirmish.parent_id is None:
                    report.append(skirmish.report())

            report.append("")
            report.append(("## Final Score:  Team Orangered: %d "
                           "Team Periwinkle: %d") % (done.score0, done.score1))
            if done.victor is not None:
                report.append("\n# The Victor:  Team %s" %
                              num_to_team(done.victor))
            else:
                report.append("# TIE")

            text = "\n".join(report)
            post = self.reddit.get_submission(
                submission_id=name_to_id(done.submission_id))
            post.edit(text)

            session.delete(done)
            session.commit()

    def run(self):
        logging.info("Bot started up")
        while(True):
            self.config.refresh()
            logging.info("Checking headquarters")
            self.check_hq()
            logging.info("Checking Messages")
            self.check_messages()
            logging.info("Checking Battles")
            self.check_battles()
            logging.info("Updating game state")
            self.update_game()
            logging.info("Sleeping")
            time.sleep(self.config["bot"]["sleep"])

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    c = Config()
    reddit = c.praw()

    bot = Bot(c, reddit)
    bot.run()
