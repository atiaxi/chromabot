import logging
import random
import time
import unittest
from collections import defaultdict

from chromabot import db
from chromabot.commands import Context, MoveCommand
from chromabot.db import (DB, Battle, Region, MarchingOrder, User)
from chromabot.utils import now


TEST_LANDS = """
[
    {
        "name": "Periopolis",
        "srname": "ct_periopolis",
        "connections": ["Sapphire"],
        "capital": 1
    },
    {
        "name": "Sapphire",
        "srname": "ct_sapphire",
        "connections": ["Orange Londo"]
    },
    {
        "name": "Orange Londo",
        "srname": "ct_orangelondo",
        "aliases": ["ct_orangelondo"],
        "connections": ["Oraistedarg"],
        "owner": 0
    },
    {
        "name": "Oraistedarg",
        "srname": "ct_oraistedarg",
        "connections": [],
        "capital": 0
    }
]
"""


class MockConf(object):

    def __init__(self, dbstring=None):
        self._dbstring = dbstring
        self.confitems = defaultdict(dict)

    @property
    def dbstring(self):
        return self._dbstring

    @property
    def game(self):
        return self['games']

    def __getitem__(self, key):
        return self.confitems[key]

    def __setitem__(self, key, value):
        self.confitems[key] = value


class MockContext(Context):

    def __init__(self, player, config, session, comment):
        Context.__init__(self, player, config, session, comment, None)

    def reply(self, reply, pm=True):
        pass


class ChromaTest(unittest.TestCase):

    def setUp(self):
        logging.basicConfig(level=logging.DEBUG)
        self.conf = MockConf(dbstring="sqlite://")
        self.db = DB(self.conf)
        self.db.create_all()
        self.sess = self.db.session()
        Region.create_from_json(self.sess, TEST_LANDS)

        # Create some users
        self.alice = self.create_user("alice", 0)
        self.bob = self.create_user("bob", 1)

    def create_user(self, name, team):
        newbie = User(name=name, team=team, loyalists=100, leader=True)
        self.sess.add(newbie)
        cap = Region.capital_for(team, self.sess)
        newbie.region = cap
        self.sess.commit()
        return newbie

    def context(self, player=None, comment=None, config=None):
        if not player:
            player = self.alice
        if not config:
            config = self.conf
        return MockContext(player, config, self.sess, comment)

    def get_region(self, name, as_who=None):
        if not as_who:
            as_who = self.alice

        return Region.get_region(name, self.context(player=as_who))


class TestPatch(ChromaTest):
    def test_patch_add(self):
        """Should be able to patch in a new region"""
        NEW_LANDS = """
[
    {
        "name": "Periopolis",
        "srname": "ct_periopolis",
            "connections": ["Sapphire"],
        "capital": 1
    },
    {
        "name": "Sapphire",
        "srname": "ct_sapphire",
        "connections": ["Orange Londo"]
    },
    {
        "name": "Orange Londo",
        "srname": "ct_orangelondo",
        "connections": ["Oraistedarg", "flooland"],
        "owner": 0
    },
    {
        "name": "Oraistedarg",
        "srname": "ct_oraistedarg",
        "connections": [],
        "capital": 0
    },
    {
        "name": "flooland",
        "srname": "ct_flooland",
        "connections": []
    }
]
"""
        self.assert_(self.get_region("sapphire"))

        # doesn't already exist
        region = self.get_region('flooland')
        self.assertFalse(region)

        londo = self.get_region("Orange Londo")
        self.assertEqual(len(londo.borders), 2)  # ora and sapph

        Region.patch_from_json(self.sess, NEW_LANDS)

        # Should exist now
        region = self.get_region('flooland')
        self.assert_(region)
        self.assertEqual(len(region.borders), 1)

        # Should connect to londo
        self.assertEqual(region.borders[0], londo)
        self.assertEqual(len(londo.borders), 3)

        # Now there are 5 regions
        regnum = self.sess.query(Region).count()
        self.assertEqual(regnum, 5)

        # Meanwhile, periopolis is unchanged
        peri = self.get_region('Periopolis')
        self.assertEqual(len(peri.borders), 1)

    def test_patch_alias(self):
        """Should be able to patch in a new alias"""
        NEW_LANDS = """
[
    {
        "name": "Periopolis",
        "aliases": ["periperi"],
        "connections": []
    }
]
"""
        peri = self.sess.query(Region).filter_by(name="periopolis").first()
        self.assertIsNotNone(peri)
        periperi = self.get_region("periperi")
        self.assertIsNone(periperi)

        Region.patch_from_json(self.sess, NEW_LANDS)
        periperi = self.get_region("periperi")
        self.assertIsNotNone(periperi)

        self.assertEqual(peri, periperi)


class TestRegions(ChromaTest):

    def test_region_autocapital(self):
        """A region that's a capital is automatically owned by the same team"""
        cap = Region.capital_for(0, self.sess)
        self.assertEqual(cap.capital, cap.owner)

        cap = Region.capital_for(1, self.sess)
        self.assertEqual(cap.capital, cap.owner)

    def test_alias(self):
        """Move Alice to a globally funny-named region"""
        londo = self.get_region("Orange Londo")
        self.assertIsNotNone(londo)
        ol = self.get_region("OL")
        self.assertIsNone(ol)

        a = londo.create_alias("OL")
        self.assertIsNotNone(a)

        ol = self.get_region("OL")
        self.assertEqual(londo, ol)

    def test_unique_alias(self):
        """Aliased regions should be unique"""
        londo = self.get_region("Orange Londo")
        self.assertIsNotNone(londo)
        ol = self.get_region("OL")
        self.assertIsNone(ol)

        a = londo.create_alias("OL")
        self.assertIsNotNone(a)

        b = londo.create_alias("ol")
        self.assertIsNotNone(b)

        self.assertEqual(a, b)


class TestPlaying(ChromaTest):

    def test_defect(self):
        """For periwinkle!"""
        old_team = self.alice.team
        old_cap = self.alice.region
        self.alice.defect(1)

        self.assertEqual(self.alice.team, 1)
        self.assertNotEqual(self.alice.team, old_team)
        self.assertNotEqual(self.alice.region, old_cap)

    def test_ineffective_defect(self):
        """For... orangered?"""
        old_team = self.alice.team
        with self.assertRaises(db.TeamException):
            self.alice.defect(0)

        self.assertEqual(self.alice.team, old_team)

    def test_too_late_defect(self):
        """Can't defect once you've done something"""
        old_team = self.alice.team
        londo = self.get_region("Orange Londo")

        self.alice.move(100, londo, 0)
        with self.assertRaises(db.TimingException):
            self.alice.defect(1)

        self.assertEqual(self.alice.team, old_team)

    def test_unlimited_defect(self):
        """For periwinkle, then orangered, then periwinkle!"""
        self.conf["game"]["unlimited_defect"] = True
        old_team = self.alice.team
        old_cap = self.alice.region

        self.alice.defect(1, self.conf)

        self.assertEqual(self.alice.team, 1)
        self.assertNotEqual(self.alice.team, old_team)
        self.assertNotEqual(self.alice.region, old_cap)

        self.alice.defect(0, self.conf)
        self.assertEqual(self.alice.team, 0)
        self.assertEqual(self.alice.team, old_team)
        self.assertEqual(self.alice.region, old_cap)

        # Even after we do stuff!
        londo = self.get_region("Orange Londo")
        self.alice.move(100, londo, 0)

        self.alice.defect(1, self.conf)
        self.assertEqual(self.alice.team, 1)
        self.assertNotEqual(self.alice.team, old_team)
        self.assertNotEqual(self.alice.region, old_cap)

    def test_disabled_defect(self):
        """Can't defect if we disabled defecting"""
        self.conf["game"]["disable_defect"] = True

        old_team = self.alice.team

        with self.assertRaises(db.DisabledException):
            self.alice.defect(1, self.conf)

        self.assertEqual(self.alice.team, old_team)

    def test_movement(self):
        """Move Alice from the Orangered capital to an adjacent region"""
        sess = self.sess
        cap = Region.capital_for(0, sess)
        # First of all, make sure alice is actually there
        self.assertEqual(self.alice.region.id, cap.id)

        londo = self.get_region("Orange Londo")
        self.assertIsNotNone(londo)

        self.alice.move(100, londo, 0)

        # Now she should be there
        self.assertEqual(self.alice.region.id, londo.id)

    def test_movement_codeword(self):
        """Move Alice to a funny-named adjacent region"""
        londo = self.get_region("Orange Londo")
        self.assertIsNotNone(londo)
        blondo = self.get_region("Best Londo")
        self.assertIsNone(blondo)

        self.alice.add_codeword('Best Londo', 'Orange Londo')

        # Now it should be there!
        blondo = self.get_region("Best Londo")
        self.assertEqual(blondo, londo)

    def test_sector_movement(self):
        self.conf["game"]["num_sectors"] = 7
        sess = self.sess
        cap = Region.capital_for(0, sess)
        self.assertEqual(self.alice.region.id, cap.id)
        londo = self.get_region("Orange Londo")
        self.assertIsNotNone(londo)

        self.alice.move(100, londo, 0, sector=3, conf=self.conf)

    def test_default_sector_movement(self):
        self.conf["game"]["num_sectors"] = 7

        # Alice should be in sector 0 by default
        self.assertEqual(self.alice.sector, 0)

        sess = self.sess
        cap = Region.capital_for(0, sess)
        self.assertEqual(self.alice.region.id, cap.id)
        londo = self.get_region("Orange Londo")
        self.assertIsNotNone(londo)

        # This seed means that it'll pick 5.  I deliberately chose a seed that
        # would result in itself.
        random.seed(5)
        self.alice.move(100, londo, 0, conf=self.conf)

        self.assertEqual(self.alice.sector, 5)

    def test_intraregion_sector_movement(self):
        self.conf["game"]["num_sectors"] = 7
        home = self.alice.region
        # Put alice somewhere
        self.alice.sector = 1
        self.sess.commit()

        self.alice.move(100, home, 0, sector=3, conf=self.conf)

        self.assertEqual(self.alice.sector, 3)

    def test_out_of_bounds_sector_movement(self):
        self.conf["game"]["num_sectors"] = 7
        home = self.alice.region
        # Put alice somewhere
        self.alice.sector = 1
        self.sess.commit()

        with self.assertRaises(db.NoSuchSectorException):
            self.alice.move(100, home, 0, sector=9, conf=self.conf)

        self.assertEqual(self.alice.sector, 1)

    def test_delayed_intrasector_movement(self):
        DAY = 60 * 60 * 24
        self.conf["game"]["num_sectors"] = 7
        self.conf["game"]["intrasector_travel"] = DAY / 2
        home = self.alice.region

        movements = self.sess.query(MarchingOrder).count()
        self.assertEqual(movements, 0)

        DAY = 60 * 60 * 24
        then = now()  # We'll need this to check timing

        self.alice.move(100, home, DAY, sector=7, conf=self.conf)

        movements = self.sess.query(MarchingOrder).all()
        self.assertEqual(len(movements), 1)
        first = movements[0]
        self.assertEqual(first.source, self.get_region('Oraistedarg'))
        self.assertEqual(first.dest, self.get_region('Oraistedarg'))
        self.assertEqual(first.dest_sector, 7)
        # Note, if self.alice.move takes longer than 10 minutes to run, this
        # will fail.
        self.assertAlmostEqual(first.arrival, then + DAY / 2, delta=600)

        # Tired of waiting!
        first.arrival = now()
        self.sess.commit()
        self.assert_(first.has_arrived())
        arrived = MarchingOrder.update_all(self.sess)
        self.assert_(arrived)

        # Should still be home
        self.assertEqual(home, self.alice.region)

        # But in sector 7
        self.assertEqual(self.alice.sector, 7)

    def test_movement_multiplier_does_not_affect_intrasector(self):
        DAY = 60 * 60 * 24
        self.conf["game"]["num_sectors"] = 7
        self.conf["game"]["intrasector_travel"] = DAY / 2
        home = self.alice.region
        self.assertEqual(home, self.get_region('Oraistedarg'))
        home.travel_multiplier = 2
        self.sess.commit()

        movements = self.sess.query(MarchingOrder).count()
        self.assertEqual(movements, 0)

        then = now()  # We'll need this to check timing

        self.alice.move(100, home, DAY, sector=7, conf=self.conf)

        movements = self.sess.query(MarchingOrder).all()
        self.assertEqual(len(movements), 1)
        first = movements[0]
        self.assertEqual(first.source, home)
        self.assertEqual(first.dest, home)
        self.assertEqual(first.dest_sector, 7)

        # Unaffected by travel multiplier
        self.assertAlmostEqual(first.arrival, then + DAY / 2, delta=600)

        # Tired of waiting!
        first.arrival = now()
        self.sess.commit()
        self.assert_(first.has_arrived())
        arrived = MarchingOrder.update_all(self.sess)
        self.assert_(arrived)

        # Should still be home
        self.assertEqual(home, self.alice.region)

        # But in sector 7
        self.assertEqual(self.alice.sector, 7)


    def test_delayed_sector_movement(self):
        self.conf["game"]["num_sectors"] = 7
        londo = self.get_region("Orange Londo")

        movements = self.sess.query(MarchingOrder).count()
        self.assertEqual(movements, 0)

        DAY = 60 * 60 * 24
        then = now()  # We'll need this to check timing

        self.alice.move(100, londo, DAY, sector=2, conf=self.conf)

        movements = self.sess.query(MarchingOrder).all()
        self.assertEqual(len(movements), 1)
        first = movements[0]
        self.assertEqual(first.source, self.get_region('Oraistedarg'))
        self.assertEqual(first.dest, self.get_region('Orange Londo'))
        self.assertEqual(first.dest_sector, 2)
        # Note, if self.alice.move takes longer than 10 minutes to run, this
        # will fail.
        self.assertAlmostEqual(first.arrival, then + DAY, delta=600)

        # Tired of waiting!
        first.arrival = now()
        self.sess.commit()
        self.assert_(first.has_arrived())
        arrived = MarchingOrder.update_all(self.sess)
        self.assert_(arrived)

        # Should be in londo
        self.assertEqual(londo, self.alice.region)

        # And in sector 2
        self.assertEqual(self.alice.sector, 2)

    def test_srname(self):
        """Should be able to look up by srname"""
        londo = self.get_region("Orange Londo")
        self.assertIsNotNone(londo)

        ct = self.get_region("ct_orangelondo")
        self.assertIsNotNone(ct)
        self.assertEqual(londo, ct)

    def test_extract(self):
        """Emergency movement back to capital"""
        sess = self.sess
        cap = Region.capital_for(0, sess)
        # Move Alice somewhere else
        londo = self.get_region("Orange Londo")
        self.alice.move(100, londo, 0)

        # Should be in londo
        self.assertEqual(self.alice.region, londo)
        # Emergency move!
        self.alice.extract()

        # Should be back in capital
        self.assertEqual(self.alice.region, cap)

    def test_extract_cancels_movement(self):
        """Emergency movement shouldn't rubberband"""
        sess = self.sess
        cap = Region.capital_for(0, sess)
        # Move Alice somewhere else
        londo = self.get_region("Orange Londo")
        self.alice.move(100, londo, 0)

        # Should be in londo
        self.assertEqual(self.alice.region, londo)

        # Bloodless coup of Sapphire
        sapp = self.get_region("Sapphire")
        sapp.owner = self.alice.team
        sess.commit()

        # Start wandering that way
        order = self.alice.move(100, sapp, 60 * 60 * 24)
        self.assert_(order)

        orders = self.sess.query(MarchingOrder).count()
        self.assertEqual(orders, 1)

        self.alice.extract()
        self.assertEqual(self.alice.region, cap)

        orders = self.sess.query(MarchingOrder).count()
        self.assertEqual(orders, 0)

        # Make sure she ended up in a sector
        self.assertTrue(self.alice.sector)

    def test_stop_cancels_movement(self):
        """Stopping movement should actually, you know, stop movement"""

        sess = self.sess
        cap = Region.capital_for(0, sess)
        # Move Alice somewhere else
        londo = self.get_region("Orange Londo")
        self.alice.move(100, londo, 0)

        # Should be in londo
        self.assertEqual(self.alice.region, londo)

        # Bloodless coup of Sapphire
        sapp = self.get_region("Sapphire")
        sapp.owner = self.alice.team
        sess.commit()

        # Start wandering that way
        order = self.alice.move(100, sapp, 60 * 60 * 24)
        self.assert_(order)

        orders = self.sess.query(MarchingOrder).count()
        self.assertEqual(orders, 1)

        self.alice.cancel_movement()
        self.assertEqual(self.alice.region, londo)

        orders = self.sess.query(MarchingOrder).count()
        self.assertEqual(orders, 0)

    def test_disallow_unscheduled_invasion(self):
        """Can't move somewhere you don't own or aren't invading"""
        londo = self.get_region("Orange Londo")
        # For testing purposes, londo is now neutral
        londo.owner = None

        with self.assertRaises(db.TeamException):
            self.alice.move(100, londo, 0)

        n = (self.sess.query(db.MarchingOrder).
            filter_by(leader=self.alice)).count()
        self.assertEqual(n, 0)

    def test_allow_scheduled_invasion(self):
        """Can move somewhere that's not yours if you are invading"""
        londo = self.get_region("Orange Londo")
        # For testing purposes, londo is now neutral
        londo.owner = None

        battle = Battle(region=londo)
        self.sess.add(battle)
        self.sess.commit()

        self.alice.move(100, londo, 0)

        self.assertEqual(self.alice.region, londo)

    def test_allow_neutral_traversal(self):
        """Optionally, you can move through neutral territories"""
        # See test_disallow_unscheduled_invasion for the inverse of this
        londo = self.get_region("Orange Londo")
        # For testing purposes, londo is now neutral
        londo.owner = None

        self.conf["game"]["traversable_neutrals"] = True

        self.alice.move(100, londo, 0, conf=self.conf)

        self.assertEqual(self.alice.region, londo)

    def test_situation_changes(self):
        """Can't move somewhere that changes hands while you're moving"""
        started = self.alice.region
        londo = self.get_region("Orange Londo")
        # For testing purposes, londo is now alice's
        londo.owner = self.alice.team

        order = self.alice.move(100, londo, 60 * 60 * 24)[0]
        n = self.sess.query(db.MarchingOrder).count()
        self.assertEqual(n, 1)

        # BUT WAIT!  Londo's government is overthrown!
        londo.owner = self.bob.team

        # Push back arrival time
        order.arrival = now()
        self.sess.commit()

        # Invoke the update routine to set everyone's location
        arrived = MarchingOrder.update_all(self.sess)
        self.assert_(arrived)

        # Alice should be back where she started, as she can't be in londo
        self.assertEqual(started, self.alice.region)

        n = self.sess.query(db.MarchingOrder).count()
        self.assertEqual(n, 0)

    def test_situation_changes_neutral(self):
        """Can't move somewhere that becomes neutral while you're moving"""
        started = self.alice.region
        londo = self.get_region("Orange Londo")
        # For testing purposes, londo is now alice's
        londo.owner = self.alice.team

        order = self.alice.move(100, londo, 60 * 60 * 24)[0]
        n = self.sess.query(db.MarchingOrder).count()
        self.assertEqual(n, 1)

        # What makes a man turn neutral?
        londo.owner = None

        # Push back arrival time
        order.arrival = now()
        self.sess.commit()

        # Invoke the update routine to set everyone's location
        arrived = MarchingOrder.update_all(self.sess)
        self.assert_(arrived)

        # Alice should be back where she started, as she can't be in londo
        self.assertEqual(started, self.alice.region)

        n = self.sess.query(db.MarchingOrder).count()
        self.assertEqual(n, 0)

    def test_situation_changes_neutral_ok(self):
        """Can end up somewhere neutral if we allow it"""
        self.conf["game"]["traversable_neutrals"] = True
        started = self.alice.region
        londo = self.get_region("Orange Londo")
        # For testing purposes, londo is now alice's
        londo.owner = self.alice.team

        order = self.alice.move(100, londo, 60 * 60 * 24, conf=self.conf)[0]
        n = self.sess.query(db.MarchingOrder).count()
        self.assertEqual(n, 1)

        # What makes a man turn neutral?
        londo.owner = None

        # Push back arrival time
        order.arrival = now()
        self.sess.commit()

        # Invoke the update routine to set everyone's location
        arrived = MarchingOrder.update_all(self.sess, conf=self.conf)
        self.assert_(arrived)

        # Now we're there!
        self.assertEqual(londo, self.alice.region)

        # Shouldn't be any marching orders left
        orders = self.sess.query(MarchingOrder).count()
        self.assertEqual(orders, 0)

    def test_got_moved(self):
        """Make sure you can't finish moving if you're warped"""
        started = self.alice.region
        londo = self.get_region("Orange Londo")
        # For testing purposes, londo is now alice's
        londo.owner = self.alice.team

        # But she's at the fight
        self.alice.region = self.get_region('sapphire')

        order = self.alice.move(100, londo, 60 * 60 * 24)[0]
        n = self.sess.query(db.MarchingOrder).count()
        self.assertEqual(n, 1)

        # The sapphire battle ends poorly for alice's team, and she gets
        # booted out
        self.alice.region = self.get_region('oraistedarg')

        # Invoke the update routine to set everyone's location
        order.arrival = now()
        arrived = MarchingOrder.update_all(self.sess)
        self.assert_(arrived)

        # Alice should be back where she started, as the move isn't valid
        self.assertEqual(started, self.alice.region)

        n = self.sess.query(db.MarchingOrder).count()
        self.assertEqual(n, 0)

    def test_disallow_overdraw_movement(self):
        """Make sure you can't move more people than you have"""
        londo = self.get_region("Orange Londo")
        old = self.alice.region

        with self.assertRaises(db.InsufficientException):
            self.alice.move(10000, londo, 0)

        # She should still be in the capital
        self.assertEqual(self.alice.region.id, old.id)

        n = (self.sess.query(db.MarchingOrder).
            filter_by(leader=self.alice)).count()
        self.assertEqual(n, 0)

    def test_disallow_nonadjacent_movement(self):
        """Make sure you can't move to somewhere that's not next to you"""
        old = self.alice.region
        pericap = self.get_region("Periopolis")

        with self.assertRaises(db.NonAdjacentException):
            # Strike instantly at the heart of the enemy!
            self.alice.move(100, pericap, 0)

        # Actually, no, nevermind, let's stay here
        self.assertEqual(self.alice.region.id, old.id)
        n = (self.sess.query(db.MarchingOrder).
            filter_by(leader=self.alice)).count()
        self.assertEqual(n, 0)

    def test_delayed_movement(self):
        """Most movement should take a while"""
        home = self.alice.region
        londo = self.get_region("Orange Londo")

        # Everything's fine
        self.assertFalse(self.alice.is_moving())

        # Ideally, this test will not take a day to complete
        order = self.alice.move(100, londo, 60 * 60 * 24)[0]
        self.assert_(order)

        # Alice should be moving
        self.assert_(self.alice.is_moving())

        # For record-keeping purposes, she's in her source city
        self.assertEqual(home, self.alice.region)

        # Well, we don't want to wait an entire day, so let's cheat and push
        # back the arrival time
        order.arrival = time.mktime(time.localtime())
        self.sess.commit()
        self.assert_(order.has_arrived())

        # But we're not actually there yet
        self.assertEqual(home, self.alice.region)

        # Invoke the update routine to set everyone's location
        arrived = MarchingOrder.update_all(self.sess)
        self.assert_(arrived)

        # Now we're there!
        self.assertEqual(londo, self.alice.region)

        # Shouldn't be any marching orders left
        orders = self.sess.query(MarchingOrder).count()
        self.assertEqual(orders, 0)

    def test_no_move_while_moving(self):
        """Can only move if you're not already going somewhere"""
        londo = self.get_region("Orange Londo")
        order = self.alice.move(100, londo, 60 * 60 * 24)[0]
        self.assert_(order)

        with self.assertRaises(db.InProgressException):
            # Sending to londo because Alice is technically still in the
            # capital, otherwise we'd get a NotAdjacentException
            self.alice.move(100, londo, 0)
        n = (self.sess.query(db.MarchingOrder).
            filter_by(leader=self.alice)).count()
        self.assertEqual(n, 1)

    def test_disallow_invadeception(self):
        """Can't invade if you're already invading!"""
        londo = self.get_region("Orange Londo")
        # For testing purposes, londo is now neutral
        londo.owner = None

        now = time.mktime(time.localtime())
        when = now + 60 * 60 * 24
        battle = londo.invade(self.alice, when)

        self.assert_(battle)

        with self.assertRaises(db.InProgressException):
            londo.invade(self.alice, when)

        n = (self.sess.query(db.Battle).count())
        self.assertEqual(n, 1)

    def test_disallow_fortified_invasion(self):
        """Can't invade a region with the 'fortified' buff"""
        londo = self.get_region("Orange Londo")
        londo.owner = None
        londo.buff_with(db.Buff.fortified())

        when = now() + 60 * 60 * 24

        with self.assertRaises(db.TimingException):
            londo.invade(self.alice, when)

        n = (self.sess.query(db.Battle).count())
        self.assertEqual(n, 0)

    def test_disallow_nonadjacent_invasion(self):
        """Invasion must come from somewhere you control"""
        pericap = self.get_region("Periopolis")

        with self.assertRaises(db.NonAdjacentException):
            pericap.invade(self.alice, 0)
        n = (self.sess.query(db.Battle).count())
        self.assertEqual(n, 0)

    def test_disallow_friendly_invasion(self):
        """Can't invade somewhere you already control"""
        londo = self.get_region("Orange Londo")

        with self.assertRaises(db.TeamException):
            londo.invade(self.alice, 0)
        n = (self.sess.query(db.Battle).count())
        self.assertEqual(n, 0)

    def test_disallow_peon_invasion(self):
        """Must have .leader set to invade"""
        londo = self.get_region("Orange Londo")
        londo.owner = None
        self.alice.leader = False

        with self.assertRaises(db.RankException):
            londo.invade(self.alice, 0)
        n = (self.sess.query(db.Battle).count())
        self.assertEqual(n, 0)

    def test_multimove(self):
        """Should be able to more more than one hop.
        (with corresponding increase in times)"""
        sapp = self.get_region("Sapphire")
        sapp.owner = self.alice.team
        self.sess.commit()

        DAY = 60 * 60 * 24

        movements = self.sess.query(MarchingOrder).count()
        self.assertEqual(movements, 0)

        path = [self.get_region(name) for name in ('Orange Londo', 'Sapphire')]
        then = now()  # We'll need this to check timing
        self.alice.move(100, path, DAY)

        movements = self.sess.query(MarchingOrder).all()
        self.assertEqual(len(movements), 2)
        # The first should be to londo
        londomove = movements[0]
        self.assertEqual(londomove.source, self.get_region('Oraistedarg'))
        self.assertEqual(londomove.dest, self.get_region('Orange Londo'))
        # Note, if self.alice.move takes longer than 10 minutes to run, this
        # will fail.
        self.assertAlmostEqual(londomove.arrival, then + DAY, delta=600)

        # Next, sapphire
        sappmove = movements[1]
        self.assertEqual(sappmove.source, self.get_region('Orange Londo'))
        self.assertEqual(sappmove.dest, self.get_region('Sapphire'))
        # Should arrive 2 days from now, +/- 5 minutes
        self.assertAlmostEqual(sappmove.arrival, then + DAY + DAY, delta=600)

        n = (self.sess.query(db.MarchingOrder).
            filter_by(leader=self.alice)).count()
        self.assertEqual(n, 2)

        # Tired of waiting
        movements[0].arrival = now()
        self.sess.commit()
        self.assert_(movements[0].has_arrived())
        arrived = MarchingOrder.update_all(self.sess)
        self.assert_(arrived)

        # Should be in londo
        self.assertEqual(londomove.dest, self.alice.region)

        # One order left
        n = (self.sess.query(db.MarchingOrder).
            filter_by(leader=self.alice)).count()
        self.assertEqual(n, 1)

        movements[1].arrival = now()
        self.sess.commit()
        self.assert_(movements[1].has_arrived())
        arrived = MarchingOrder.update_all(self.sess)
        self.assert_(arrived)

        # And now in sapphire
        self.assertEqual(sappmove.dest, self.alice.region)

        # Done moving
        n = (self.sess.query(db.MarchingOrder).
            filter_by(leader=self.alice)).count()
        self.assertEqual(n, 0)

    def test_multimove_noentry(self):
        """Can't use multimove to get into enemy territory"""
        sapp = self.get_region("Sapphire")
        sapp.owner = self.bob.team
        self.sess.commit()

        DAY = 60 * 60 * 24

        movements = self.sess.query(MarchingOrder).count()
        self.assertEqual(movements, 0)

        path = [self.get_region(name) for name in ('Orange Londo', 'Sapphire')]
        with self.assertRaises(db.TeamException):
            self.alice.move(100, path, DAY)

        n = (self.sess.query(db.MarchingOrder).
            filter_by(leader=self.alice)).count()
        self.assertEqual(n, 0)

    def test_multimove_situation_changes(self):
        """Can't multimove somewhere that's changed hands"""
        sapp = self.get_region("Sapphire")
        sapp.owner = self.alice.team
        self.sess.commit()

        DAY = 60 * 60 * 24

        movements = self.sess.query(MarchingOrder).count()
        self.assertEqual(movements, 0)

        path = [self.get_region(name) for name in ('Orange Londo', 'Sapphire')]
        then = now()  # We'll need this to check timing
        self.alice.move(100, path, DAY)

        movements = self.sess.query(MarchingOrder).all()
        self.assertEqual(len(movements), 2)
        # The first should be to londo
        londomove = movements[0]
        self.assertEqual(londomove.source, self.get_region('Oraistedarg'))
        self.assertEqual(londomove.dest, self.get_region('Orange Londo'))
        # Note, if self.alice.move takes longer than 10 minutes to run, this
        # will fail.
        self.assertAlmostEqual(londomove.arrival, then + DAY, delta=600)

        # Next, sapphire
        sappmove = movements[1]
        self.assertEqual(sappmove.source, self.get_region('Orange Londo'))
        self.assertEqual(sappmove.dest, self.get_region('Sapphire'))
        # Should arrive 2 days from now, +/- 5 minutes
        self.assertAlmostEqual(sappmove.arrival, then + DAY + DAY, delta=600)

        n = (self.sess.query(db.MarchingOrder).
            filter_by(leader=self.alice)).count()
        self.assertEqual(n, 2)

        # Sapphire falls to the enemy!
        sappmove.dest.owner = self.bob.team
        self.sess.commit()

        # Tired of waiting
        movements[0].arrival = now()
        self.sess.commit()
        self.assert_(movements[0].has_arrived())
        arrived = MarchingOrder.update_all(self.sess)
        self.assert_(arrived)

        # Should be in londo
        self.assertEqual(londomove.dest, self.alice.region)

        # One order left
        n = (self.sess.query(db.MarchingOrder).
            filter_by(leader=self.alice)).count()
        self.assertEqual(n, 1)

        movements[1].arrival = now()
        self.sess.commit()
        self.assert_(movements[1].has_arrived())
        arrived = MarchingOrder.update_all(self.sess)
        self.assert_(arrived)

        # But we fail to arrive because this movement's no longer valid.
        self.assertEqual(londomove.dest, self.alice.region)

        # Done moving
        n = (self.sess.query(db.MarchingOrder).
            filter_by(leader=self.alice)).count()
        self.assertEqual(n, 0)

    def test_movement_multiplier(self):
        """Some lands are harder to enter/leave"""
        home = self.alice.region
        londo = self.get_region("Orange Londo")
        londo.travel_multiplier = 2
        self.sess.commit()

        DAY = 60 * 60 * 24

        movements = self.sess.query(MarchingOrder).count()
        self.assertEqual(movements, 0)

        then = now()
        order = self.alice.move(100, londo, DAY)[0]
        self.assert_(order)

        # But because the travel multiplier's 2, that should take twice
        # as long
        self.assertAlmostEqual(order.arrival, then + DAY + DAY, delta=600)

        # Tired of waiting
        order.arrival = now()
        self.sess.commit()
        self.assert_(order.has_arrived())
        arrived = MarchingOrder.update_all(self.sess)
        self.assert_(arrived)

        # Should be in londo
        self.assertEqual(order.dest, londo)
        self.assertEqual(order.dest, self.alice.region)

        # We're bored and want to go home
        then = now()
        order = self.alice.move(100, home, DAY)[0]

        self.assert_(order)

        # But because the travel multiplier's 2, that should ALSO take twice
        # as long
        self.assertAlmostEqual(order.arrival, then + DAY + DAY, delta=600)

    def test_mutimove_multiplier(self):
        """Can move more than one hop through harder territory and it takes
        correspondingly longer"""
        sapp = self.get_region("Sapphire")
        sapp.owner = self.alice.team
        londo = self.get_region("Orange Londo")
        londo.travel_multiplier = 2
        self.sess.commit()

        DAY = 60 * 60 * 24

        movements = self.sess.query(MarchingOrder).count()
        self.assertEqual(movements, 0)

        path = [self.get_region(name) for name in ('Orange Londo', 'Sapphire')]
        then = now()  # We'll need this to check timing
        self.alice.move(100, path, DAY)

        movements = self.sess.query(MarchingOrder).all()
        self.assertEqual(len(movements), 2)
        # The first should be to londo
        londomove = movements[0]
        self.assertEqual(londomove.source, self.get_region('Oraistedarg'))
        self.assertEqual(londomove.dest, self.get_region('Orange Londo'))
        # Travel multiplier to londo is double
        self.assertAlmostEqual(londomove.arrival, then + DAY + DAY, delta=600)

        # Next, sapphire
        sappmove = movements[1]
        self.assertEqual(sappmove.source, self.get_region('Orange Londo'))
        self.assertEqual(sappmove.dest, self.get_region('Sapphire'))
        # Should arrive 4(!) days from now, thanks to freaking londo
        self.assertAlmostEqual(sappmove.arrival, then + (DAY * 4), delta=600)


class TestPathfinding(ChromaTest):

    def test_no_neutral_traversal(self):
        """Normally, can't walk over the neutrals"""
        londo = self.get_region("Orange Londo")
        # For testing purposes, londo is now neutral
        londo.owner = None

        path = MoveCommand.expand_path(["*", "Orange Londo"], self.context())
        self.assertIsNone(path)

    def test_allow_neutral_traversal(self):
        londo = self.get_region("Orange Londo")
        # For testing purposes, londo is now neutral
        londo.owner = None

        self.conf["game"]["traversable_neutrals"] = True

        path = MoveCommand.expand_path(["*", "Orange Londo"], self.context())
        self.assertIsNotNone(path)

if __name__ == '__main__':
    unittest.main()
