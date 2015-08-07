import time

from functools import partial
from state import StateMachine

POWER_SUPPLY_IS_ON_SLEEP = 10 # s

class MagnetCycling(StateMachine):
    def __init__(self, powersupply,
                 current_hi, current_lo, wait, iterations_max, current_step,
                 ramp_time, steps, current_nom_percentage=0.9, event=None):
        self.powersupply = powersupply
        self.event = event
        if event:
            self.sleep = event.wait
        else :
            self.sleep = time.sleep
        self.current_hi = current_hi
        self.current_lo = current_lo  # the end ramp current
        self.current_nom_percentage = current_nom_percentage  # nominal current is a percentage of the max current
        self.wait = wait  # time (s) to wait at max and min currents
        self.iterations = 0
        self.interations_max = iterations_max
        self.ref_time = 0
        try:
            self.step_time = ramp_time / (steps - 1)  # increase/decrease current and wait
        except ZeroDivisionError:
            self.step_time = ramp_time
        # self.current_step = current_step  # current add/sub at each step
        self.current_step = round((current_hi - current_lo) / steps, 3)
        self.step_timeout = 0
        self.iterationstatus = " (" + str(self.iterations) + "/" + str(self.interations_max) + ")"
        def print_state_change(old, new):
            print("\t iter : %d %3.3f: %s -> %s" % (self.iterations, time.time(), old, new))

        states = ["INITIALISE",
                  "SET_STEP_LO",
                  "WAIT_LO",
                  "SET_STEP_HI",
                  "WAIT_HI",
                  "SET_STEP_NOM_CURRENT",
                  "DONE"]

        StateMachine.__init__(self, states)

        self.INITIALISE.when(self.check_power_supply_state).goto(self.SET_STEP_LO)

        # decrease current by step
        self.SET_STEP_LO.set_action(self.init_ramp_to_min_current)
        self.SET_STEP_LO.set_recurring_action(self.ramp_to_min_current)
        self.SET_STEP_LO.when(partial(self.is_step_finished,lambda: not self.powersupply.isMoving() and not self.is_low_current())).goto(self.SET_STEP_LO)
        self.SET_STEP_LO.when(partial(self.is_step_finished,lambda: not self.powersupply.isMoving() and self.is_low_current())).goto(self.WAIT_LO)

        # waiting state when current is at minimum value
        self.WAIT_LO.when(lambda : not self.is_interupted()).do(self.sleep, self.wait).goto(self.SET_STEP_HI)

        # increase current by step
        self.SET_STEP_HI.set_action(self.init_ramp_to_max_current)
        self.SET_STEP_HI.set_recurring_action(self.ramp_to_max_current)
        self.SET_STEP_HI.when(partial(self.is_step_finished,lambda: not self.powersupply.isMoving() and not self.is_high_current())).goto(self.SET_STEP_HI)
        self.SET_STEP_HI.when(partial(self.is_step_finished,lambda: not self.powersupply.isMoving() and self.is_high_current())).goto(
            self.WAIT_HI)

        #self.WAIT_HI.set_action(set_ref_time)
        self.WAIT_HI.when(partial(self.is_step_finished,lambda: self.iterations == self.interations_max)).do(self.sleep, self.wait).goto(self.SET_STEP_NOM_CURRENT)
        self.WAIT_HI.when(partial(self.is_step_finished,lambda: self.iterations < self.interations_max)).do(self.sleep, self.wait).goto(self.SET_STEP_LO)

        # decrese current to nominal state
        self.SET_STEP_NOM_CURRENT.set_action(self.init_ramp_to_nom_current)
        self.SET_STEP_NOM_CURRENT.set_recurring_action(self.ramp_to_nom_current)
        self.SET_STEP_NOM_CURRENT.when(partial(self.is_step_finished, lambda: not self.powersupply.isMoving()  and not self.is_nom_current())).goto(self.SET_STEP_NOM_CURRENT)
        self.SET_STEP_NOM_CURRENT.when(partial(self.is_step_finished, lambda: not self.powersupply.isMoving() and self.is_nom_current())).goto(self.DONE)


    def check_power_supply_state(self):
        print self.powersupply.isOn()
        ps_is_on = self.powersupply.isOn()
        if ps_is_on == False:
            self.sleep(POWER_SUPPLY_IS_ON_SLEEP)
        return ps_is_on



    def is_step_finished(self, action):
        return not self.is_interupted() and action()


    def is_interupted(self):
        try :
            return self.event.isSet()
        except AttributeError:
            return False

    def sleep_step(self):
        dt = time.time() - self.ref_time
        self.sleep(self.step_time - dt)
        self.ref_time = time.time()


    def set_max_current(self):
        self.powersupply.setCurrent(self.current_hi)
        self.iterations = self.iterations + 1
        self.iterationstatus = " (" + str(self.iterations) + "/" + str(self.interations_max) + ")"
        return True

    def get_nom_current(self):
        return self.current_hi * self.current_nom_percentage

    def set_nom_current(self):
        self.powersupply.setCurrent(self.get_nom_current())
        return True

    def set_min_current(self):
        self.powersupply.setCurrent(self.current_lo)
        return True

    def current(self):
        return self.powersupply.getCurrent()

    def is_low_current(self):
        return self.current() == self.current_lo

    def is_high_current(self):
        return self.current() == self.current_hi

    def is_nom_current(self):
        return self.current() == self.get_nom_current()

    def set_timeout(self, dt):
        self.timeout = dt + time.time()

    def set_step_timeout(self, dt):
        self.step_timeout = dt + time.time()

    def init_ramp_to_max_current(self):
        self.ref_time = time.time()
        self.ramp_to_max_current()

    def ramp_to_max_current(self):
        current = round(self.current(), 3)
        if round(self.current_hi - current, 3) > self.current_step and current + self.current_step < self.current_hi:
            self.powersupply.setCurrent(current + self.current_step)
            self.sleep_step()
        else:
            self.powersupply.setCurrent(self.current_hi)
            self.iterations = self.iterations + 1
            self.iterationstatus = " (" + str(self.iterations) + "/" + str(self.interations_max) + ")"

    def init_ramp_to_min_current(self):
        self.ref_time = time.time()
        self.ramp_to_min_current()

    def ramp_to_min_current(self):
        current = round(self.current(), 3)
        if round(current - self.current_lo) > self.current_step and current - self.current_step > self.current_lo :
            self.powersupply.setCurrent(current - self.current_step)
            self.sleep_step()
        else:
            self.powersupply.setCurrent(self.current_lo)

    def init_ramp_to_nom_current(self):
        self.ref_time = time.time()
        self.ramp_to_nom_current()

    def ramp_to_nom_current(self):
        current = round(self.current(), 3)
        nom_current = self.get_nom_current()
        if current > self.get_nom_current():
            if round(current - nom_current, 3) > self.current_step:
                self.powersupply.setCurrent(current - self.current_step)
                self.sleep_step()
            else:
                self.powersupply.setCurrent(nom_current)
        else:
            if round(nom_current - current, 3) > self.current_step:
                self.powersupply.setCurrent(current + self.current_step)
                self.sleep_step()
            else:
                self.powersupply.setCurrent(nom_current)
