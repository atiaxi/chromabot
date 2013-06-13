import logging
import time

import db
from db import Battle, Region, SkirmishAction
from utils import num_to_team, name_to_id


class Context(object):
    def __init__(self, player, config, session, comment, reddit):
        self.player = player    # a DB object
        self.config = config
        self.session = session
        self.comment = comment  # a praw object
        self.reddit = reddit    # root praw object

    def reply(self, reply):
        return self.comment.reply(reply)


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
        if "amount" in tokens:
            self.amount = int(tokens["amount"])
        else:
            self.amount = -1
        self.where = tokens["where"].lower()

    def execute(self, context):
        dest = self.get_region(self.where, context)
        if dest:
            order = None

            if self.amount == -1:  # -1 means 'everyone'
                self.amount = context.player.loyalists

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
                # Determine if there's a move in progress or a battle
                if hasattr(ipe.other, 'arrival_str'):
                    context.comment.reply((
                        "You are already leading your armies to %s - "
                        "you can give further orders upon your arrival at %s"
                        ) % (ipe.other.dest.markdown(),
                             ipe.other.arrival_str()))
                else:
                    context.comment.reply((
                        "You have committed your armies to the battle at %s - "
                        "you must see this through to the bitter end."
                        ) % (ipe.other.get_battle().region.markdown()))
                return
            except db.TeamException:
                context.reply(("%s is not friendly territory - invade first "
                               "if you want to go there") % self.where)
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


class SkirmishCommand(Command):
    def __init__(self, tokens):
        self.action = tokens['action']
        if self.action == 'oppose':  # Clearer-sounding synonym for 'attack'
            self.action = 'attack'
        self.amount = int(tokens['amount'])

    def execute(self, context):
        # getattr wackiness because real comments not gotten from inbox don't
        # have "was_comment" set on them
        if not getattr(context.comment, 'was_comment', True):
            # PMing skirmish commands makes no sense
            context.reply("You must enter your skirmish commands in the "
                          "appropriate battle post")
            return

        post_id = context.comment.link_id  # Actually a 'name'
        ongoing = context.session.query(Battle).filter_by(
            submission_id=post_id)
        current = ongoing.first()
        if not current:
            context.reply("There's no battle happening here!")
            return

        try:
            if post_id == context.comment.parent_id:
                skirmish = current.create_skirmish(context.player, self.amount)
            else:
                parent = context.session.query(SkirmishAction).filter_by(
                    comment_id=context.comment.parent_id).first()
                if not parent:
                    context.reply("You can only use skirmish commands in "
                                  "reply to other confirmed skirmish commands")
                    return
                hinder = self.action == 'attack'
                skirmish = parent.react(context.player, self.amount,
                                        hinder=hinder)
            total = context.player.committed_loyalists
            context.reply(("**Confirmed**: You have committed %d of your "
                "forces to this battle.\n\n(As of now, you have "
                "committed %d total)") % (skirmish.amount, total))

            skirmish.comment_id = context.comment.name
            context.session.commit()
        except db.NotPresentException as npe:
            context.reply(("Your armies are currently in %s and thus cannot "
                           "participate in this battle.") %
                          npe.actually_am.markdown())
        except db.TeamException as te:
            if te.friendly:
                context.reply("You cannot attack someone on your team")
            else:
                context.reply("You cannot aid the enemy!")
        except db.InProgressException:
            context.reply("You can only spearhead one offensive per battle "
                          "(though you may still assist others)")
        except db.InsufficientException as ie:
            if ie.requested <= 0:
                context.reply("You must use at least 1 troop!")
            else:
                context.reply(("You don't have %d troops to spare! "
                               "(you have committed %d total)") %
                              (ie.requested,
                               context.player.committed_loyalists))
