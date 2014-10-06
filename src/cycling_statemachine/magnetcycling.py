import time
from threading import Thread, Semaphore, Event
from threading import Lock
from time import sleep
from cond_state import MagnetCycling as ConditioningState


class MagnetCycling(object):

    def __init__(self, powersupply, hicurrent, locurrent, wait, iterations):

        self.ps = powersupply

        # Conditions
        self.hicurrent_set_point = hicurrent
        self.locurrent_set_point = locurrent
        self.wait_time  = wait
        self.iterations = iterations

        # States
        self._conditioning = False

        # Cycling
        self.cycling_thread = None  # The conditioning thread
        self.cycling_run = Event()  # Set while running.
        self.cycling_end_step = Event()  # Signal for the end of each step
        self.cycling_stop = Event()  # Set when aborting.
        self.cycling_done = Event()  # Set when done.

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

    def increase_current(self):
        self.powersupply.setCurrrent(voltage+dv)

    def start(self):
        # Start the ramping
        self.cycling_run.set()
        self.cycling_end_step.clear()
        self.cycling_stop.clear()
        self.cycling_done.clear()

        self.statemachine = ConditioningState(
            self.ps,
            self.hicurrent_set_point,
            self.locurrent_set_point,
            self.wait_time,
            self.iterations)

        self.cycling_thread = Thread(target=self.ramp)
        self.cycling_thread.start()

    #def pause(self):
    #    self.cycling_run.clear()

    #def resume(self):
    #    self.cycling_run.set()

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
            return "NOT CYCLING (limits are %s %s)"  % (self.locurrent_set_point, self.hicurrent_set_point)
        return (self.statemachine.state + self.statemachine.iterationstatus) 

    def ramp(self, dt=1.0):

        """The main loop for one cycling run."""

        while not (self.statemachine.finished or self.cycling_stop.isSet()):
            self.cycling_end_step.clear()
            self.statemachine.proceed()
            self.cycling_end_step.set()
            self.cycling_stop.wait(dt)  # Defines the period of the loop
            while not self.cycling_run.isSet():
                self.cycling_run.wait(1.0)  # Paused; do nothing
        self.cycling_done.set()
        self.statemachine = None
