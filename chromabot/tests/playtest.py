import logging
import time
import unittest

import db
from db import (DB, Battle, Region, MarchingOrder, User)


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

    def __init__(self, dbstring):
        self._dbstring = dbstring

    @property
    def dbstring(self):
        return self._dbstring


class ChromaTest(unittest.TestCase):

    def setUp(self):
        logging.basicConfig(level=logging.DEBUG)
        conf = MockConf(dbstring="sqlite://")
        self.db = DB(conf)
        self.db.create_all()
        self.sess = self.db.session()
        self.sess.add_all(Region.create_from_json(TEST_LANDS))

        self.sess.commit()
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

    def get_region(self, name):
        name = name.lower()
        region = self.sess.query(Region).filter_by(name=name).first()
        return region


class TestRegions(ChromaTest):

    def test_region_autocapital(self):
        """A region that's a capital is automatically owned by the same team"""
        cap = Region.capital_for(0, self.sess)
        self.assertEqual(cap.capital, cap.owner)

        cap = Region.capital_for(1, self.sess)
        self.assertEqual(cap.capital, cap.owner)


class TestPlaying(ChromaTest):

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

    def test_disallow_unscheduled_invasion(self):
        """Can't move somewhere you don't own or aren't invading"""
        londo = self.get_region("Orange Londo")
        # For testing purposes, londo is now neutral
        londo.owner = None

        with self.assertRaises(db.OwnershipException):
            self.alice.move(100, londo, 0)

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

    def test_disallow_overdraw_movement(self):
        """Make sure you can't move more people than you have"""
        londo = self.get_region("Orange Londo")
        old = self.alice.region

        with self.assertRaises(db.InsufficientException):
            self.alice.move(10000, londo, 0)

        # She should still be in the capital
        self.assertEqual(self.alice.region.id, old.id)

    def test_disallow_nonadjacent_movement(self):
        """Make sure you can't move to somewhere that's not next to you"""
        old = self.alice.region
        pericap = self.get_region("Periopolis")

        with self.assertRaises(db.NonAdjacentException):
            # Strike instantly at the heart of the enemy!
            self.alice.move(100, pericap, 0)

        # Actually, no, nevermind, let's stay here
        self.assertEqual(self.alice.region.id, old.id)

    def test_delayed_movement(self):
        """Most movement should take a while"""
        home = self.alice.region
        londo = self.get_region("Orange Londo")

        # Everything's fine
        self.assertFalse(self.alice.is_moving())

        # Ideally, this test will not take a day to complete
        order = self.alice.move(100, londo, 60 * 60 * 24)
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
        order = self.alice.move(100, londo, 60 * 60 * 24)
        self.assert_(order)

        with self.assertRaises(db.InProgressException):
            # Sending to londo because Alice is technically still in the
            # capital, otherwise we'd get a NotAdjacentException
            self.alice.move(100, londo, 0)


class TestBattle(ChromaTest):

    def test_battle_creation(self):
        """Typical battle announcement"""
        londo = self.get_region("Orange Londo")
        # For testing purposes, londo is now neutral
        londo.owner = None

        now = time.mktime(time.localtime())
        when = now + 60 * 60 * 24
        battle = londo.invade(self.alice, when)

        self.assert_(battle)

        # Unless that commit took 24 hours, the battle's not ready yet
        self.assertFalse(battle.is_ready())

        # Move the deadline back
        battle.begins = now
        self.sess.commit()

        self.assert_(battle.is_ready())

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

    def test_disallow_nonadjacent_invasion(self):
        """Invasion must come from somewhere you control"""
        pericap = self.get_region("Periopolis")

        with self.assertRaises(db.NonAdjacentException):
            pericap.invade(self.alice, 0)

    def test_disallow_friendly_invasion(self):
        """Can't invade somewhere you already control"""
        londo = self.get_region("Orange Londo")

        with self.assertRaises(db.OwnershipException):
            londo.invade(self.alice, 0)

    def test_disallow_peon_invasion(self):
        """Must have .leader set to invade"""
        londo = self.get_region("Orange Londo")
        londo.owner = None
        self.alice.leader = False

        with self.assertRaises(db.RankException):
            londo.invade(self.alice, 0)

    # Now that the formalities are out of the way
    def test_full_battle(self):
        londo = self.get_region("Orange Londo")
        self.alice.region = londo
        self.sess.commit()
        sapphire = self.get_region("Sapphire")

        # Let's have Periwinkle start the hostilities
        now = time.mktime(time.localtime())
        battle = sapphire.invade(self.bob, now)

        # Battle should be ready, but not started
        self.assert_(battle.is_ready())
        self.assertFalse(battle.has_started())

        # Let's get a party started
        battle.submission_id = "TEST"
        self.assert_(battle.has_started())

if __name__ == '__main__':
    unittest.main()
