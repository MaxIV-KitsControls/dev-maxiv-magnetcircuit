from contextlib import contextmanager
from timeit import default_timer as time
from PyTango import DevFailed
from threading import Thread, Event
from time import sleep
from cond_state import MagnetCycling as ConditioningState
from collections import deque

# Tick context


@contextmanager
def tick_context(value, sleep=sleep):
    """Generate a context that controls the duration of its execution."""
    start = time()
    yield
    sleep_time = start + value - time()
    if sleep_time > 0:
        sleep(sleep_time)


class MagnetCycling(object):

    def __init__(self, powersupply, hi_setpoint, lo_setpoint, wait,
                 iterations, ramp_time, steps,
                 nominal_setpoint_percentage=0.9,
                 unit="A"):
        self.ps = powersupply
        # Conditions
        self.hi_set_point = hi_setpoint
        self.lo_set_point = lo_setpoint
        self.nominal_setpoint_percentage = nominal_setpoint_percentage
        self.wait_time = wait
        self.iterations = iterations
        self.ramp_time = ramp_time
        self.steps = steps
        self.unit = unit
        # States
        self._conditioning = False
        # Cycling
        self.cycling_thread = None  # The conditioning thread
        self.cycling_stop = Event()  # Set when aborting.
        self.statemachine = None
        self.error_stack = deque(maxlen=10)

    @property
    def cycling(self):
        return self._cycling

    @cycling.setter
    def cycling(self, value):
        self._cycling = value
        if self._cycling:
            self.start()
        else:
            # Stop any action
            self.stop()

    @property
    def cycling_errors(self):
        return "/n".join(set(map(str, self.error_stack)))

    def start(self):
        self.stop()
        self.error_stack.clear()
        # Start the ramping
        self.cycling_stop.clear()
        self.statemachine = ConditioningState(
            powersupply=self.ps,
            hi_setpoint=self.hi_set_point,
            lo_setpoint=self.lo_set_point,
            wait=self.wait_time,
            iterations_max=self.iterations,
            ramp_time=self.ramp_time,
            steps=self.steps,
            nominal_setpoint_percentage=self.nominal_setpoint_percentage,
            event=self.cycling_stop)
        self.cycling_thread = Thread(target=self.ramp)
        self.cycling_thread.start()

    def stop(self):
        # Stop the conditioning thread
        self.cycling_stop.set()
        # Wait the end of the ramping thread
        if self.cycling_thread is not None:
            self.cycling_thread.join()

    @property
    def phase(self):
        """Get the 'phase' of the conditioning; a high-level state"""
        if not self.statemachine:
            return "NOT CYCLING (limits are %s %s %s)" % (
                self.lo_set_point, self.hi_set_point, self.unit)
        return (self.statemachine.state + self.statemachine.iterationstatus)

    def ramp(self, dt=0.001):
        """The main loop for one cycling run."""
        while not (self.statemachine.finished or self.cycling_stop.isSet()):
            with tick_context(dt, sleep=self.cycling_stop.wait):
                try:
                    self.statemachine.proceed()
                except DevFailed as e:
                    self.error_stack.append(e)
        self.statemachine = None
