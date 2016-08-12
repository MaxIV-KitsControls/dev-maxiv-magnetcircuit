import unittest

from mock import Mock
from cycling_statemachine import magnetcycling
from time import sleep
from PyTango import DevFailed
CURRENT_STEP = 1.2
RAMP_TIME = 1.3
STEPS = 10
LOOP = 0.001


class MagnetCyclingStateMachineTestCase(unittest.TestCase):

    def setUp(self):
        magnetcycling.ConditioningState = self.ConditioningState = Mock()
        self.statemachine = self.ConditioningState.return_value
        self.statemachine.state = ''
        self.statemachine.iterationstatus = ''
        self.statemachine.finished = False
        self.statemachine.__nonzero__ = lambda self: False
        args = Mock('powersupply'), 10, -10, 5, 4,  RAMP_TIME, STEPS
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
        err_msg = "present phase: {}, expected phase: {}"
        expected = "NOT CYCLING (limits are -10 10 A)"
        present = self.magnetcycling.phase
        self.assertEqual(present, expected, err_msg.format(present, expected))
        self.statemachine.__nonzero__ = lambda self: True
        self.statemachine.state = "State"
        self.statemachine.iterationstatus = "Iteration status"
        expected = self.statemachine.state + self.statemachine.iterationstatus
        present = self.magnetcycling.phase
        self.assertEqual(present, expected, err_msg.format(present, expected))

    def test_ramp_time(self):
        " r/w in attribute wait_step. "
        err_msg = "present ramp_time: {}, expected ramp_time: {}"
        present = self.magnetcycling.ramp_time
        self.assertEqual(present, RAMP_TIME, err_msg.format(present, RAMP_TIME))
        value = 3
        self.magnetcycling.ramp_time = 3
        present = self.magnetcycling.ramp_time
        self.assertEqual(present, value, err_msg.format(present, value))

    def test_steps(self):
        " r/w in attribute wait_step. "
        err_msg = "present steps: {}, expected steps: {}"
        present = self.magnetcycling.steps
        self.assertEqual(present, STEPS, err_msg.format(present, STEPS))
        value = 3
        self.magnetcycling.steps = 3
        present = self.magnetcycling.steps
        self.assertEqual(present, value, err_msg.format(present, value))

    def test_cycling(self):
        " statemachine finished. "
        assert not self.magnetcycling.cycling_ended
        assert not self.magnetcycling.cycling_interrupted
        assert self.magnetcycling.cycling
        assert self.magnetcycling.cycling_thread.is_alive()
        self.statemachine.finished = True
        sleep(LOOP)
        assert self.magnetcycling.cycling_ended
        assert not self.magnetcycling.cycling_interrupted
        assert not self.magnetcycling.cycling_thread.is_alive()
        self.statemachine.finished = False
        self.magnetcycling.cycling = True
        # test interruption
        assert not self.magnetcycling.cycling_ended
        assert not self.magnetcycling.cycling_interrupted
        assert self.magnetcycling.cycling
        assert self.magnetcycling.cycling_thread.is_alive()
        self.magnetcycling.cycling = False
        sleep(LOOP)
        assert not self.magnetcycling.cycling_ended
        assert self.magnetcycling.cycling_interrupted
        assert not self.magnetcycling.cycling_thread.is_alive()

    def test_exception(self):
        """ raise exception while looping """
        assert self.magnetcycling.cycling
        assert not self.magnetcycling.cycling_interrupted
        assert not self.magnetcycling.cycling_ended
        assert self.magnetcycling.cycling_thread.is_alive()
        self.statemachine.proceed.side_effect = DevFailed()
        sleep(LOOP)
        assert len(self.magnetcycling.error_stack) == 1
        assert self.magnetcycling.cycling_thread.is_alive()
        assert not self.magnetcycling.cycling_interrupted
        assert not self.magnetcycling.cycling_ended
        self.statemachine.proceed.side_effect = ZeroDivisionError()
        sleep(LOOP)
        assert len(self.magnetcycling.error_stack) == 2
        assert self.magnetcycling.cycling_interrupted
        assert not self.magnetcycling.cycling_ended
