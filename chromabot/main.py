#!/usr/bin/env python
import json
import logging
import os.path
import random
import time
from urllib import urlencode

import praw
from pyparsing import ParseException

import db
from config import Config
from db import DB, Battle, Region, User, MarchingOrder, Processed
from parser import parse
from commands import (Command, Context, failable, InvadeCommand,
                      SkirmishCommand, StatusCommand)
from utils import (base36decode, extract_command, num_to_team, name_to_id, now,
                   timestr, version)


class Bot(object):
    def __init__(self, config, reddit):
        self.config = config
        self.reddit = reddit
        self.db = DB(config)
        self.db.create_all()
        self.session = self.db.session()

    @failable
    def check_battles(self):
        session = self.session
        battles = session.query(Battle).all()
        for battle in battles:
            post = self.reddit.get_submission(
                comment_limit=None,
                submission_id=name_to_id(battle.submission_id))
            if post:
                self.process_post_for_battle(post, battle, session)

    @failable
    def check_hq(self):
        hq = self.reddit.get_subreddit(self.config.headquarters)
        submissions = hq.get_new()
        for submission in submissions:
            if "[Recruitment]" in submission.title:
                self.recruit_from_post(submission)
                break  # Only recruit from the first one

    @failable
    def check_messages(self):
        unread = reddit.get_unread(True, True)
        session = self.session
        for comment in unread:
            # Only PMs, we deal with comment replies in process_post_for_battle
            if not comment.was_comment:
                player = self.find_player(comment, session)
                if player:
                    cmd = extract_command(comment.body)
                    if not cmd:
                        cmd = comment.body
                    context = Context(player, self.config, session,
                                      comment, self.reddit)
                    self.command(cmd, context)

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
            context.reply(result)

    def find_player(self, comment, session):
        if comment.author:  # Some messages (mod invites) don't have authors
            player = session.query(User).filter_by(
            name=comment.author.name.lower()).first()
            if not player and getattr(comment, 'was_comment', None):
                comment.reply(Command.FAIL_NOT_PLAYER %
                                  self.config.headquarters)
            return player
        return None

    @failable
    def generate_markdown_report(self, loop_start):
        """
        Separate from the others as this logs to a sidebar rather than
        a file
        """
        s = self.session

        land_report = StatusCommand.lands_status_for(s, self.config)
        hq = self.reddit.get_subreddit(self.config.headquarters)

        cur = now()
        elapsed = (cur - loop_start) + self.config["bot"]["sleep"]
        version_str = version(self.config)

        bot_report = ("Bot Status:\n\n"
                      "* Last run at %s\n\n"
                      "* Seconds per Frame: %d\n\n"
                      "* Version: %s") % (timestr(cur), elapsed, version_str)

        report = "%s\n\n%s" % (land_report, bot_report)

        # This is apparently not immediately done, or there's some caching.
        # Keep an eye on it.
        hq.update_settings(description=report)

    def generate_reports(self, loop_start):
        logging.info("Generating reports")
        self.generate_markdown_report(loop_start)
        rdir = self.config["bot"].get("report_dir")
        if not rdir:
            return
        s = self.session
        regions = s.query(Region).all()
        with open(os.path.join(rdir, "report.txt"), 'w') as url:
            urldict = {}
            for r in regions:
                if r.owner is not None:
                    owner = r.owner
                else:
                    owner = -1
                urldict[r.srname] = owner
            url.write(urlencode(urldict))

        with open(os.path.join(rdir, "report.json"), 'w') as j:
            jdict = {}
            for r in regions:
                rdict = {}
                rdict['name'] = r.name
                rdict['srname'] = r.srname
                if r.owner is not None:
                    rdict['owner'] = r.owner
                else:
                    rdict['owner'] = -1

                if r.battle:
                    if r.battle.has_started():
                        rdict['battle'] = 'underway'
                    else:
                        rdict['battle'] = 'preparing'
                else:
                    rdict['battle'] = 'none'
                jdict[r.srname] = rdict
            j.write(json.dumps(jdict))

    def process_post_for_battle(self, post, battle, sess):
        p = sess.query(Processed).filter_by(battle=battle).all()
        seen = [entry.id36 for entry in p]

        replaced = post.replace_more_comments(limit=None, threshold=0)
        if replaced:
            logging.info("Comments that went un-replaced: %s" % replaced)
        flat_comments = praw.helpers.flatten_tree(
            post.comments)

        for comment in flat_comments:
            if comment.name in seen:
                continue
            if not comment.author:  # Deleted comments don't have an author
                continue
            if comment.author.name.lower() == self.config.username.lower():
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

    @failable
    def recruit_from_post(self, post):
        post.replace_more_comments(threshold=0)
        flat_comments = praw.helpers.flatten_tree(post.comments)
        session = self.session
        for comment in flat_comments:
            if not comment.author:  # Deleted comments don't have an author
                continue
            name = comment.author.name.lower()
            if name == self.config.username.lower():
                continue

            # Is this author already one of us?
            found = session.query(User).filter_by(
                name=name).first()
            if not found:
                team = 0
                assignment = self.config['game']['assignment']
                if assignment == 'uid':
                    base10_id = base36decode(comment.author.id)
                    team = base10_id % 2
                elif assignment == "random":
                    team = random.randint(0, 1)
                is_leader = name in self.config["game"]["leaders"]
                newbie = User(name=name,
                              team=team,
                              loyalists=100,
                              leader=is_leader)
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
                ) % (newbie.rank,
                     num_to_team(newbie.team, self.config),
                     newbie.loyalists,
                     cap.markdown())
                comment.reply(reply)
            else:
                #logging.info("Already registered %s", comment.author.name)
                pass

    @failable
    def update_game(self):
        session = self.session
        MarchingOrder.update_all(session)

        results = Region.update_all(session, self.config)
        to_add = []
        for newternal in results['new_eternal']:
            title = "The Eternal Battle Rages On"
            post = InvadeCommand.post_invasion(title, newternal, self.reddit)
            if post:
                newternal.submission_id = post.name
                to_add.append(newternal)
            else:
                logging.warn("Couldn't submit eternal battle thread")
                session.rollback()
        if to_add:
            session.add_all(to_add)
            session.commit()

        results = Battle.update_all(session, self.config)

        for ready in results['begin']:
            ready.display_ends = (ready.begins +
                self.config["game"]["battle_time"])

            # Actual ending is within battle_lockout of the end
            chooserange = self.config["game"]["battle_lockout"]
            chosen = random.randint(0, chooserange)
            ready.ends = ready.display_ends - (chooserange / 2) + chosen

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
            report += done.report(self.config)

            report.append("")

            if done.old_buffs:
                report.append("Buffs in effect for Team %s\n" %
                              num_to_team(done.old_owner, self.config))
                for buff in done.old_buffs:
                    report.append("  * %s" % buff.name)
                report.append("")

            team0_name = num_to_team(0, self.config)
            team1_name = num_to_team(1, self.config)
            report.append(("## Final Score:  Team %s: %d "
                           "Team %s: %d") % (team0_name, done.score0,
                                             team1_name, done.score1))
            if done.victor is not None:
                report.append("\n# The Victor:  Team %s" %
                              num_to_team(done.victor, self.config))
            else:
                report.append("# TIE")

            text = "\n".join(report)
            post = self.reddit.get_submission(
                submission_id=name_to_id(done.submission_id))
            post.edit(text)

            # Update all the skirmish summaries
            for s in done.toplevel_skirmishes():
                c = Context(player=None,
                            config=self.config,
                            session=None,
                            comment=None,
                            reddit=self.reddit)
                SkirmishCommand.update_summary(c, s)

            session.delete(done)
            session.commit()
        db.Buff.update_all(session)

    @failable
    def login(self):
        reddit.login(c.username, c.password)
        return True

    def run(self):
        logging.info("Bot started up")
        logged_in = self.login()
        while(logged_in):
            loop_start = now()
            self.config.refresh()
            logging.info("Checking headquarters")
            self.check_hq()
            logging.info("Checking Messages")
            self.check_messages()
            logging.info("Checking Battles")
            self.check_battles()
            logging.info("Updating game state")
            self.update_game()
            # generate_reports logs itself
            self.generate_reports(loop_start)
            logging.info("Sleeping")
            time.sleep(self.config["bot"]["sleep"])
        logging.fatal("Unable to log into bot; shutting down")

if __name__ == '__main__':
    fmt = "%(asctime)s: %(levelname)s %(message)s"
    logging.basicConfig(level=logging.INFO, format=fmt)
    c = Config()
    reddit = c.praw()

    bot = Bot(c, reddit)
    bot.run()
