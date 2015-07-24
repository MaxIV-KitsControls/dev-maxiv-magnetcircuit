import time
from threading import Thread, Semaphore, Event
from threading import Lock
from time import sleep
from cond_state import MagnetCycling as ConditioningState


class MagnetCycling(object):
    def __init__(self, powersupply, hicurrent, locurrent, wait, iterations, current_step, ramp_time, steps,current_nom_percentage=0.9):
        self.ps = powersupply
        # Conditions
        self.hicurrent_set_point = hicurrent
        self.locurrent_set_point = locurrent
        self.current_nom_percentage = current_nom_percentage
        self.wait_time = wait
        self.iterations = iterations
        self.current_step = current_step
        self.ramp_time = ramp_time
        self.steps = steps
        # States
        self._conditioning = False
        # Cycling
        self.cycling_thread = None  # The conditioning thread
        self.cycling_stop = Event()  # Set when aborting.
        self.statemachine = None

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

    def start(self):
        # Start the ramping
        self.cycling_stop.clear()
        self.statemachine = ConditioningState(
            self.ps,
            self.hicurrent_set_point,
            self.locurrent_set_point,
            self.wait_time,
            self.iterations,
            self.current_step,
            self.ramp_time,
            self.steps,
            self.current_nom_percentage)
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
            return "NOT CYCLING (limits are %s %s A)" % (self.locurrent_set_point, self.hicurrent_set_point)
        return (self.statemachine.state + self.statemachine.iterationstatus)

    def ramp(self, dt=0.1):
        """The main loop for one cycling run."""
        while not (self.statemachine.finished or self.cycling_stop.isSet()):
            self.statemachine.proceed()
            self.cycling_stop.wait(dt)  # Defines the period of the loop
        self.statemachine = None

