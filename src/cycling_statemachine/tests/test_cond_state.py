from random import random
import time
from time import sleep
import unittest

from cycling_statemachine.cond_state import MagnetCycling

from dummies import DummyPS

from mock import patch

CURRENT_HI = 5
CURRENT_LO = 0
WAIT = 5
ITERATIONS = 3

STEP_TIME = 1.  # s
STEP_CURRENT = 0.5


class MagnetCyclingStateMachineTestCase(unittest.TestCase):
    """Detailed tests for the state machine, focusing on one or a few state changes."""

    def setUp(self):
        self.powersupply = DummyPS()

        self.cycling = MagnetCycling(
            self.powersupply,
            current_hi=CURRENT_HI, current_lo=CURRENT_LO,
            wait=WAIT, iterations_max=ITERATIONS,
            step_wait=STEP_TIME, current_step=STEP_CURRENT)

    # use this in main tests below to check state is as expected
    def assertState(self, expected):
        present = self.cycling.state
        self.assertEqual(present, expected,
                         "present state: %s, expected state: %s" % (present, expected))

    # use this in main tests below to check current value is as expected
    def assertCurrent(self, expected):
        present = self.powersupply.getCurrent()
        self.assertEqual(present, expected,
                         "present current: %s, expected current: %s" % (present, expected))

    def test_decrease_current(self):
        "reduce current with minimal value using ramp."
        start_current = 2.7
        with patch("time.time") as mock_time:
            # start with initial current
            self.powersupply.setCurrent(start_current)
            mock_time.return_value = 0.
            self.cycling.state = "SET_STEP_LO"
            self.cycling.proceed()
            self.assertCurrent(start_current - STEP_CURRENT)
            self.assertState("WAIT_STEP_LO")

            # wait less than a ramp wait time
            mock_time.return_value += STEP_TIME / 2
            self.cycling.proceed()
            self.assertCurrent(start_current - STEP_CURRENT)
            self.assertState("WAIT_STEP_LO")

            # pass a normal ramp time
            mock_time.return_value += STEP_TIME / 2
            self.cycling.proceed()
            self.assertCurrent(start_current - 2 * STEP_CURRENT)
            self.assertState("WAIT_STEP_LO")

            # set current near goal value and step time
            self.powersupply.setCurrent(CURRENT_LO + (STEP_CURRENT / 2))
            mock_time.return_value += STEP_TIME
            self.cycling.proceed()
            self.assertCurrent(CURRENT_LO)
            self.assertState("WAIT_LO")

    def test_increase_current(self):
        "increase current to max value using ramp."
        with patch("time.time") as mock_time:
            # start with minimal current
            self.powersupply.setCurrent(CURRENT_LO)
            mock_time.return_value = 0.
            self.cycling.state = "SET_STEP_HI"
            self.cycling.proceed()
            self.assertCurrent(CURRENT_LO + STEP_CURRENT)
            self.assertState("WAIT_STEP_HI")

            # wait less than a ramp wait time
            mock_time.return_value += STEP_TIME / 2
            self.cycling.proceed()
            self.assertCurrent(CURRENT_LO + STEP_CURRENT)
            self.assertState("WAIT_STEP_HI")

            # pass a normal ramp time
            mock_time.return_value += STEP_TIME / 2
            self.cycling.proceed()
            self.assertCurrent(CURRENT_LO + 2 * STEP_CURRENT)
            self.assertState("WAIT_STEP_HI")

            # set current near goal value and step time
            self.powersupply.setCurrent(CURRENT_HI - (STEP_CURRENT / 2))
            mock_time.return_value += STEP_TIME
            self.cycling.proceed()
            self.assertCurrent(CURRENT_HI)
            self.assertState("WAIT_HI")

    def test_increase_to_nominal_current(self):
        "increase current to nominal value using ramp"
        with patch("time.time") as mock_time:
            # start with minimal current
            self.powersupply.setCurrent(CURRENT_LO)
            mock_time.return_value = 0.
            self.cycling.state = "SET_STEP_NOM_CURRENT"
            self.cycling.proceed()
            self.assertCurrent(CURRENT_LO + STEP_CURRENT)
            self.assertState("WAIT_STEP_NOM_CURRENT")

            # wait less than a ramp wait time
            mock_time.return_value += STEP_TIME / 2
            self.cycling.proceed()
            self.assertCurrent(CURRENT_LO + STEP_CURRENT)
            self.assertState("WAIT_STEP_NOM_CURRENT")

            # pass a normal ramp time
            mock_time.return_value += STEP_TIME / 2
            self.cycling.proceed()
            self.assertCurrent(CURRENT_LO + 2 * STEP_CURRENT)
            self.assertState("WAIT_STEP_NOM_CURRENT")

            # set current near goal value and step time
            self.powersupply.setCurrent(self.cycling.get_nom_current() - (STEP_CURRENT / 2))
            mock_time.return_value += STEP_TIME
            self.cycling.proceed()
            self.assertCurrent(self.cycling.get_nom_current())
            self.assertState("DONE")

    def test_decrease_to_nominal_current(self):
        "reduce current to nominal value using ramp."
        start_current = CURRENT_HI * 2
        with patch("time.time") as mock_time:
            self.powersupply.setCurrent(start_current)
            mock_time.return_value = 0.
            self.cycling.state = "SET_STEP_NOM_CURRENT"
            self.cycling.proceed()
            self.assertCurrent(start_current - STEP_CURRENT)
            self.assertState("WAIT_STEP_NOM_CURRENT")

            mock_time.return_value += STEP_TIME / 2
            self.cycling.proceed()
            self.assertCurrent(start_current - STEP_CURRENT)
            self.assertState("WAIT_STEP_NOM_CURRENT")

            mock_time.return_value += STEP_TIME / 2
            self.cycling.proceed()
            self.assertCurrent(start_current - 2 * STEP_CURRENT)
            self.assertState("WAIT_STEP_NOM_CURRENT")

            self.powersupply.setCurrent(self.cycling.get_nom_current() + (STEP_CURRENT / 2))
            mock_time.return_value += STEP_TIME
            self.cycling.proceed()
            self.assertCurrent(self.cycling.get_nom_current())
            self.assertState("DONE")

    def test_iteration_cycle(self):
        "cycle with iterations."
        start_current = 2.7
        with patch("time.time") as mock_time:
            # start with initial current
            self.powersupply.setCurrent(start_current)
            mock_time.return_value = 0.
            # start cycle
            self.cycling.state = "SET_STEP_LO"
            for iteration in range(0, ITERATIONS):
                # decrease current
                self.cycling.proceed()
                self.assertState("WAIT_STEP_LO")

                # set current at min value and run a step time
                mock_time.return_value += STEP_TIME
                self.powersupply.setCurrent(CURRENT_LO)
                self.cycling.proceed()
                self.assertCurrent(CURRENT_LO)
                self.assertState("WAIT_LO")

                # run a wait time
                mock_time.return_value += WAIT
                self.cycling.proceed()
                self.assertState("WAIT_STEP_HI")

                # increase current
                # set current at max value and run a step time
                mock_time.return_value += STEP_TIME
                self.powersupply.setCurrent(CURRENT_HI)
                self.cycling.proceed()
                self.assertCurrent(CURRENT_HI)
                self.assertState("WAIT_HI")
                # run a wait time
                mock_time.return_value += WAIT

            # cycle iterations done
            self.cycling.proceed()
            self.assertState("DONE")
            self.assertCurrent(self.cycling.get_nom_current())

if __name__ == '__main__':
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(unittest.makeSuite(MagnetCyclingTestCase))
