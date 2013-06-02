import unittest

from db import DB, InsufficientException, NonAdjacentException, Region, User


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
        "connections": ["Ameythest Cove", "Torquois Moors"]
    },
    {
        "name": "Torquois Moors",
        "srname": "ct_fortiris",
        "connections": ["Snooland"]
    },
    {
        "name": "Ameythest Cove",
        "srname": "ct_amethestcove",
        "connections": ["Snooland"]
    },
    {
        "name": "Snooland",
        "srname": "ct_snooland",
        "connections": ["Aegis", "Novum Persarum"]
    },
    {
        "name": "Aegis",
        "srname": "ct_aegis",
        "connections": ["Orange Londo"]
    },
    {
        "name": "Novum Persarum",
        "srname": "ct_novumpersarum",
        "connections": ["Orange Londo"]
    },
    {
        "name": "Orange Londo",
        "srname": "ct_orangelondo",
        "connections": ["Oraistedarg"]
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


class TestPlaying(unittest.TestCase):

    def setUp(self):
        conf = MockConf(dbstring="sqlite://")
        self.db = DB(conf)
        self.db.create_all()
        self.sess = self.db.session()
        # And we will call it... this land
        self.sess.add_all(Region.create_from_json(TEST_LANDS))

        self.sess.commit()
        # Create some users
        self.alice = self.create_user("alice", 0)

    def create_user(self, name, team):
        newbie = User(name=name, team=team, loyalists=100)
        self.sess.add(newbie)
        cap = Region.capital_for(team, self.sess)
        newbie.region = cap
        self.sess.commit()
        return newbie

    def get_region(self, name):
        region = self.sess.query(Region).filter_by(name=name).first()
        return region

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

    def test_disallow_overdraw_movement(self):
        """Make sure you can't move more people than you have"""
        londo = self.get_region("Orange Londo")
        old = self.alice.region

        with self.assertRaises(InsufficientException):
            self.alice.move(10000, londo, 0)

        # She should still be home
        self.assertEqual(self.alice.region.id, old.id)

    def test_disallow_nonadjacent_movement(self):
        """Make sure you can't move to somewhere that's not next to you"""
        old = self.alice.region
        pericap = self.get_region("Periopolis")

        with self.assertRaises(NonAdjacentException):
            # Strike instantly at the heart of the enemy!
            self.alice.move(100, pericap, 0)

        # Actually, no, nevermind, let's stay home
        self.assertEqual(self.alice.region.id, old.id)

if __name__ == '__main__':
    unittest.main()
