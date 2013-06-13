import logging
import time
import unittest

import db
from db import (DB, Battle, Region, MarchingOrder, SkirmishAction, User)


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
        n = (self.sess.query(db.MarchingOrder).
            filter_by(leader=self.alice)).count()
        self.assertEqual(n, 1)


class TestBattle(ChromaTest):

    def setUp(self):
        ChromaTest.setUp(self)
        sapphire = self.get_region("Sapphire")

        self.sapphire = sapphire

        self.alice.region = sapphire
        self.bob.region = sapphire

        self.carol = self.create_user("carol", 0)
        self.carol.region = sapphire
        self.dave = self.create_user("dave", 1)
        self.dave.region = sapphire

        self.sess.commit()

        now = time.mktime(time.localtime())
        self.battle = sapphire.invade(self.bob, now)
        self.battle.ends = now + 60 * 60 * 24
        self.assert_(self.battle)

    def test_battle_creation(self):
        """Typical battle announcement"""
        londo = self.get_region("Orange Londo")
        # For testing purposes, londo is now neutral
        londo.owner = None

        now = time.mktime(time.localtime())
        when = now + 60 * 60 * 24
        battle = londo.invade(self.alice, when)
        battle.ends = when  # Also end it then, too
        self.sess.commit()

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

        n = (self.sess.query(db.Battle).count())
        self.assertEqual(n, 2)

    def test_disallow_nonadjacent_invasion(self):
        """Invasion must come from somewhere you control"""
        pericap = self.get_region("Periopolis")

        with self.assertRaises(db.NonAdjacentException):
            pericap.invade(self.alice, 0)
        n = (self.sess.query(db.Battle).count())
        self.assertEqual(n, 1)

    def test_disallow_friendly_invasion(self):
        """Can't invade somewhere you already control"""
        londo = self.get_region("Orange Londo")

        with self.assertRaises(db.TeamException):
            londo.invade(self.alice, 0)
        n = (self.sess.query(db.Battle).count())
        self.assertEqual(n, 1)

    def test_disallow_peon_invasion(self):
        """Must have .leader set to invade"""
        londo = self.get_region("Orange Londo")
        londo.owner = None
        self.alice.leader = False

        with self.assertRaises(db.RankException):
            londo.invade(self.alice, 0)
        n = (self.sess.query(db.Battle).count())
        self.assertEqual(n, 1)

    def test_skirmish_parenting(self):
        """Make sure I set up relationships correctly w/ skirmishes"""
        root = SkirmishAction()
        a1 = SkirmishAction()
        a2 = SkirmishAction()
        self.sess.add_all([root, a1, a2])
        self.sess.commit()

        root.children.append(a1)
        root.children.append(a2)
        self.sess.commit()

        self.assertEqual(a1.parent_id, root.id)
        self.assertEqual(a2.parent_id, root.id)

    def test_battle_skirmish_assoc(self):
        """Make sure top-level skirmishes are associated with their battles"""
        battle = self.battle

        s1 = battle.create_skirmish(self.alice, 1)
        s2 = battle.create_skirmish(self.bob, 1)

        s3 = s2.react(self.alice, 1)

        self.assertEqual(len(battle.skirmishes), 2)
        self.assertIn(s1, battle.skirmishes)
        self.assertIn(s2, battle.skirmishes)
        self.assertNotIn(s3, battle.skirmishes)

        self.assertEqual(s1.battle, battle)

    def test_get_battle(self):
        """get_battle and get_root work, right?"""
        battle = self.battle

        s1 = battle.create_skirmish(self.alice, 1)
        s2 = battle.create_skirmish(self.bob, 1)

        s3 = s2.react(self.alice, 1)

        self.assertEqual(battle, s1.get_battle())
        self.assertEqual(battle, s3.get_battle())

    def test_simple_unopposed(self):
        """Bare attacks are unopposed"""
        s1 = self.battle.create_skirmish(self.alice, 1)
        s1.resolve()
        self.assert_(s1.unopposed)

        # Should be worth 2 VP
        self.assertEqual(s1.vp, 2)

    def test_canceled_unopposed(self):
        """Attacks that have counterattacks nullified are unopposed"""
        s1 = self.battle.create_skirmish(self.alice, 1)   # Attack 1
        s1a = s1.react(self.bob, 2)                       # --Attack 2
        s1a.react(self.alice, 9)                          # ----Attack 9
        s1.resolve()
        self.assertEqual(s1.victor, self.alice.team)
        self.assert_(s1.unopposed)

        # Should be 4 VP (double the 2 it'd ordinarily be worth)
        self.assertEqual(s1.vp, 4)

    def test_not_unopposed(self):
        """If there's an attack, even if ineffective, it's opposed"""
        s1 = self.battle.create_skirmish(self.alice, 2)   # Attack 2
        s1.react(self.bob, 1)                             # --Attack 1
        s1.resolve()
        self.assertFalse(s1.unopposed)

    def test_committed_loyalists(self):
        """We're actually committing to battle, right?"""
        # Indirectly tested in test_no_adds_to_overdraw_skirmish, too
        old = self.alice.committed_loyalists
        self.battle.create_skirmish(self.alice, 5)
        self.assertEqual(old + 5, self.alice.committed_loyalists)

    def test_decommit_after_battle(self):
        """When the battle's over, we no longer commit, right?"""
        sess = self.sess
        self.battle.submission_id = "TEST"  # So update_all will work correctly

        old = self.alice.committed_loyalists
        self.battle.create_skirmish(self.alice, 5)

        # And just like that, the battle's over
        self.battle.ends = 0
        sess.commit()

        updates = Battle.update_all(sess)
        sess.commit()

        self.assertNotEqual(len(updates['ended']), 0)
        self.assertEqual(updates["ended"][0], self.battle)

        self.assertEqual(self.alice.committed_loyalists, old)

    def test_single_toplevel_skirmish_each(self):
        """Each participant can only make one toplevel skirmish"""
        self.battle.create_skirmish(self.alice, 1)

        with self.assertRaises(db.InProgressException):
            self.battle.create_skirmish(self.alice, 1)

        n = (self.sess.query(db.SkirmishAction).filter_by(parent_id=None).
            filter_by(participant=self.alice)).count()
        self.assertEqual(n, 1)

    def test_commit_at_least_one(self):
        """It isn't a skirmish without fighters"""
        with self.assertRaises(db.InsufficientException):
            self.battle.create_skirmish(self.alice, 0)

        with self.assertRaises(db.InsufficientException):
            self.battle.create_skirmish(self.alice, -5)

        n = (self.sess.query(db.SkirmishAction).filter_by(parent_id=None).
            filter_by(participant=self.alice)).count()
        self.assertEqual(n, 0)

    def test_support_at_least_one(self):
        # Saw this happen in testing, not sure why, reproducing here:
        s1 = self.battle.create_skirmish(self.alice, 1)
        with self.assertRaises(db.InsufficientException):
            s1.react(self.alice, 0, hinder=False)

        n = (self.sess.query(db.SkirmishAction).
            filter_by(participant=self.alice)).count()
        self.assertEqual(n, 1)

    def test_no_overdraw_skirmish(self):
        """Can't start a skirmish with more loyalists than you have"""
        with self.assertRaises(db.InsufficientException):
            self.battle.create_skirmish(self.alice, 9999999)

        n = (self.sess.query(db.SkirmishAction).filter_by(parent_id=None).
            filter_by(participant=self.alice)).count()
        self.assertEqual(n, 0)

    def test_no_adds_to_overdraw_skirmish(self):
        """Can't commit more loyalists than you have"""
        s1 = self.battle.create_skirmish(self.alice, 99)
        with self.assertRaises(db.InsufficientException):
            s1.react(self.alice, 2, hinder=False)

        n = (self.sess.query(db.SkirmishAction).filter_by(parent_id=None).
            filter_by(participant=self.alice)).count()
        self.assertEqual(n, 1)

    def test_stop_hitting_yourself(self):
        """Can't hinder your own team"""
        s1 = self.battle.create_skirmish(self.alice, 1)
        with self.assertRaises(db.TeamException):
            s1.react(self.alice, 1, hinder=True)

        n = (self.sess.query(db.SkirmishAction).filter_by(parent_id=None).
            filter_by(participant=self.alice)).count()
        self.assertEqual(n, 1)

    def test_disallow_betrayal(self):
        """Can't help the opposing team"""
        s1 = self.battle.create_skirmish(self.alice, 1)
        with self.assertRaises(db.TeamException):
            s1.react(self.bob, 1, hinder=False)

        n = (self.sess.query(db.SkirmishAction).filter_by(parent_id=None).
            filter_by(participant=self.alice)).count()
        self.assertEqual(n, 1)

    def test_disallow_absent_fighting(self):
        """Can't fight in a region you're not in"""
        londo = self.get_region("Orange Londo")
        self.alice.region = londo
        self.sess.commit()

        with self.assertRaises(db.NotPresentException):
            self.battle.create_skirmish(self.alice, 1)

        n = (self.sess.query(db.SkirmishAction).filter_by(parent_id=None).
            filter_by(participant=self.alice)).count()
        self.assertEqual(n, 0)

    def test_disallow_retreat(self):
        """Can't move away once you've begun a fight"""
        self.battle.create_skirmish(self.alice, 1)
        londo = self.get_region("Orange Londo")

        with self.assertRaises(db.InProgressException):
            self.alice.move(100, londo, 0)

        n = (self.sess.query(db.MarchingOrder).
            filter_by(leader=self.alice)).count()
        self.assertEqual(n, 0)

    def test_simple_resolve(self):
        """Easy battle resolution"""
        battle = self.battle
        s1 = battle.create_skirmish(self.alice, 10)  # Attack 10
        s1.react(self.bob, 9)                        # --Attack 9

        result = s1.resolve()
        self.assert_(result)
        self.assertEqual(result.victor, self.alice.team)
        self.assertEqual(result.vp, 9)

    def test_failed_attack(self):
        """Stopping an attack should award VP to the ambushers"""
        battle = self.battle
        s1 = battle.create_skirmish(self.alice, 10)  # Attack 10
        s1.react(self.bob, 19)                       # --Attack 19

        result = s1.resolve()
        self.assert_(result)
        self.assertEqual(result.victor, self.bob.team)
        self.assertEqual(result.vp, 10)

    def test_supply_ambush(self):
        """Taking out a 'support' should not escalate further"""
        battle = self.battle
        s1 = battle.create_skirmish(self.alice, 1)
        s2 = s1.react(self.alice, 1, hinder=False)
        s2.react(self.bob, 100)  # OVERKILL!

        # Alice still wins, though - the giant 99 margin attack is just to stop
        # reinforcements
        result = s1.resolve()
        self.assert_(result)
        self.assertEqual(result.victor, self.alice.team)

    def test_complex_resolve_cancel(self):
        """Multilayer battle resolution that cancels itself out"""
        battle = self.battle
        s1 = battle.create_skirmish(self.alice, 1)  # Attack 1
        s2 = s1.react(self.alice, 1, hinder=False)  # --Support 1
        s2.react(self.bob, 10)                      # ----Attack 10
        s3 = s1.react(self.bob, 10)                 # --Attack 10
        s3.react(self.alice, 10)                    # ----Attack 10

        # Make sure the leaves cancel correctly
        s2result = s2.resolve()
        self.assert_(s2result)
        self.assertEqual(s2result.victor, self.bob.team)

        s3result = s3.resolve()
        self.assert_(s3result)
        self.assertEqual(s3result.victor, None)

        # All the supports and attacks cancel each other out, winner should
        # be alice by 1
        result = s1.resolve()
        self.assert_(result)
        self.assertEqual(result.victor, self.alice.team)
        self.assertEqual(result.margin, 1)
        # s2 has 1 die, s2react has 1 die, s3 has 10 die, s3react has 10 die
        # total = 11 each; 22 because alice ends up unopposed
        self.assertEqual(result.vp, 22)

    def test_additive_support(self):
        battle = self.battle
        s1 = battle.create_skirmish(self.alice, 1)   # Attack 1
        s2 = s1.react(self.alice, 19, hinder=False)  # --Support 19
        s2.react(self.alice, 1, hinder=False)        # ----Support 1
        s3 = s1.react(self.bob, 20)                  # --Attack 20
        s3.react(self.alice, 5)                      # ----Attack 5

        # s2react's support adds 1 to its parent
        # Alice gets 20 from support for total of 21, bob gets 15
        result = s1.resolve()
        self.assert_(result)
        self.assertEqual(result.victor, self.alice.team)
        self.assertEqual(result.margin, 6)

    def test_additive_attacks(self):
        battle = self.battle
        s1 = battle.create_skirmish(self.alice, 1)   # Attack 1
        s1.react(self.alice, 19, hinder=False)       # --Support 19
        s3 = s1.react(self.bob, 20)                  # --Attack 20
        s3.react(self.bob, 5, hinder=False)          # ----Support 5

        # s3react's support adds 5 to its parent
        # Alice gets 20 support total, bob gets 25 attack
        result = s1.resolve()
        self.assert_(result)
        self.assertEqual(result.victor, self.bob.team)
        self.assertEqual(result.margin, 5)

    def test_complex_resolve_bob(self):
        """Multilayer battle resolution that ends with bob winning"""
        battle = self.battle
        s1 = battle.create_skirmish(self.alice, 1)   # Attack 1
        s2 = s1.react(self.alice, 10, hinder=False)  # --Support 10
        s2.react(self.bob, 1)                        # ----Attack 1
        s3 = s1.react(self.bob, 20)                  # --Attack 20
        s3.react(self.alice, 5)                      # ----Attack 5

        # Alice will win 9 support from her support,
        # but bob will gain 15 attack from his attack
        # Final score: alice 10 vs bob 15
        # Winner:  Bob by 5
        result = s1.resolve()
        self.assert_(result)
        self.assertEqual(result.victor, self.bob.team)
        self.assertEqual(result.margin, 5)

        # s2 has 1 die, s2react has 1 die, s3 has 5 die, s3react has 5 die
        # final battle has 10 die on each side
        # alice: 5 + 1 + 10, bob: 5 + 1 + 10
        self.assertEqual(result.vp, 16)

    def test_full_battle(self):
        """Full battle"""
        battle = self.battle
        sess = self.sess

        oldowner = self.sapphire.owner

        # Battle should be ready, but not started
        self.assert_(battle.is_ready())
        self.assertFalse(battle.has_started())

        # Let's get a party started
        battle.submission_id = "TEST"
        self.assert_(battle.has_started())

        # Still going, right?
        self.assertFalse(battle.past_end_time())

        # Skirmish 1
        s1 = battle.create_skirmish(self.alice, 10)  # Attack 10
        s1a = s1.react(self.carol, 3, hinder=False)  # --Support 3
        s1a.react(self.bob, 3)                       # ----Attack 3
        s1.react(self.dave, 8)                       # --Attack 8
        # Winner will be team orangered, 11 VP

        # Skirmish 2
        battle.create_skirmish(self.bob, 15)         # Attack 15
        # Winner will be team periwinkle, 30 VP for unopposed

        # Skirmish 3
        s3 = battle.create_skirmish(self.carol, 10)  # Attack 10
        s3.react(self.bob, 5)                        # --Attack 5
        # Winner will be team orangered, 5 VP
        # Overall winner should be team periwinkle, 30 to 16

        # End this bad boy
        self.battle.ends = 0
        sess.commit()
        self.assert_(battle.past_end_time())

        updates = Battle.update_all(sess)
        sess.commit()

        self.assertNotEqual(len(updates['ended']), 0)
        self.assertEqual(updates["ended"][0], battle)
        self.assertEqual(battle.victor, 1)
        self.assertEqual(battle.score0, 16)
        self.assertEqual(battle.score1, 30)

        self.assertNotEqual(oldowner, battle.region.owner)
        self.assertEqual(battle.region.owner, 1)

if __name__ == '__main__':
    unittest.main()
