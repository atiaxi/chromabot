# coding=utf-8

import logging
import time
import unittest

from chromabot import db
from chromabot.db import (Battle, Processed, SkirmishAction)
from playtest import ChromaTest, MockConf
from chromabot.utils import now


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
        self.battle.display_ends = self.battle.ends
        self.battle.submission_id = "TEST"
        self.assert_(self.battle)

        self.sess.commit()

    def end_battle(self, battle=None, conf=None):
        if battle is None:
            battle = self.battle
        sess = self.sess

        battle.ends = battle.begins
        sess.commit()
        updates = Battle.update_all(sess, conf)
        sess.commit()

        self.assertNotEqual(len(updates['ended']), 0)
        self.assertEqual(updates["ended"][0], battle)
        return battle

    def start_endable_skirmish(self, alice_forces=10, bob_forces=9):
        self.conf["game"]["skirmish_time"] = 60 * 60 * 24
        battle = self.battle
        s1 = battle.create_skirmish(self.alice, alice_forces, conf=self.conf)
        s2 = s1.react(self.bob, bob_forces)
        return (s1, s2)

    def end_skirmish(self, skirmish):
        sess = self.sess
        skirmish.ends = 1
        Battle.update_all(sess)
        return skirmish

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

        self.assertEqual(len(battle.skirmishes), 3)
        self.assertIn(s1, battle.skirmishes)
        self.assertIn(s2, battle.skirmishes)
        # s3 should inherit its battle from its parents
        self.assertIn(s3, battle.skirmishes)

        self.assertEqual(s1.battle, battle)

    def test_proper_cascade(self):
        """When a battle is deleted, everything should go with it"""
        battle = self.battle

        battle.create_skirmish(self.alice, 1)
        s2 = battle.create_skirmish(self.bob, 1)
        s2.react(self.alice, 1)
        s2.buff_with(db.Buff.first_strike())

        # Make up some processed comments
        battle.processed_comments.append(Processed(id36="foo"))
        battle.processed_comments.append(Processed(id36="bar"))
        self.sess.commit()
        self.assertNotEqual(self.sess.query(Processed).count(), 0)
        self.assertNotEqual(self.sess.query(SkirmishAction).count(), 0)
        self.assertNotEqual(self.sess.query(db.Buff).count(), 0)

        self.sess.delete(battle)
        self.sess.commit()

        # Shouldn't be any skirmishes or processed
        self.assertEqual(self.sess.query(Processed).count(), 0)
        self.assertEqual(self.sess.query(SkirmishAction).count(), 0)
        self.assertEqual(self.sess.query(db.Buff).count(), 0)

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

    def test_no_early_fights(self):
        """
        Even if battle thread's live, can't fight until the battle
        actually starts
        """
        self.battle.begins = now() + 60 * 60 * 12

        self.assertFalse(self.battle.is_ready())
        self.assertFalse(self.battle.has_started())

        with self.assertRaises(db.TimingException):
            self.battle.create_skirmish(self.alice, 1)

        n = (self.sess.query(db.SkirmishAction).filter_by(parent_id=None).
            filter_by(participant=self.alice)).count()
        self.assertEqual(n, 0)

    def test_canceled_unopposed(self):
        """Attacks that have counterattacks nullified are unopposed"""
        s1 = self.battle.create_skirmish(self.alice, 10)   # Attack 10
        s1a = s1.react(self.bob, 8,
                       troop_type="cavalry")               # --Attack 8 (12)
        s1a.react(self.alice, 6,
                  troop_type="ranged")                     # ----Attack 6 (9)
        s1.resolve()
        self.assertEqual(s1.victor, self.alice.team)
        self.assert_(s1.unopposed)

        # Should be 20 VP (double the 10 it'd ordinarily be worth)
        self.assertEqual(s1.vp, 20)

    def test_not_unopposed(self):
        """If there's an attack, even if ineffective, it's opposed"""
        s1 = self.battle.create_skirmish(self.alice, 2)   # Attack 2
        s1.react(self.bob, 1)                             # --Attack 1
        s1.resolve()
        self.assertFalse(s1.unopposed)

    def test_no_overkill(self):
        """You can't use more loyalists than whoever started the fight"""
        s1 = self.battle.create_skirmish(self.alice, 10)  # Attack 10
        s1.react(self.carol, 10, hinder=False)  # Right amount = ok

        with self.assertRaises(db.TooManyException):
            s1.react(self.bob, 11)

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
        self.end_battle()

        self.assertEqual(self.alice.committed_loyalists, old)

    def test_ejection_after_battle(self):
        """We don't want the losers sticking around after the fight"""
        self.battle.submission_id = "TEST"  # So update_all will work correctly

        old_bob_region = self.bob.region
        old_alice_region = self.alice.region
        self.battle.create_skirmish(self.alice, 5)

        self.end_battle()

        self.assertEqual(self.battle.victor, self.alice.team)

        self.assertNotEqual(self.bob.region, self.alice.region)
        self.assertNotEqual(self.bob.region, old_bob_region)
        self.assertEqual(self.alice.region, old_alice_region)

    def test_reward_after_battle(self):
        """Participants get 10% of their committed, winners 15%"""
        self.assertEqual(self.alice.loyalists, 100)
        self.assertEqual(self.bob.loyalists, 100)

        s1 = self.battle.create_skirmish(self.alice, 50)
        s1.react(self.bob, 50, troop_type="cavalry")

        self.end_battle(self.battle, self.conf)

        # Bob wins the fight and the war
        self.assertEqual(self.battle.victor, self.bob.team)

        # Alice should have gotten a 10% reward (5 troops)
        self.assertEqual(self.alice.loyalists, 105)
        # Bob gets 15% (7 troops)
        self.assertEqual(self.bob.loyalists, 107)

    def test_configurable_reward_after_battle(self):
        """Participants get 5% of their committed, winners 7%"""
        self.conf["game"]["winreward"] = 7
        self.conf["game"]["losereward"] = 5

        self.assertEqual(self.alice.loyalists, 100)
        self.assertEqual(self.bob.loyalists, 100)

        s1 = self.battle.create_skirmish(self.alice, 50)
        s1.react(self.bob, 50, troop_type="cavalry")

        self.end_battle(self.battle, self.conf)

        # Bob wins the fight and the war
        self.assertEqual(self.battle.victor, self.bob.team)

        # Alice should have gotten a 5% reward (2 troops)
        self.assertEqual(self.alice.loyalists, 102)
        # Bob gets 7% (3 troops)
        self.assertEqual(self.bob.loyalists, 103)

    def test_troop_cap(self):
        """Setting a troop cap should work"""
        self.conf["game"]["troopcap"] = 106

        self.assertEqual(self.alice.loyalists, 100)
        self.assertEqual(self.bob.loyalists, 100)

        s1 = self.battle.create_skirmish(self.alice, 50)
        s1.react(self.bob, 50, troop_type='cavalry')

        self.end_battle(self.battle, self.conf)

        # Bob wins the fight and the war
        self.assertEqual(self.battle.victor, self.bob.team)

        # Alice's 10% reward puts her under cap
        self.assertEqual(self.alice.loyalists, 105)
        # Bob's 15% reward puts him over
        self.assertEqual(self.bob.loyalists, 106)

    def test_single_toplevel_skirmish_each(self):
        """Each participant can only make one toplevel skirmish"""
        self.battle.create_skirmish(self.alice, 1)

        with self.assertRaises(db.InProgressException):
            self.battle.create_skirmish(self.alice, 1)

        n = (self.sess.query(db.SkirmishAction).filter_by(parent_id=None).
            filter_by(participant=self.alice)).count()
        self.assertEqual(n, 1)

    def test_single_response_to_skirmish(self):
        """Each participant can only response once to a skirmishaction"""
        s1 = self.battle.create_skirmish(self.alice, 1)
        s1.react(self.bob, 1)

        with self.assertRaises(db.InProgressException):
            s1.react(self.bob, 1)

        n = (self.sess.query(db.SkirmishAction).
             count())
        self.assertEqual(n, 2)

    def test_no_last_minute_ambush(self):
        """
        Can't make toplevel attacks within the last X seconds of the battle
        """
        self.battle.lockout = 60 * 60 * 24
        with self.assertRaises(db.TimingException):
            self.battle.create_skirmish(self.alice, 1)

        n = (self.sess.query(db.SkirmishAction).filter_by(parent_id=None).
            filter_by(participant=self.alice)).count()
        self.assertEqual(n, 0)

    def test_no_rookies_toplevel(self):
        """
        Can't participate in a battle if you were created before it was
        """
        self.bob.recruited = now() + 6000

        # Top level
        with self.assertRaises(db.TimingException):
            self.battle.create_skirmish(self.bob, 1)

        self.assertEqual(self.sess.query(db.SkirmishAction).count(), 0)

    def test_no_rookies_react(self):
        self.bob.recruited = now() + 6000

        # No responses, either
        s1 = self.battle.create_skirmish(self.alice, 1)
        with self.assertRaises(db.TimingException):
            s1.react(self.bob, 1)

        self.assertEqual(self.sess.query(db.SkirmishAction).count(), 1)

    def test_enable_rookies(self):
        self.bob.recruited = now() + 6000
        s1 = self.battle.create_skirmish(self.bob, 1, enforce_noob_rule=False)
        s1.react(self.bob, 1, hinder=False, enforce_noob_rule=False)

        self.assertEqual(self.sess.query(db.SkirmishAction).count(), 2)

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

    def test_disallow_extract(self):
        """Can't even emergency evac in a warzone"""
        self.battle.create_skirmish(self.alice, 1)
        cap = self.get_region("Oraistedarg")
        self.assertNotEqual(self.alice.region, cap)

        with self.assertRaises(db.InProgressException):
            self.alice.extract()

        n = (self.sess.query(db.MarchingOrder).
            filter_by(leader=self.alice)).count()
        self.assertEqual(n, 0)
        self.assertNotEqual(self.alice.region, cap)

    def test_disallow_fighting_retreat(self):
        """Can't start moving away then start a fight"""
        londo = self.get_region("Orange Londo")
        self.alice.move(100, londo, 60 * 60 * 24)

        with self.assertRaises(db.InProgressException):
            self.battle.create_skirmish(self.alice, 1)

    def test_simple_resolve(self):
        """Easy battle resolution"""
        battle = self.battle
        s1 = battle.create_skirmish(self.alice, 10)  # Attack 10
        s1.react(self.bob, 9)                        # --Attack 9
        # Without a conf entry, skirmishes don't end
        self.assertFalse(s1.ends)

        result = s1.resolve()
        self.assert_(result)
        self.assertEqual(result.victor, self.alice.team)
        self.assertEqual(result.vp, 9)

    def test_skirmish_end(self):
        """Skirmishes should be allowed to expire!"""
        s1, s2 = self.start_endable_skirmish()

        self.assertTrue(s1.ends)
        self.assertFalse(s1.is_resolved())

        # Go through one round of battle updating to verify skirmish
        # doesn't end early
        sess = self.sess
        db.Battle.update_all(sess)

        self.assertTrue(s1.ends)
        self.assertFalse(s1.is_resolved())
        self.assertFalse(s2.is_resolved())

        # Force skirmish end
        self.end_skirmish(s1)

        # Skirmish should have been resolved
        self.assertTrue(s1.is_resolved())
        self.assertTrue(s2.is_resolved())

        # With alice as the victor
        self.assertEqual(s1.victor, self.alice.team)

    def test_skirmish_random_end(self):
        # 1 in 1800 chance this test fails, I can live with that.
        self.conf["game"]["skirmish_variability"] = 1800
        s1, _ = self.start_endable_skirmish()
        self.assert_(s1.display_ends)
        self.assertNotEqual(s1.ends, s1.display_ends)

    def test_ended_skirmishes_block(self):
        """Still can't spearhead a skirmish even if your last skirmish is done
        """
        skirmish, _ = self.start_endable_skirmish()
        self.end_skirmish(skirmish)

        with self.assertRaises(db.InProgressException):
            self.battle.create_skirmish(self.alice, 1)

        n = (self.sess.query(db.SkirmishAction).filter_by(parent_id=None).
            filter_by(participant=self.alice)).count()
        self.assertEqual(n, 1)

    def test_no_decommit_after_skirmishes(self):
        """Expired skirmishes still count against your total"""
        skirmish, _ = self.start_endable_skirmish(alice_forces=5, bob_forces=5)
        self.end_skirmish(skirmish)

        self.assertEqual(5, self.alice.committed_loyalists)

    def test_no_reply_to_expired_skirmish(self):
        """Can't fight in a skimrish that's over!"""
        s1, s2 = self.start_endable_skirmish()
        self.end_skirmish(s1)
        with self.assertRaises(db.TimingException):
            s1.react(self.dave, 1)

        # Make sure the non-root nodes also don't allow it
        with self.assertRaises(db.TimingException):
            s2.react(self.carol, 1)

    def test_ties_resolve_correctly(self):
        """Ties still count as resolved"""
        skirmish, _ = self.start_endable_skirmish(alice_forces=1, bob_forces=1)
        self.assertFalse(skirmish.is_resolved())
        self.end_skirmish(skirmish)

        self.assertTrue(skirmish.is_resolved())

    def test_failed_attack(self):
        """Stopping an attack should award VP to the ambushers"""
        battle = self.battle
        s1 = battle.create_skirmish(self.alice, 10)  # Attack 10
        s1.react(self.bob, 10)                       # --Attack 10
        s1.react(self.dave, 9)                       # --Attack 9

        result = s1.resolve()
        self.assert_(result)
        self.assertEqual(result.victor, self.bob.team)
        self.assertEqual(result.vp, 10)

    def test_supply_ambush(self):
        """Taking out a 'support' should not escalate further"""
        battle = self.battle
        s1 = battle.create_skirmish(self.alice, 2)
        s2 = s1.react(self.alice, 2, hinder=False)
        s2.react(self.bob, 2, troop_type="cavalry")

        # Alice still wins, though - the margin attack is just to stop
        # reinforcements
        result = s1.resolve()
        self.assert_(result)
        self.assertEqual(result.victor, self.alice.team)

    def test_default_codeword(self):
        """Supplying an unrecognized codeword should default to 'infantry'"""
        battle = self.battle
        s1 = battle.create_skirmish(self.alice, 1, troop_type='muppet')
        self.assertEqual(s1.troop_type, "infantry")

    def test_codeword(self):
        """Use of codewords in top-level skirmises"""
        self.assertEqual(self.sess.query(db.CodeWord).count(), 0)
        self.alice.add_codeword('muppet', 'ranged')
        self.assertEqual(self.sess.query(db.CodeWord).count(), 1)

        battle = self.battle
        s1 = battle.create_skirmish(self.alice, 1, troop_type='muppet')
        self.assertEqual(s1.troop_type, "ranged")

        self.alice.remove_codeword('muppet')
        self.assertEqual(self.sess.query(db.CodeWord).count(), 0)
        s2 = s1.react(self.alice, 1, hinder=False, troop_type='muppet')
        self.assertEqual(s2.troop_type, 'infantry')

    def test_unicodeword(self):
        self.alice.add_codeword(u'ಠ_ಠ', 'ranged')
        battle = self.battle
        s1 = battle.create_skirmish(self.alice, 1, troop_type=u'ಠ_ಠ')
        self.assertEqual(s1.troop_type, "ranged")

    def test_overwrite_codeword(self):
        """Use of codewords in top-level skirmises"""
        self.assertEqual(self.sess.query(db.CodeWord).count(), 0)
        self.alice.add_codeword('muppet', 'ranged')
        self.assertEqual(self.alice.translate_codeword('muppet'), 'ranged')
        self.assertEqual(self.sess.query(db.CodeWord).count(), 1)
        self.alice.add_codeword('muppet', 'infantry')
        self.assertEqual(self.alice.translate_codeword('muppet'), 'infantry')
        self.assertEqual(self.sess.query(db.CodeWord).count(), 1)

    def test_extra_default_codeword(self):
        """Using the wrong codeword should also default to infantry"""
        self.alice.add_codeword("flugelhorn", "ranged")

        battle = self.battle
        s1 = battle.create_skirmish(self.alice, 1, troop_type='muppet')
        self.assertEqual(s1.troop_type, "infantry")

    def test_response_codeword(self):
        """Use of codewords in response skirmishes"""
        self.bob.add_codeword('muppet', 'ranged')
        battle = self.battle
        s1 = battle.create_skirmish(self.alice, 100)
        s2 = s1.react(self.bob, 100, troop_type='muppet')
        self.assertEqual(s2.troop_type, 'ranged')

    def test_no_cross_codewording(self):
        """Bob's codewords don't work for alice"""
        self.bob.add_codeword('muppet', 'ranged')

        battle = self.battle
        s1 = battle.create_skirmish(self.alice, 1, troop_type='muppet')
        self.assertEqual(s1.troop_type, "infantry")

    def test_complex_resolve_cancel(self):
        """Multilayer battle resolution that cancels itself out"""
        battle = self.battle
        s1 = battle.create_skirmish(self.alice, 10)  # Attack 10
        s2 = s1.react(self.alice, 1, hinder=False)   # --Support 1
        s2.react(self.bob, 10)                       # ----Attack 10
        s3 = s1.react(self.bob, 10)                  # --Attack 10
        s3.react(self.alice, 10)                     # ----Attack 10

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
        self.assertEqual(result.margin, 10)
        # s2 has 1 die, s2react has 1 die, s3 has 10 die, s3react has 10 die
        # total = 11 each; 22 because alice ends up unopposed
        self.assertEqual(result.vp, 22)

    def test_additive_support(self):
        battle = self.battle
        s1 = battle.create_skirmish(self.alice, 20)   # Attack 20
        s2 = s1.react(self.alice, 19, hinder=False)   # --Support 19
        s2.react(self.alice, 1, hinder=False)         # ----Support 1
        s3 = s1.react(self.bob, 20)                   # --Attack 20
        s3.react(self.alice, 5)                       # ----Attack 5

        # s2react's support adds 1 to its parent
        # Alice's 19 support is capped at 19 for a total of 39
        # Bob gets 15
        result = s1.resolve()
        self.assert_(result)
        self.assertEqual(result.victor, self.alice.team)
        self.assertEqual(result.margin, 24)

    def test_no_exponential_support(self):
        """Long chains of support used to provide exponentially larger
        numbers.  Test that the fix (capping support at the stated amount)
        works as intended."""
        battle = self.battle
        s1 = battle.create_skirmish(self.alice, 75)  # Attack 1
        s2 = s1.react(self.carol, 1, hinder=False)   # -- Support 1
        s3 = s2.react(self.carol, 1, hinder=False)   # ---- Support 1
        s4 = s3.react(self.carol, 1, hinder=False)   # ------ Support 1
        s4.react(self.carol, 75, hinder=False)       # -------- Support 75

        result = s1.resolve()
        self.assert_(result)
        self.assertEqual(result.margin, 76)  # Original attack, 1 support

    def test_additive_attacks(self):
        battle = self.battle
        s1 = battle.create_skirmish(self.alice, 20)   # Attack 20
        s1.react(self.alice, 19, hinder=False)        # --Support 19
        s3 = s1.react(self.bob, 20)                   # --Attack 20
        s3.react(self.bob, 5, hinder=False)           # ----Support 5
        s1.react(self.dave, 19)

        # s3react's support adds 5 to its parent
        # Alice gets 20 support total, bob gets 25 attack
        result = s1.resolve()
        self.assert_(result)
        self.assertEqual(result.victor, self.bob.team)
        self.assertEqual(result.margin, 5)

    def test_complex_resolve_bob(self):
        """Multilayer battle resolution that ends with bob winning"""
        battle = self.battle
        s1 = battle.create_skirmish(self.alice, 10)   # Attack 10
        s2 = s1.react(self.alice, 10, hinder=False)   # --Support 10
        s2.react(self.bob, 1)                         # ----Attack 1
        s1.react(self.dave, 9)                        # --Attack 9
        s3 = s1.react(self.bob, 10,
                      troop_type="cavalry")           # --Attack 10
        s3.react(self.alice, 1)                       # ----Attack 1

        result = s1.resolve()
        self.assert_(result)
        self.assertEqual(result.victor, self.bob.team)
        self.assertEqual(result.margin, 5)
        self.assertEqual(result.vp, 21)

    def test_attack_types(self):
        """Using the right type of attack can boost its effectiveness"""
        battle = self.battle
        s1 = battle.create_skirmish(self.alice, 10)  # Attack 10 infantry
        s1.react(self.bob, 8, troop_type='cavalry')  # --Attack 8 cavalry

        # Cavalry should get a 50% bonus here, for a total of 8+4=12
        # So Bob should win by 2 despite lesser numbers
        result = s1.resolve()
        self.assert_(result)
        self.assertEqual(result.victor, self.bob.team)
        self.assertEqual(result.margin, 2)
        self.assertEqual(result.vp, 10)

        s2 = battle.create_skirmish(self.bob, 10,
                                    troop_type='cavalry')  # attack 10 cavalry
        s2.react(self.alice, 8, troop_type='ranged')       # -- oppose 8 ranged
        result = s2.resolve()
        self.assert_(result)
        self.assertEqual(result.victor, self.alice.team)
        self.assertEqual(result.margin, 2)
        self.assertEqual(result.vp, 10)

        s3 = battle.create_skirmish(self.carol, 10,      # Attack 10 ranged
                                    troop_type='ranged')
        s3.react(self.bob, 8)                            # -- oppose 8 infantry
        result = s3.resolve()
        self.assert_(result)
        self.assertEqual(result.victor, self.bob.team)
        self.assertEqual(result.margin, 2)
        self.assertEqual(result.vp, 10)

    def test_bad_attack_types(self):
        """Using the wrong type of attack can hinder its effectiveness"""
        battle = self.battle
        s1 = battle.create_skirmish(self.alice, 10)  # Attack 10 infantry
        s1.react(self.bob, 10, troop_type='ranged')  # --Attack 10 ranged

        # Ranged should get a 50% penalty here, for a total of 10/2 = 5
        # So Alice should win by 5 despite lesser numbers
        result = s1.resolve()
        self.assert_(result)
        self.assertEqual(result.victor, self.alice.team)
        self.assertEqual(result.margin, 5)
        self.assertEqual(result.vp, 10)

        s2 = battle.create_skirmish(self.bob, 10,        # attack 10 ranged
                                    troop_type='ranged')
        s2.react(self.alice, 10, troop_type='cavalry')   # -- oppose 10 cavalry
        result = s2.resolve()
        self.assert_(result)
        self.assertEqual(result.victor, self.bob.team)
        self.assertEqual(result.margin, 5)
        self.assertEqual(result.vp, 10)

        s3 = battle.create_skirmish(self.carol, 10,     # Attack 10 cavalry
                                    troop_type='cavalry')
        s3.react(self.bob, 10)                          # -- oppose 10 infantry
        result = s3.resolve()
        self.assert_(result)
        self.assertEqual(result.victor, self.carol.team)
        self.assertEqual(result.margin, 5)
        self.assertEqual(result.vp, 10)

    def test_support_types(self):
        battle = self.battle

        s1 = battle.create_skirmish(self.alice, 10)  # Attack 10 infantry
        s1.react(self.bob, 9)                        # -- oppose 9 infantry
        s1.react(self.dave, 9)                       # -- oppose 9 infantry
        s1.react(self.alice, 8,                      # -- support 8 ranged
                 troop_type="ranged", hinder=False)
        # Ranged should get a 50% support bonus here, for a total of
        # 10 + 8 + 4 = 22 - alice should win by 4
        result = s1.resolve()
        self.assert_(result)
        self.assertEqual(result.victor, self.alice.team)
        self.assertEqual(result.margin, 4)
        self.assertEqual(result.vp, 18)

        s2 = battle.create_skirmish(self.bob, 10,
                troop_type="ranged")                 # Attack 10 ranged
        s2.react(self.alice, 10,
                 troop_type="ranged")                # -- oppose 10 ranged
        s2.react(self.carol, 9,
                 troop_type="ranged")                # -- oppose 9 ranged
        s2.react(self.bob, 8,                        # -- support 8 cavalry
                 troop_type="cavalry", hinder=False)

        result = s2.resolve()
        self.assert_(result)
        self.assertEqual(result.victor, self.bob.team)
        self.assertEqual(result.margin, 3)
        self.assertEqual(result.vp, 19)

        s3 = battle.create_skirmish(self.carol, 10,
                troop_type="cavalry")                 # Attack 10 cavalry
        s3.react(self.bob, 10,
                 troop_type="cavalry")                # -- oppose 10 cavalry
        s3.react(self.dave, 9,
                 troop_type="cavalry")                # -- oppose 9 cavalry
        s3.react(self.carol, 8, hinder=False)           # -- support 8 infantry

        result = s3.resolve()
        self.assert_(result)
        self.assertEqual(result.victor, self.carol.team)
        self.assertEqual(result.margin, 3)
        self.assertEqual(result.vp, 19)

    def test_bad_support_types(self):
        battle = self.battle

        s1 = battle.create_skirmish(self.alice, 10)  # Attack 10 infantry
        s1.react(self.bob, 10)                       # -- oppose 19 infantry
        s1.react(self.dave, 9)
        s1.react(self.alice, 10,                     # -- support 10 cavalry
                 troop_type="cavalry", hinder=False)
        # Cavalry should get a 50% support penalty here, for a total of
        # 10 + 5 = 15 - bob should win by 4
        result = s1.resolve()
        self.assert_(result)
        self.assertEqual(result.victor, self.bob.team)
        self.assertEqual(result.margin, 4)
        self.assertEqual(result.vp, 20)

        s2 = battle.create_skirmish(self.bob, 10,
                troop_type="ranged")                 # Attack 10 ranged
        s2.react(self.alice, 10,
                 troop_type="ranged")                # -- oppose 19 ranged
        s2.react(self.carol, 9,
                 troop_type="ranged")
        s2.react(self.bob, 10, hinder=False)         # -- support 10 infantry

        result = s2.resolve()
        self.assert_(result)
        self.assertEqual(result.victor, self.alice.team)
        self.assertEqual(result.margin, 4)
        self.assertEqual(result.vp, 20)

        s3 = battle.create_skirmish(self.carol, 10,
                troop_type="cavalry")                 # Attack 10 cavalry
        s3.react(self.bob, 10,
                 troop_type="cavalry")                # -- oppose 19 cavalry
        s3.react(self.dave, 9,
                 troop_type="cavalry")
        s3.react(self.carol, 10,
                 troop_type="ranged",
                 hinder=False)                        # -- support 10 ranged

        result = s3.resolve()
        self.assert_(result)
        self.assertEqual(result.victor, self.bob.team)
        self.assertEqual(result.margin, 4)
        self.assertEqual(result.vp, 20)

    def test_buff_first_strike(self):
        """See that first strike works correctly"""
        battle = self.battle
        s1 = battle.create_skirmish(self.alice, 20)  # Attack 20 infantry
        s1.react(self.bob, 20)                       # -- oppose 20 infantry
        s1.react(self.dave, 4)                       # -- oppose 4 infantry

        s1.buff_with(db.Buff.first_strike())

        result = s1.resolve()
        self.assert_(result)
        self.assertEqual(result.victor, self.alice.team)
        self.assertEqual(result.margin, 1)
        self.assertEqual(result.vp, 24)

    def test_buff_first_strike_support(self):
        """See that first strike works correctly with support"""
        battle = self.battle
        s1 = battle.create_skirmish(self.alice, 20)  # Attack 20 infantry
        s2 = s1.react(self.bob, 10)                  # -- oppose 10 infantry
        s3 = s2.react(self.dave, 9, hinder=False)    # ---- support 9

        s3.buff_with(db.Buff.first_strike())

        result = s1.resolve()
        self.assert_(result)
        self.assertEqual(result.victor, self.bob.team)
        self.assertEqual(result.margin, 1)
        self.assertEqual(result.vp, 20)

    def test_buff_otd(self):
        battle = self.battle

        # For the buff to work, alice needs to own this region
        battle.region.owner = self.alice.team
        self.sess.commit()

        s1 = battle.create_skirmish(self.alice, 30)  # Attack 30 infantry
        s1.react(self.bob, 30,
                 troop_type="cavalry")               # -- oppose 30 cavalry
        result = s1.resolve()
        self.assertEqual(result.victor, self.bob.team)
        self.assertEqual(result.margin, 15)
        self.assertEqual(result.vp, 30)

        s2 = battle.create_skirmish(self.bob, 29)  # Attack with 29 infantry
        s2.react(self.alice, 29,
                 troop_type="cavalry")             # -- oppose with 29 cavalry
        result = s2.resolve()
        self.assertEqual(result.victor, self.alice.team)
        self.assertEqual(result.margin, 14)
        self.assertEqual(result.vp, 29)

        # Bob's winning this, but wait!  A buff!
        battle.region.buff_with(db.Buff.otd())
        self.end_battle()

        # Now alice should be winning, 31 to 30
        self.assertEqual(self.battle.victor, self.alice.team)
        # score1 is the score for team 1
        self.assertEqual(self.battle.score1, 30)
        # score0 should include the buff
        self.assertEqual(self.battle.score0, 31)

    def test_buff_otd_gain(self):
        battle = self.battle
        region = battle.region
        self.assertEqual(region.owner, None)

        battle.create_skirmish(self.alice, 30)  # Attack 30 infantry

        # No buffs before battle ends
        self.assertEqual(self.sess.query(db.Buff).count(), 0)

        self.end_battle()
        # Should have gotten a buff for our region
        self.assertEqual(self.sess.query(db.Buff).count(), 1)
        self.assertEqual(len(region.buffs), 1)
        self.assertEqual(region.buffs[0].internal, "otd")

    def test_buff_expiration(self):
        """Buffs should expire during update"""
        sess = self.sess
        battle = self.battle

        # For the buff to work, alice needs to own this region
        battle.region.owner = self.alice.team
        sess.commit()

        s1 = battle.create_skirmish(self.alice, 30)  # Attack 30 infantry
        s1.react(self.bob, 30)                       # -- oppose 30 infantry
        s1.react(self.dave, 4)                       # -- oppose  4 infantry
        result = s1.resolve()
        self.assertEqual(result.victor, self.bob.team)
        self.assertEqual(result.margin, 4)
        self.assertEqual(result.vp, 30)

        s2 = battle.create_skirmish(self.bob, 29)  # Attack with 29 infantry
        s2.react(self.alice, 29)                   # -- oppose with 29 infantry
        s2.react(self.carol, 2)                    # -- oppose with 2
        result = s2.resolve()
        self.assertEqual(result.victor, self.alice.team)
        self.assertEqual(result.margin, 2)
        self.assertEqual(result.vp, 29)

        # Bob's winning this, but wait!  A buff that expires immediately!
        buff = db.Buff.otd(expiration=-30)
        battle.region.buff_with(buff)

        # One buff should exist in DB
        self.assertEqual(sess.query(db.Buff).count(), 1)
        db.Buff.update_all(sess)
        # Now it should be gone due to expiration
        self.assertEqual(sess.query(db.Buff).count(), 0)

        self.end_battle()

        # Bob wins because buff expired, 30 to 29
        self.assertEqual(self.battle.victor, self.bob.team)
        # score1 is the score for team 1
        self.assertEqual(self.battle.score1, 30)
        # score0 should not include the buff
        self.assertEqual(self.battle.score0, 29)

    def test_buff_fortified_gain(self):
        battle = self.battle
        region = battle.region
        region.owner = self.alice.team

        battle.create_skirmish(self.alice, 30)  # Attack 30 infantry

        # No buffs before battle ends
        self.assertEqual(self.sess.query(db.Buff).count(), 0)
        self.assertFalse(region.has_buff('fortified'))

        self.end_battle()
        # Should have gotten a buff for our region
        self.assertEqual(self.sess.query(db.Buff).count(), 1)
        self.assertEqual(len(region.buffs), 1)
        buff = region.buffs[0]
        self.assertEqual(buff.internal, "fortified")
        # Also test region.has_buff here too
        buff = region.has_buff('fortified')
        self.assert_(buff)
        self.assertIsInstance(buff, db.Buff)
        # Should expire in a week
        self.assertLessEqual(buff.expires, now() + 3600 * 24 * 7)

    def test_configurable_buff_time(self):
        self.conf.game["defense_buff_time"] = 0

        battle = self.battle
        region = battle.region
        region.owner = self.alice.team

        battle.create_skirmish(self.alice, 30)  # Attack 30 infantry

        # No buffs before battle ends
        self.assertEqual(self.sess.query(db.Buff).count(), 0)

        self.end_battle(conf=self.conf)
        # Should have gotten a buff for our region
        self.assertEqual(self.sess.query(db.Buff).count(), 1)
        self.assertEqual(len(region.buffs), 1)
        buff = region.buffs[0]
        self.assertEqual(buff.internal, "fortified")
        # Should already be expired
        self.assertLessEqual(buff.expires, now())

    def test_buff_nostacking(self):
        """Same-named buffs shouldn't stack"""
        battle = self.battle
        s1 = battle.create_skirmish(self.alice, 20)  # Attack 20 infantry
        s1.react(self.bob, 20)                       # -- oppose 20 infantry
        s1.react(self.dave, 6)                       # -- oppose 6 infantry

        s1.buff_with(db.Buff.first_strike())
        s1.buff_with(db.Buff.first_strike())

        result = s1.resolve()
        self.assert_(result)
        self.assertEqual(result.victor, self.bob.team)
        self.assertEqual(result.margin, 1)
        self.assertEqual(result.vp, 20)

    def test_orangered_victory(self):
        """Make sure orangered victories actually count"""
        self.assertEqual(None, self.sapphire.owner)
        sess = self.sess
        self.battle.create_skirmish(self.alice, 5)

        self.battle.ends = self.battle.begins
        sess.commit()
        updates = Battle.update_all(sess)
        sess.commit()

        self.assertNotEqual(len(updates['ended']), 0)
        self.assertEqual(updates["ended"][0], self.battle)
        self.assertEqual(0, self.sapphire.owner)

    def test_full_battle(self):
        """Full battle"""
        battle = self.battle
        sess = self.sess

        oldowner = self.sapphire.owner

        # Battle should be ready and started
        self.assert_(battle.is_ready())
        self.assert_(battle.has_started())

        # Still going, right?
        self.assertFalse(battle.past_end_time())

        # Skirmish 1
        s1 = battle.create_skirmish(self.alice, 10)  # Attack 10
        s1a = s1.react(self.carol, 4, hinder=False)  # --Support 4
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
        self.battle.ends = self.battle.begins
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
