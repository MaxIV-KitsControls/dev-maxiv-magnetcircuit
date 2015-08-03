from random import random
import time
from time import sleep
import unittest
from mock import Mock

from cycling_statemachine.cond_state import MagnetCycling

from dummies import DummyPS

from mock import patch

CURRENT_HI = 5.
CURRENT_LO = 0.
WAIT = 5
ITERATIONS = 3

RAMP_TIME = 10.  # s
STEPS = 10
STEP_TIME = RAMP_TIME / (STEPS - 1)  # s
STEP_CURRENT = round((CURRENT_HI - CURRENT_LO) / STEPS, 3)


class MagnetCyclingStateMachineTestCase(unittest.TestCase):
    """Detailed tests for the state machine, focusing on one or a few state changes."""

    def setUp(self):
        self.powersupply = DummyPS()
        self.event = Mock()

        self.cycling = MagnetCycling(
            self.powersupply,
            current_hi=CURRENT_HI, current_lo=CURRENT_LO,
            wait=WAIT, iterations_max=ITERATIONS,
            ramp_time=RAMP_TIME, steps=STEPS, current_step=STEP_CURRENT, event=self.event
        )

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

    def assertCalled(self, mock):
        assert mock.called
        mock.called = False

    def test_decrease_current(self):
        "reduce current with minimal value using ramp."
        start_current = 2.7
        self.event.isSet.return_value = False

        # start with initial current
        self.powersupply.current = start_current
        self.cycling.state = "SET_STEP_LO"

        # first step was proceed
        self.assertCurrent(start_current - STEP_CURRENT)
        self.assertState("SET_STEP_LO")
        self.assertCalled(self.event.wait)

        # PS still moving
        self.cycling.proceed()
        self.assertCurrent(start_current - STEP_CURRENT)
        self.assertState("SET_STEP_LO")
        assert not self.event.wait.called

        # proceed another step
        self.powersupply.moving = False
        self.cycling.proceed()
        self.assertCurrent(start_current - (2 * STEP_CURRENT))
        self.assertState("SET_STEP_LO")
        self.assertCalled(self.event.wait)

        # set current value at less than one step
        self.powersupply.moving = False
        self.powersupply.current = CURRENT_LO + (STEP_CURRENT / 2)
        self.cycling.proceed()
        self.assertState("SET_STEP_LO")
        self.assertCurrent(CURRENT_LO)
        assert not self.event.wait.called

        # set stop event
        self.powersupply.moving = False
        self.event.isSet.return_value = True
        self.cycling.proceed()
        self.assertState("SET_STEP_LO")
        self.assertCalled(self.event.isSet)

        # check wait low
        self.event.isSet.return_value = False
        self.cycling.proceed()
        ## check if wait was called, can not check WAIT_LO state
        self.assertCalled(self.event.wait)
        self.assertState("SET_STEP_HI")

    def test_increase_current(self):
        "increase current to max value using ramp."
        self.event.isSet.return_value = False

        # start with low current value
        self.powersupply.current = CURRENT_LO
        self.cycling.state = "SET_STEP_HI"

        # first step was proceed
        self.assertCurrent(CURRENT_LO + STEP_CURRENT)
        self.assertState("SET_STEP_HI")
        self.assertCalled(self.event.wait)

        # PS still moving
        self.cycling.proceed()
        self.assertCurrent(CURRENT_LO + STEP_CURRENT)
        self.assertState("SET_STEP_HI")
        assert not self.event.wait.called

        # proceed another step
        self.powersupply.moving = False
        self.cycling.proceed()
        self.assertCurrent(CURRENT_LO + (2 * STEP_CURRENT))
        self.assertState("SET_STEP_HI")
        self.assertCalled(self.event.wait)

        # set current value at less than one step value
        self.powersupply.moving = False
        self.powersupply.current = CURRENT_HI - (STEP_CURRENT / 2)
        self.cycling.proceed()
        self.assertState("SET_STEP_HI")
        self.assertCurrent(CURRENT_HI)
        assert not self.event.wait.called

        # set stop event
        self.powersupply.moving = False
        self.event.isSet.return_value = True
        self.cycling.proceed()
        self.assertState("SET_STEP_HI")
        self.assertCalled(self.event.isSet)

        # check wait high
        self.event.isSet.return_value = False
        self.cycling.proceed()
        # -> check if wait was called, can not check WAIT_HI state
        self.assertCalled(self.event.wait)
        self.assertState("SET_STEP_LO")

    def test_decrease_to_nominal_current(self):
        "reduce current to nominal value using ramp."
        start_current = CURRENT_HI * 2
        self.event.isSet.return_value = False

        # start with initial current very high
        self.powersupply.current = start_current
        self.cycling.state = "SET_STEP_NOM_CURRENT"

        # first step was proceed
        self.assertCurrent(start_current - STEP_CURRENT)
        self.assertState("SET_STEP_NOM_CURRENT")
        self.assertCalled(self.event.wait)

        # PS still moving
        self.cycling.proceed()
        self.assertCurrent(start_current - STEP_CURRENT)
        self.assertState("SET_STEP_NOM_CURRENT")
        assert not self.event.wait.called

        # proceed another step
        self.powersupply.moving = False
        self.cycling.proceed()
        self.assertCurrent(start_current - (2 * STEP_CURRENT))
        self.assertState("SET_STEP_NOM_CURRENT")
        self.assertCalled(self.event.wait)

        # set current value at less than one step
        self.powersupply.moving = False
        self.powersupply.current = (self.cycling.get_nom_current() + (STEP_CURRENT / 2))
        self.cycling.proceed()
        self.assertState("SET_STEP_NOM_CURRENT")
        self.assertCurrent(self.cycling.get_nom_current())
        assert not self.event.wait.called
        self.powersupply.moving = False
        self.cycling.proceed()
        self.assertState("DONE")

    def test_iteration_cycle(self):
        "cycle with iterations."
        start_current = 2.7
        self.event.isSet.return_value = False
        self.powersupply.setCurrent(start_current)
        self.cycling.state = "SET_STEP_LO"
        for iteration in range(0, ITERATIONS):
            # cycling is in decrease current steps
            self.assertState("SET_STEP_LO")
            self.powersupply.current = CURRENT_LO + (STEP_CURRENT / 2)
            self.powersupply.moving = False
            self.cycling.proceed()
            self.assertState("SET_STEP_LO")
            self.assertCurrent(CURRENT_LO)
            self.powersupply.moving = False
            self.cycling.proceed()

            # cycling is in increase current steps
            self.assertState("SET_STEP_HI")
            self.powersupply.current = CURRENT_HI - (STEP_CURRENT / 2)
            self.powersupply.moving = False
            self.cycling.proceed()
            self.assertState("SET_STEP_HI")
            self.assertCurrent(CURRENT_HI)
            self.powersupply.moving = False
            self.cycling.proceed()

        # iterations was done, go to nominal current
        self.assertState("SET_STEP_NOM_CURRENT")
        self.assertCurrent(self.cycling.get_nom_current())
        self.powersupply.moving = False
        self.cycling.proceed()
        self.assertState('DONE')


if __name__ == '__main__':
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(unittest.makeSuite(MagnetCyclingTestCase))
