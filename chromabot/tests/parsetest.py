import unittest

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

    def testInvadeCommand(self):
        src = "invade hurfendurf"
        parsed = parse(src)

        self.assertIsInstance(parsed, InvadeCommand)
        self.assertEqual(parsed.where, "hurfendurf")


class TestStatus(unittest.TestCase):
    def testStatusCommand(self):
        src = 'status'
        parsed = parse(src)
        self.assertIsInstance(parsed, StatusCommand)

if __name__ == '__main__':
    unittest.main()
