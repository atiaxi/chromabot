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
        self.assertEqual(parsed.where, "hurfendurf")

    def testMoveSubreddit(self):
        src = 'lead 10 to /r/hurfendurf'
        parsed = parse(src)

        self.assertIsInstance(parsed, MoveCommand)
        self.assertEqual(10, parsed.amount)
        self.assertEqual(parsed.where, "hurfendurf")

    def testMovePlain(self):
        src = "lead 10 to hurfendurf"

        parsed = parse(src)
        self.assertIsInstance(parsed, MoveCommand)
        self.assertEqual(10, parsed.amount)
        self.assertEqual(parsed.where, "hurfendurf")

    def test_move_all(self):
        src = "lead all to hurfendurf"
        parsed = parse(src)

        self.assertIsInstance(parsed, MoveCommand)
        self.assertEqual(-1, parsed.amount)
        self.assertEqual(parsed.where, "hurfendurf")

    def test_move_implied_all(self):
        src = "lead to hurfendurf"
        parsed = parse(src)

        self.assertIsInstance(parsed, MoveCommand)
        self.assertEqual(-1, parsed.amount)
        self.assertEqual(parsed.where, "hurfendurf")


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
        self.assertEqual(parsed.troop_type, "infantry")

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


class TestStatus(unittest.TestCase):
    def testStatusCommand(self):
        src = 'status'
        parsed = parse(src)
        self.assertIsInstance(parsed, StatusCommand)


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
