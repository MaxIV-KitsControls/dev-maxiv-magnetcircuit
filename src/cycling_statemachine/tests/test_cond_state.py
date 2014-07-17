import sys
sys.path.append("../")

from random import random
import time
from time import sleep
import unittest

from cond_state import MagnetCycling
from mock import Mock, patch

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
        current = self.cycling.state
        self.assertEqual(current, expected,
                         "Current state: %s, expected state: %s" % (current, expected))

    def test_cycle(self):
        "ramp the current."

        START_CURRENT = 2.7

        with patch("time.time") as mock_time:

            self.powersupply.setCurrent(START_CURRENT)

            # 
            mock_time.return_value = 0.
            self.cycling.state = "SET_MIN_CURRENT"
            self.cycling.proceed()

            #wait for the current to reach zero
            mock_time.return_value = 21.
            self.assertState("WAIT")


if __name__ == '__main__':
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(unittest.makeSuite(MagnetCyclingTestCase))
