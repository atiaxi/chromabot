import json
import logging
import time

from sqlalchemy import (
    create_engine, Boolean, Column, ForeignKey, Integer, String, Table)
from sqlalchemy.orm import backref, relationship, sessionmaker
from sqlalchemy.orm.session import Session
from sqlalchemy.ext.declarative import declarative_base

from utils import num_to_team


# Some helpful model exceptions

class InsufficientException(Exception):
    def __init__(self, requested, available, ofwhat):
        Exception.__init__(self,
                           "Insufficient %s - needed %d but only had %d" %
                           (ofwhat, requested, available))
        self.requested = requested
        self.available = available
        self.ofwhat = ofwhat


class NonAdjacentException(Exception):
    def __init__(self, src, dest):
        Exception.__init__(self,
                           "%s and %s are not adjacent!" % (src, dest))


class NotPresentException(Exception):
    def __init__(self, need_to_be, actually_am):
        self.need_to_be = need_to_be
        self.actually_am = actually_am
        Exception.__init__(self,
                           "To do this you need to be in %s, but are in %s" %
                           (need_to_be.name, actually_am.name))


class InProgressException(Exception):
    def __init__(self, other):
        self.other = other
        Exception.__init__(self, "You're already doing that!")


class TeamException(Exception):
    def __init__(self, what, friendly=False):
        self.friendly = friendly
        self.what = what
        if friendly:
            msg = "%s is friendly!" % what
        else:
            msg = "%s is not friendly!" % what
        Exception.__init__(self, msg)


class RankException(Exception):
    def __init__(self):
        Exception.__init__(self,
                           "You do not have the rank required to do that!")


# Models
class Model(object):

    def session(self):
        return Session.object_session(self)

    def timestr(self, secs=None):
        if secs is None:
            secs = time.mktime(time.localtime())
        return time.strftime("%Y-%m-%d %H:%M:%S GMT",
                              time.gmtime(secs))

Base = declarative_base(cls=Model)


class DB(object):
    def __init__(self, config):
        self.engine = create_engine(config.dbstring, echo=False)
        self.sessionfactory = sessionmaker(bind=self.engine)

    def create_all(self):
        Base.metadata.create_all(self.engine)

    def drop_all(self):
        Base.metadata.drop_all(self.engine)

    def session(self):
        return self.sessionfactory()


class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    name = Column(String(255))
    team = Column(Integer)
    loyalists = Column(Integer)
    committed_loyalists = Column(Integer, default=0)
    region_id = Column(Integer, ForeignKey('regions.id'))
    leader = Column(Boolean, default=False)

    def __repr__(self):
        return "<User(name='%s', team='%d', loyalists='%d')>" % (
            self.name, self.team, self.loyalists)

    @property
    def rank(self):
        if self.leader:
            return "general"
        else:
            return "captain"

    def is_moving(self):
        if self.movement:
            return self.movement[0]
        return None

    def move(self, how_many, where, delay):
        result = None
        sess = Session.object_session(self)

        already = sess.query(MarchingOrder).filter_by(leader=self).first()
        if already:
            raise InProgressException(already)

        fighting = (sess.query(SkirmishAction).
                    filter_by(participant=self).first())
        if fighting:
            raise InProgressException(fighting)

        if how_many > self.loyalists:
            # TODO: Attempt to pick up loyalists
            raise InsufficientException(how_many, self.loyalists, "loyalists")

        # TODO: Drop off loyalists
        if not where in self.region.borders:
            raise NonAdjacentException(self.region, where)

        if where.owner != self.team:
            if not where.battle:
                raise TeamException(where)

        if(delay > 0):
            result = MarchingOrder(arrival=time.mktime(time.localtime())
                                    + delay,
                                   leader=self,
                                   source=self.region,
                                   dest=where)
            sess.add(result)
        else:
            self.region = where
        # TODO: Change number of loyalists
        sess.commit()

        return result

region_to_region = Table("region_to_region", Base.metadata,
        Column("left_id", Integer, ForeignKey("regions.id"), primary_key=True),
        Column("right_id", Integer, ForeignKey("regions.id"),
               primary_key=True))


class MarchingOrder(Base):
    __tablename__ = "marching_orders"

    id = Column(Integer, primary_key=True)
    arrival = Column(Integer, default=0)

    leader_id = Column(Integer, ForeignKey('users.id'))
    leader = relationship("User", backref="movement")

    # Relationships for these defined in the Region class
    source_id = Column(Integer, ForeignKey("regions.id"))
    dest_id = Column(Integer, ForeignKey("regions.id"))

    @classmethod
    def update_all(cls, sess):
        orders = sess.query(cls).all()
        result = []
        for order in orders:
            if order.update():
                result.append(order)
        return result

    def has_arrived(self):
        now = time.mktime(time.localtime())
        return self.arrival <= now

    def arrival_str(self):
        return self.timestr(self.arrival)

    def update(self):
        sess = Session.object_session(self)
        if self.has_arrived():
            self.leader.region = self.dest
            sess.delete(self)
            sess.commit()
            return True
        return False


class Region(Base):
    __tablename__ = "regions"

    id = Column(Integer, primary_key=True)
    name = Column(String(255))
    srname = Column(String(255))
    capital = Column(Integer)
    owner = Column(Integer)

    people = relationship("User", backref="region")

    borders = relationship("Region", secondary=region_to_region,
        primaryjoin=id == region_to_region.c.left_id,
        secondaryjoin=id == region_to_region.c.right_id,
        cascade="all, delete",
        backref="other_borders")

    outbound_armies = relationship("MarchingOrder",
                                   foreign_keys=MarchingOrder.source_id,
                                   backref="source")

    inbound_armies = relationship("MarchingOrder",
                                  foreign_keys=MarchingOrder.dest_id,
                                  backref="dest")

    @classmethod
    def capital_for(cls, team, session):
        return session.query(cls).filter_by(capital=team).first()

    @classmethod
    def create_from_json(cls, json_str=None, json_file=None):
        if json_file is not None:
            with open(json_file) as srcfile:
                unconverted = json.load(srcfile)
        else:
            unconverted = json.loads(json_str)

        atlas = {}
        result = []
        for region in unconverted:
            capital = None
            owner = None
            if 'capital' in region:
                capital = region['capital']
                owner = capital
            if 'owner' in region:
                owner = region['owner']
            created = cls(name=region['name'].lower(),
                          srname=region['srname'].lower(),
                          capital=capital,
                          owner=owner)
            result.append(created)
            atlas[created.name] = created

        # Hook up the regions
        for region in unconverted:
            created = atlas[region['name'].lower()]
            for adjacent in region['connections']:
                created.add_border(atlas[adjacent.lower()])
        return result

    def add_border(self, other_region):
        """Adds the other region to this region's borders, and then does the
        same for the other region, to keep bidirectionality intact"""
        # So tired of trying to figure out how to tell sqlalchemy to do it,
        # just going to do it manually
        self.borders.append(other_region)
        other_region.borders.append(self)

    def invade(self, by_who, when):
        if not by_who.leader:
            raise RankException()

        if self.owner == by_who.team:
            raise TeamException(self, friendly=True)

        if self.battle:
            raise InProgressException(self.battle)

        # Make sure that the given team owns at least one region adjacent
        # to this one
        bad_neighbors = [region for region in self.borders
                         if region.owner is not None
                            and region.owner == by_who.team]
        if not bad_neighbors:
            raise NonAdjacentException(self, "your territory")

        sess = Session.object_session(self)
        battle = Battle(
            region=self,
            begins=when
            )
        sess.add(battle)
        sess.commit()
        return battle

    def markdown(self):
        return "[%s](/r/%s)" % (self.name, self.srname)

    def __repr__(self):
        return "<Region(id='%s', name='%s')>" % (self.id, self.name)


class Battle(Base):
    __tablename__ = "battles"

    id = Column(Integer, primary_key=True)
    begins = Column(Integer, default=0)
    ends = Column(Integer, default=0)
    submission_id = Column(String)

    victor = Column(Integer)
    score0 = Column(Integer)
    score1 = Column(Integer)

    region_id = Column(Integer, ForeignKey('regions.id'))
    region = relationship("Region", uselist=False, backref="battle")

    @classmethod
    def update_all(cls, sess):
        battles = sess.query(cls).all()
        begin = []
        ended = []
        for battle in battles:
            if not battle.has_started() and battle.is_ready():
                begin.append(battle)
            elif battle.has_started() and battle.past_end_time():
                battle.resolve()
                ended.append(battle)

        result = {
            "begin": begin,
            "ended": ended
        }
        return result

    def begins_str(self):
        return self.timestr(self.begins)

    def ends_str(self):
        return self.timestr(self.ends)

    def create_skirmish(self, who, howmany, troop_type='infantry'):
        sess = self.session()
        sa = SkirmishAction.create(sess, who, howmany, battle=self,
                                   troop_type=troop_type)
        sess.commit()
        return sa

    def has_started(self):
        """
        A battle has started if its time has come, and there's a thread
        to do battle in.
        """
        if self.is_ready():
            return self.submission_id
        return False

    def is_ready(self):
        now = time.mktime(time.localtime())
        return now >= self.begins

    def participants(self):
        return {skirmish.participant for skirmish in self.skirmishes}

    def past_end_time(self):
        now = time.mktime(time.localtime())
        return now >= self.ends

    def resolve(self):
        score = [0, 0]
        for skirmish in self.skirmishes:
            skirmish.resolve()
            if skirmish.victor is not None:
                score[skirmish.victor] += skirmish.vp
        self.score0, self.score1 = score

        if self.score0 > self.score1:
            self.victor = 0
        elif self.score1 > self.score0:
            self.victor = 1
        else:
            self.victor = None

        # The new owner of wherever this battle happened is the victor
        if self.victor:
            self.region.owner = self.victor

        # Un-commit all the loyalists for this fight, kick out the losers
        losercap = None
        for person in self.region.people:
            person.committed_loyalists = 0
            if person.team != self.victor:
                if not losercap:
                    losercap = Region.capital_for(person.team,
                                                  self.session())
                person.region = losercap

        self.session().commit()


class Processed(Base):
    __tablename__ = "processed"

    id = Column(Integer, primary_key=True)
    id36 = Column(String)

    battle_id = Column(Integer, ForeignKey('battles.id'))
    battle = relationship("Battle",
                          backref=backref("processed_comments",
                                          cascade="all, delete"))


class SkirmishAction(Base):
    __tablename__ = "skirmish_actions"

    id = Column(Integer, primary_key=True)
    comment_id = Column(String)
    amount = Column(Integer, default=0)
    hinder = Column(Boolean, default=True)
    troop_type = Column(String, default='infantry')

    victor = Column(Integer)
    vp = Column(Integer)
    margin = Column(Integer)
    unopposed = Column(Boolean, default=False)

    battle_id = Column(Integer, ForeignKey('battles.id'))
    battle = relationship("Battle",
                          backref=backref("skirmishes",
                                          cascade="all, delete"))

    participant_id = Column(Integer, ForeignKey('users.id'))
    participant = relationship("User", backref="skirmishes")

    parent_id = Column(Integer, ForeignKey('skirmish_actions.id'))
    children = relationship("SkirmishAction",
        backref=backref('parent', remote_side=[id],
                        cascade="all, delete"))

    @classmethod
    def create(cls, sess, who, howmany, hinder=True, parent=None, battle=None,
               troop_type='infantry'):
        sa = SkirmishAction(participant=who,
                            amount=howmany,
                            hinder=hinder,
                            parent=parent,
                            battle=battle,
                            troop_type=troop_type)
        sa.commit_if_valid()

        return sa

    def adjusted_for_type(self, other_type, amount):
        """Certain types will be more effective vs. this skirmish"""
        ordering = ["ranged", "infantry", "cavalry"]
        our_index = ordering.index(self.troop_type)
        penalty = ordering[our_index - 1]
        bonus = ordering[(our_index + 1) % len(ordering)]
        result = amount
        if other_type == penalty:
            result = int(amount / 2)
        elif other_type == bonus:
            result = int(amount * 1.5)
        return result

    def get_battle(self):
        """
        Returns the battle that this skirmish belongs to - if this is a
        child skirmish, will go up the chain to the root
        """
        if self.parent:
            return self.get_root().get_battle()
        else:
            return self.battle

    def get_root(self):
        """
        Returns the root of this skirmish, which may be itself
        """
        if self.parent:
            return self.parent.get_root()
        else:
            return self

    def react(self, who, howmany, hinder=True, troop_type='infantry'):
        sess = self.session()
        sa = SkirmishAction.create(sess, who, howmany, hinder, parent=self,
                                   troop_type=troop_type, battle=self.battle)

        return sa

    def resolve(self):
        # Make a results representing us
        self.victor = self.participant.team
        self.vp = 0
        self.margin = self.amount
        self.unopposed = True

        # Resolve our children, if any
        if self.children:
            supporters = [child.resolve() for child in self.children
                          if child.hinder == False]
            support = self.amount
            raw_support = support
            attack = 0
            raw_attack = attack
            for supporter in supporters:
                self.vp += supporter.vp
                if supporter.victor == self.participant.team:
                    # Support only counts if it didn't get ambushed on the way
                    support += supporter.margin
                # If the attackers overtook this support, we do nothing;
                # attacks don't carry beyond their immediate target

            attackers = [child.resolve() for child in self.children
                         if child.hinder == True]
            for attacker in attackers:
                self.vp += attacker.vp
                if attacker.victor != self.participant.team:
                    # Attackers only count if they weren't beaten by our team
                    amount = attacker.margin
                    raw_attack += amount
                    attack += self.adjusted_for_type(attacker.troop_type,
                                                     amount)

            self.unopposed = attack == 0

            if(attack > support):
                # This skirmish loses!
                self.margin = attack - support
                self.victor = [1, 0][self.participant.team]
                self.vp += support
            elif(support > attack):
                # This skirmish wins!
                self.margin = support - attack
                self.victor = self.participant.team
                self.vp += raw_attack
            else:
                # Nobody is the winner, but this skirmish is sure the loser
                self.victor = None
                self.margin = 0
                self.vp += max(raw_attack, support)
        # Unopposed root nodes are worth 2x VP
        if not self.parent and self.unopposed:
            self.vp = max(self.vp * 2, self.amount * 2)

        self.session().commit()
        return self

    def report(self):
        preamble = "*  Skirmish #%d - the victor is " % self.id
        if self.victor is None:
            vstr = None
            postamble = ""
        else:
            vstr = num_to_team(self.victor)
            postamble = " by %d for **%d VP**" % (self.margin, self.vp)
        result = (("%s **%s** %s") %
                  (preamble, vstr, postamble))
        return result

    def commit_if_valid(self):
        self.validate()

        sess = self.session()
        sess.add(self)
        sess.commit()

        self.participant.committed_loyalists += self.amount

    def validate(self):
        """Raise exceptions if this is not a valid skirmish"""
        sess = self.session()

        # Are we actually there?
        need_to_be = self.get_battle().region
        actually_am = self.participant.region
        if need_to_be != actually_am:
            sess.rollback()
            raise NotPresentException(need_to_be, actually_am)

        if self.parent:
            sameteam = self.parent.participant.team == self.participant.team
            if self.hinder == sameteam:
                sess.rollback()
                raise TeamException(self, friendly=sameteam)
        else:
            # Make sure our participant doesn't have another toplevel
            s = (sess.query(SkirmishAction).
                 filter_by(parent_id=None).
                 filter_by(participant=self.participant)).count()
            # This is '1' and not '0' because for some damn reason that query
            # will count the newly created one
            if s > 1:
                sess.rollback()
                raise InProgressException(s)

        requested = self.amount + self.participant.committed_loyalists
        available = self.participant.loyalists
        if requested > available:
            sess.rollback()
            raise InsufficientException(self.amount, available, "loyalists")

        if self.amount <= 0:
            sess.rollback()
            raise InsufficientException(self.amount, 1, "argument")

        return self

    def __repr__(self):
        if self.battle:
            pstr = str(self.battle)
        else:
            pstr = str(self.parent)

        result = ("<SkirmishAction(participant=%s, amount=%s, "
                  "hinder=%s parent=%s)>") % (self.participant.name,
                                              self.amount,
                                              self.hinder,
                                              pstr)
        return result

