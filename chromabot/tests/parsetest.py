import unittest

from commands import StatusCommand
from parser import parse


class TestMovement(unittest.TestCase):

    def testMoveCommand(self):
        src = 'move 10 to "hurfendurf"'
        parsed = parse(src)

        print parsed


class TestStatus(unittest.TestCase):
    def testStatusCommand(self):
        src = 'status'
        parsed = parse(src)
        self.assertIsInstance(parsed, StatusCommand)
        from pprint import pprint
        pprint(vars(parsed))
        print parsed

if __name__ == '__main__':
    unittest.main()
