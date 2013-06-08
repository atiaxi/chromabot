import time

import db
from db import Battle, Region
from utils import num_to_team


class Context(object):
    def __init__(self, player, config, session, comment, reddit):
        self.player = player    # a DB object
        self.config = config
        self.session = session
        self.comment = comment  # a praw object
        self.reddit = reddit    # root praw object

    def reply(self, reply):
        self.comment.reply(reply)


class Command(object):

    FAIL_NOT_PLAYER = """
Sorry, I can't help you - first of all, you messaged a bot.  Secondly, you
don't seem to actually be playing the game I run!  If you'd like to change
that, comment in the latest recruitment thread in /r/%s"""

    def __init__(self, tokens):
        self.tokens = tokens

    def execute(self, context):
        raise NotImplementedError()

    # Helper functions for subclasses
    def get_region(self, where, context, require=True):
        sess = context.session
        dest = sess.query(Region).filter_by(name=where).first()
        if not dest:
            dest = sess.query(Region).filter_by(
                srname=where).first()
        if require and not dest:
            context.comment.reply(
                "I don't know any region or subreddit named '%s'" %
                self.where)
        return dest


class InvadeCommand(Command):
    def __init__(self, tokens):
        self.where = tokens["where"].lower()

    def execute(self, context):
        dest = self.get_region(self.where, context)
        if dest:
            now = time.mktime(time.localtime())
            begins = now + context.config["game"]["battle_delay"]
            battle = None
            try:
                battle = dest.invade(context.player, begins)
            except db.RankException:
                context.reply("You don't have the authority "
                              "to invade a region!")
            except db.TeamException:
                context.reply("You can't invade %s, you already own it!" %
                              dest.markdown())
            except db.NonAdjacentException:
                context.reply("%s is not next to any territory you control" %
                              dest.markdown())
            except db.InProgressException:
                context.reply("%s is already being invaded!" % dest.markdown())

            if battle:
                context.reply("**Confirmed**  Battle will begin at %s" %
                              battle.begins_str())
                title = ("[Invasion] The %s armies march!" %
                         num_to_team(context.player.team))
                text = ("Negotiations have broken down, and the trumpets of "
                        "war have sounded.  Even now, civilians are being "
                        "evacuated and the able-bodied drafted.  The conflict "
                        "will soon be upon you.\n\n"
                        "Gather your forces while you can, for your enemy "
                        "shall arrive at %s") % battle.begins_str()
                context.reddit.submit(dest.srname,
                                      title=title,
                                      text=text)


class MoveCommand(Command):
    def __init__(self, tokens):
        self.amount = int(tokens["amount"])
        self.where = tokens["where"].lower()

    def execute(self, context):
        dest = self.get_region(self.where, context.session)
        if dest:
            order = None
            try:
                speed = context.config["game"]["speed"]
                hundred_followers = self.amount / 100
                time_taken = speed * hundred_followers

                order = context.player.move(self.amount, dest, time_taken)
            except db.InsufficientException as ie:
                context.comment.reply(
                    "You cannot move %d of your people - you only have %d" %
                    (ie.requested, ie.available))
                return
            except db.NonAdjacentException:
                context.comment.reply(
                    "Your current region, %s, is not adjacent to %s" %
                    (context.player.region.markdown(), dest.markdown()))
                return
            except db.InProgressException as ipe:
                context.comment.reply((
                    "You are already leading your armies to %s - "
                    "you can give further orders upon your arrival at %s"
                    ) % (ipe.order.dest.markdown(), ipe.order.arrival_str()))
                return
            if order:
                context.comment.reply((
                    "**Confirmed**: You are leading %d of your people to %s. "
                    "You will arrive at %s."
                    ) % (self.amount, dest.markdown(), order.arrival_str()))
            else:
                context.comment.reply((
                    "**Confirmed**: You have lead %d of your people to %s."
                    ) % (self.amount, dest.markdown()))

    def __repr__(self):
        return "<MoveCommand(amount='%s', where='%s')>" % (
            self.amount, self.where)


class StatusCommand(Command):

    def execute(self, context):
        status = self.status_for(context)
        context.comment.reply(status)

    def status_for(self, context):
        found = context.player

        moving = context.player.is_moving()
        if moving:
            forces = ("Your forces are currently on the march to %s "
                      "and will arrive at %s")
            forces = forces % (moving.dest.markdown(), moving.arrival_str())
        else:
            forces = ("You are currently encamped at %s" %
                      found.region.markdown())

        result = ("You are a %s in the %s army.\n\n"
                  "Your forces number %d loyalists strong.\n\n"
                  "%s")
        return result % (found.rank, num_to_team(found.team), found.loyalists,
                         forces)
