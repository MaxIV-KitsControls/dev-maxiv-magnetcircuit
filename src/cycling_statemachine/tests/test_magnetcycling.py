import unittest

from mock import Mock
from cycling_statemachine import magnetcycling
from time import sleep

DEFAULT_CURRENT_STEP = 1.2
DEFAULT_RAMP_TIME = 1.3
DEFAULT_STEPS = 10
LOOP = 1
class MagnetCyclingStateMachineTestCase(unittest.TestCase):
    def setUp(self):
        magnetcycling.ConditioningState = self.ConditioningState = Mock()
        self.statemachine = self.ConditioningState.return_value
        self.statemachine.state = ''
        self.statemachine.iterationstatus = ''
        self.statemachine.finished = False
        self.statemachine.__nonzero__ = lambda self: False
        args = Mock('powersupply'), 10, -10, 5, 4,  DEFAULT_RAMP_TIME, DEFAULT_STEPS
        self.magnetcycling = magnetcycling.MagnetCycling(*args)
        self.magnetcycling.cycling = True
        assert self.magnetcycling.cycling
        assert self.magnetcycling.cycling_thread.is_alive()

    def tearDown(self):
        self.magnetcycling.cycling = False
        assert not self.magnetcycling.cycling
        assert not self.magnetcycling.cycling_thread.is_alive()
        pass

    def test_phase(self):
        " read phase "
        expected = "NOT CYCLING (limits are -10 10 A)"
        present = self.magnetcycling.phase
        self.assertEqual(present, expected,
                         "present phase: %s, expected phase: %s" % (present, expected))

        self.statemachine.__nonzero__ = lambda self: True
        self.statemachine.state = "State"
        self.statemachine.iterationstatus = "Iteration status"
        expected = self.statemachine.state + self.statemachine.iterationstatus
        present = self.magnetcycling.phase
        self.assertEqual(present, expected,
                         "present phase: %s, expected phase: %s" % (present, expected))

    """def test_current_step(self):
        " r/w in attribute current_step. "
        present = self.magnetcycling.current_step
        self.assertEqual(present, DEFAULT_CURRENT_STEP,
                         "present current_step: %s, expected current_step: %s" % (present, DEFAULT_CURRENT_STEP))
        value = 4
        self.magnetcycling.current_step = 4
        present = self.magnetcycling.current_step
        self.assertEqual(present, value,
                         "present current_step: %s, expected current_step: %s" % (present, value))"""

    def test_ramp_time(self):
        " r/w in attribute wait_step. "
        present = self.magnetcycling.ramp_time
        self.assertEqual(present, DEFAULT_RAMP_TIME,
                         "present ramp_time: %s, expected ramp_time: %s" % (present, DEFAULT_RAMP_TIME))
        value = 3
        self.magnetcycling.ramp_time = 3
        present = self.magnetcycling.ramp_time
        self.assertEqual(present, value,
                         "present ramp_time: %s, expected ramp_time: %s" % (present, value))

    def test_steps(self):
        " r/w in attribute wait_step. "
        present = self.magnetcycling.steps
        self.assertEqual(present, DEFAULT_STEPS,
                         "present steps: %s, expected steps: %s" % (present, DEFAULT_STEPS))
        value = 3
        self.magnetcycling.steps = 3
        present = self.magnetcycling.steps
        self.assertEqual(present, value,
                         "present steps: %s, expected steps: %s" % (present, value))

    def test_cycling(self):
        " statemachine finished. "
        assert self.magnetcycling.cycling
        assert self.magnetcycling.cycling_thread.is_alive()
        self.statemachine.finished = True
        sleep(LOOP)
        assert not self.magnetcycling.cycling_thread.is_alive()
