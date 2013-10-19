# coding=utf-8

import unittest

import utils
from commands import *
from parser import parse


class TestMovement(unittest.TestCase):

    def testMoveCommand(self):
        src = 'lead 10 to "hurfendurf"'
        parsed = parse(src)

        self.assertIsInstance(parsed, MoveCommand)
        self.assertEqual(10, parsed.amount)
        self.assertEqual(parsed.where[0], "hurfendurf")

    def testMoveSubreddit(self):
        src = 'lead 10 to /r/hurfendurf'
        parsed = parse(src)

        self.assertIsInstance(parsed, MoveCommand)
        self.assertEqual(10, parsed.amount)
        self.assertEqual(parsed.where[0], "hurfendurf")

    def testMovePlain(self):
        src = "lead 10 to hurfendurf"

        parsed = parse(src)
        self.assertIsInstance(parsed, MoveCommand)
        self.assertEqual(10, parsed.amount)
        self.assertEqual(parsed.where[0], "hurfendurf")

    def test_move_all(self):
        src = "lead all to hurfendurf"
        parsed = parse(src)

        self.assertIsInstance(parsed, MoveCommand)
        self.assertEqual(-1, parsed.amount)
        self.assertEqual(parsed.where[0], "hurfendurf")

    def test_move_implied_all(self):
        src = "lead to hurfendurf"
        parsed = parse(src)

        self.assertIsInstance(parsed, MoveCommand)
        self.assertEqual(-1, parsed.amount)
        self.assertEqual(parsed.where[0], "hurfendurf")

    def test_multimove(self):
        src = "lead all to wergland, /r/testplace, somewhereelse"
        parsed = parse(src)

        self.assertIsInstance(parsed, MoveCommand)
        self.assertEqual(-1, parsed.amount)
        self.assertEqual(parsed.where,
                         ["wergland", 'testplace', 'somewhereelse'])


class TestBattle(unittest.TestCase):

    def test_invade_command(self):
        src = "invade hurfendurf"
        parsed = parse(src)

        self.assertIsInstance(parsed, InvadeCommand)
        self.assertEqual(parsed.where, "hurfendurf")

    def test_skirmish(self):
        src = "attack with 30"
        parsed = parse(src)
        self.assertIsInstance(parsed, SkirmishCommand)
        self.assertEqual(parsed.action, "attack")
        self.assertEqual(parsed.amount, 30)
        self.assertEqual(parsed.troop_type, "infantry")

    def test_attack_with_type(self):
        src = "attack with 30 ranged"
        parsed = parse(src)
        self.assertIsInstance(parsed, SkirmishCommand)
        self.assertEqual(parsed.action, "attack")
        self.assertEqual(parsed.amount, 30)
        self.assertEqual(parsed.troop_type, "ranged")

    def test_attack_with_bad_type(self):
        src = "attack with 30 muppet"
        parsed = parse(src)
        self.assertIsInstance(parsed, SkirmishCommand)
        self.assertEqual(parsed.action, "attack")
        self.assertEqual(parsed.amount, 30)
        self.assertEqual(parsed.troop_type, "muppet")

    def test_attack_with_codeword(self):
        src = "attack with 30 copies of my college thesis"
        parsed = parse(src)
        self.assertIsInstance(parsed, SkirmishCommand)
        self.assertEqual(parsed.action, "attack")
        self.assertEqual(parsed.amount, 30)
        self.assertEqual(parsed.troop_type, "copies of my college thesis")

    def test_support(self):
        src = "support with 30"
        parsed = parse(src)
        self.assertIsInstance(parsed, SkirmishCommand)
        self.assertEqual(parsed.action, "support")
        self.assertEqual(parsed.amount, 30)

    def test_oppose(self):
        src = "oppose with 30"
        parsed = parse(src)

        self.assertIsInstance(parsed, SkirmishCommand)
        self.assertEqual(parsed.action, "attack")
        self.assertEqual(parsed.amount, 30)

    def test_targeted(self):
        src = "support #7 with 30"
        parsed = parse(src)

        self.assertIsInstance(parsed, SkirmishCommand)
        self.assertEqual(parsed.action, "support")
        self.assertEqual(parsed.amount, 30)
        self.assertEqual(parsed.target, 7)

    def test_misspellings(self):
        """Common mis-spellings are aliased"""
        src = "attack with 30 range"
        parsed = parse(src)

        self.assertEqual(parsed.action, "attack")
        self.assertEqual(parsed.amount, 30)
        self.assertEqual(parsed.troop_type, "ranged")

        src = "attack with 30 calvary"
        parsed = parse(src)

        self.assertEqual(parsed.action, "attack")
        self.assertEqual(parsed.amount, 30)
        self.assertEqual(parsed.troop_type, "cavalry")

        src = "attack with 30 calvalry"
        parsed = parse(src)

        self.assertEqual(parsed.action, "attack")
        self.assertEqual(parsed.amount, 30)
        self.assertEqual(parsed.troop_type, "cavalry")


class TestCodeword(unittest.TestCase):
    def testBasicCodeword(self):
        src = 'codeword "barf" is infantry'
        parsed = parse(src)
        self.assertIsInstance(parsed, CodewordCommand)
        self.assertFalse(parsed.remove)
        self.assertFalse(parsed.status)
        self.assertEqual(parsed.code, 'barf')
        self.assertEqual(parsed.word, "infantry")

    def testBiggerCodeword(self):
        src = 'codeword "hello, world!" is ranged'
        parsed = parse(src)
        self.assertIsInstance(parsed, CodewordCommand)
        self.assertEqual(parsed.code, 'hello, world!')
        self.assertEqual(parsed.word, "ranged")

    def testUnicodeword(self):
        """See what I did there?"""
        src = u'codeword "ಠ_ಠ" is cavalry'
        parsed = parse(src)
        self.assertIsInstance(parsed, CodewordCommand)
        self.assertEqual(parsed.code, u'ಠ_ಠ')
        self.assertEqual(parsed.word, "cavalry")

    def testCodewordAliases(self):
        src = 'codeword "werg" is calvalry'
        parsed = parse(src)
        self.assertIsInstance(parsed, CodewordCommand)
        self.assertEqual(parsed.code, 'werg')
        self.assertEqual(parsed.word, "cavalry")

    def testRemoveCodeword(self):
        src = 'codeword remove "werg"'
        parsed = parse(src)
        self.assertIsInstance(parsed, CodewordCommand)
        self.assertEqual(parsed.code, 'werg')
        self.assert_(parsed.remove)
        self.assertFalse(parsed.all)

    def testRemoveAllCodeword(self):
        src = 'codeword remove all'
        parsed = parse(src)
        self.assertIsInstance(parsed, CodewordCommand)
        self.assert_(parsed.remove)
        self.assert_(parsed.all)

    def testCodewordStatus(self):
        src = 'codeword status'
        parsed = parse(src)
        self.assertIsInstance(parsed, CodewordCommand)
        self.assert_(parsed.status)


class TestStatus(unittest.TestCase):
    def testStatusCommand(self):
        src = 'status'
        parsed = parse(src)
        self.assertIsInstance(parsed, StatusCommand)


class TestPromotion(unittest.TestCase):
    def testPromoteCommand(self):
        src = 'promote hurfendurf'
        parsed = parse(src)
        self.assertIsInstance(parsed, PromoteCommand)
        self.assertEqual(parsed.who, "hurfendurf")
        self.assertEqual(parsed.direction, 1)

    def testMixedCasePromote(self):
        src = 'promote HurfenDurf'
        parsed = parse(src)
        self.assertIsInstance(parsed, PromoteCommand)
        self.assertEqual(parsed.who, "HurfenDurf")
        self.assertEqual(parsed.direction, 1)

    def testDemoteCommand(self):
        src = "demote hurfendurf"
        parsed = parse(src)
        self.assertIsInstance(parsed, PromoteCommand)
        self.assertEqual(parsed.who, "hurfendurf")
        self.assertEqual(parsed.direction, 0)

    def testMixedCaseDemote(self):
        src = "demote HurfenDurf"
        parsed = parse(src)
        self.assertIsInstance(parsed, PromoteCommand)
        self.assertEqual(parsed.who, "HurfenDurf")
        self.assertEqual(parsed.direction, 0)


class TestCommandExtraction(unittest.TestCase):

    def goodparse(self, text):
        cmd = utils.extract_command(text)
        self.assertEqual("status", cmd)

    def badparse(self, text):
        cmd = utils.extract_command(text)
        self.assertEqual(None, cmd)

    def test_full_embed(self):
        text = ("Hello, world!  Today I intend to\n\n"
                "&gt; status\n\n"
                "among other things!")
        self.goodparse(text)

    def test_alone(self):
        text = "&gt; status"
        self.goodparse(text)

    def test_beginning(self):
        text = ("&gt; status\n\n"
                "I wonder how things are?")
        self.goodparse(text)

    def test_end(self):
        text = ("And now, more stuff\n\n"
                "&gt; status")
        self.goodparse(text)

    def test_bad_inline(self):
        text = "here's an inline &gt; status thingie"
        self.badparse(text)

    def test_singlecrlf(self):
        text = "here's an inline \n&gt; status\n thingie"
        self.goodparse(text)


class TestDefection(unittest.TestCase):
    def test_basic_defect(self):
        text = "defect"
        parsed = parse(text)

        self.assertIsInstance(parsed, DefectCommand)
        self.assertEqual(None, parsed.team)

    def test_specific_defect(self):
        text = "defect to periwinkle"
        parsed = parse(text)

        self.assertIsInstance(parsed, DefectCommand)
        self.assertEqual(parsed.team, 1)

if __name__ == '__main__':
    unittest.main()
