import sys
sys.path.append("../")

from random import random
import time
from time import sleep
import unittest

from cond_state import MagnetCycling

from dummies import DummyPS

CURRENT_HI = 5
CURRENT_LO = 0
WAIT = 5
ITERATIONS = 4

class MagnetCyclingStateMachineTestCase(unittest.TestCase):

    """Detailed tests for the state machine, focusing on one or a few state changes."""

    def setUp(self):
        self.powersupply = DummyPS()

        self.cycling = MagnetCycling(
            self.powersupply, 
            current_hi=CURRENT_HI, current_lo=CURRENT_LO,
            wait=WAIT, iterations_max=ITERATIONS)


    #use this in main tests below to check state is as expected
    def assertState(self, expected):
        present = self.cycling.state
        self.assertEqual(present, expected,
                         "present state: %s, expected state: %s" % (present, expected))

    #use this in main tests below to check current value is as expected
    def assertCurrent(self, expected):
        present = self.powersupply.getCurrent()
        self.assertEqual(present, expected,
                         "present current: %s, expected current: %s" % (present, expected))



    def test_cycle(self):
        "ramp the current."

        START_CURRENT = 2.7
        self.powersupply.setCurrent(START_CURRENT)

        #put in set min current state
        self.cycling.state = "SET_MIN_CURRENT"

        #check current now at min
        self.assertCurrent(CURRENT_LO)

        #advance the state machine - should now be in wait state
        self.cycling.next()
        self.assertState("WAIT_LO")

        #now must wait before advancing again, then get to set max current
        time.sleep(6)
        self.cycling.next()
        self.assertState("SET_MAX_CURRENT")

        #advance the state machine - should now be in wait state
        self.cycling.next()
        self.assertState("WAIT_HI")
        self.assertCurrent(CURRENT_HI)


if __name__ == '__main__':
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(unittest.makeSuite(MagnetCyclingTestCase))
