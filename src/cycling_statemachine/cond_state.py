import time

from state import StateMachine


class MagnetCycling(StateMachine):
    def __init__(self, powersupply,
                 current_hi, current_lo, wait, iterations_max, current_step,
                 ramp_time, steps, current_nom_percentage=0.9):
        self.powersupply = powersupply

        self.current_hi = current_hi
        self.current_lo = current_lo  # the end ramp current
        self.current_nom_percentage = current_nom_percentage  # nominal current is a percentage of the max current
        self.wait = wait  # time (s) to wait at max and min currents
        self.iterations = 0
        self.interations_max = iterations_max

        try:
            self.step_time = ramp_time / (steps - 1)  # increase/decrease current and wait
        except ZeroDivisionError:
            self.step_time = ramp_time

        # self.current_step = current_step  # current add/sub at each step
        self.current_step = round((current_hi - current_lo) / steps, 3)

        self.step_timeout = 0
        self.iterationstatus = " (" + str(self.iterations) + "/" + str(self.interations_max) + ")"

        def print_state_change(old, new):
            print("\t iter : %d %3.3f: %s -> %s" % (self.iterations,time.time(), old, new))

        states = ["INITIALISE",
                  "SET_STEP_LO",
                  "WAIT_STEP_LO",
                  "WAIT_LO",
                  "WAIT_STEP_HI",
                  "SET_STEP_HI",
                  "WAIT_HI",
                  "SET_STEP_NOM_CURRENT",
                  "WAIT_STEP_NOM_CURRENT",
                  "DONE"]

        StateMachine.__init__(self, states, on_state_change=print_state_change)

        def wait():
            self.set_timeout(self.wait)

        # def step_wait():
        #    self.set_step_timeout(self.step_wait)

        self.INITIALISE.when(lambda: self.powersupply.isOn()).goto(self.SET_STEP_LO)

        # decrease current by step
        self.SET_STEP_LO.set_action(self.ramp_to_min_current)
        self.SET_STEP_LO.when(lambda: self.powersupply.isMoving() == False and self.is_low_current() == False).goto(
            self.WAIT_STEP_LO)
        self.SET_STEP_LO.when(lambda: self.powersupply.isMoving() == False and self.is_low_current()).goto(self.WAIT_LO)

        # waiting state between two current decreasing state
        # self.WAIT_STEP_LO.set_action(step_wait)
        self.WAIT_STEP_LO.when(lambda: time.time() >= self.step_timeout).goto(self.SET_STEP_LO)

        # waiting state when current is at minimum value
        self.WAIT_LO.set_action(wait)
        self.WAIT_LO.when(lambda: time.time() >= self.timeout).goto(self.SET_STEP_HI)

        # increase current by step
        self.SET_STEP_HI.set_action(self.ramp_to_max_current)
        self.SET_STEP_HI.when(lambda: self.powersupply.isMoving() == False and self.is_high_current() == False).goto(
            self.WAIT_STEP_HI)
        self.SET_STEP_HI.when(lambda: self.powersupply.isMoving() == False and self.is_high_current()).goto(
            self.WAIT_HI)

        # waiting state between two current increasing state
        # self.WAIT_STEP_HI.set_action(step_wait)
        self.WAIT_STEP_HI.when(lambda: time.time() >= self.step_timeout).goto(self.SET_STEP_HI)

        # waiting state when current is at maximum value
        self.WAIT_HI.set_action(wait)
        self.WAIT_HI.when(lambda: time.time() >= self.timeout and self.iterations == self.interations_max).goto(
            self.SET_STEP_NOM_CURRENT)
        self.WAIT_HI.when(lambda: time.time() >= self.timeout and self.iterations < self.interations_max).goto(
            self.SET_STEP_LO)

        # decrese current to nominal state
        self.SET_STEP_NOM_CURRENT.set_action(self.ramp_to_nom_current)
        self.SET_STEP_NOM_CURRENT.when(
            lambda: self.powersupply.isMoving() == False and self.is_nom_current() == False).goto(
            self.WAIT_STEP_NOM_CURRENT)
        self.SET_STEP_NOM_CURRENT.when(lambda: self.powersupply.isMoving() == False and self.is_nom_current()).goto(
            self.DONE)

        # waiting state between two current decreasing state
        # self.WAIT_STEP_NOM_CURRENT.set_action(step_wait)
        self.WAIT_STEP_NOM_CURRENT.when(lambda: time.time() >= self.step_timeout).goto(self.SET_STEP_NOM_CURRENT)

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

    def ramp_to_max_current(self):
        self.set_step_timeout(self.step_time)
        current = round(self.current(), 3)
        if round(self.current_hi - current, 3) > self.current_step:
            self.powersupply.setCurrent(current + self.current_step)
        else:
            self.powersupply.setCurrent(self.current_hi)
            self.iterations = self.iterations + 1
            self.iterationstatus = " (" + str(self.iterations) + "/" + str(self.interations_max) + ")"

    def ramp_to_min_current(self):
        self.set_step_timeout(self.step_time)
        current = round(self.current(), 3)
        if round(current - self.current_lo) > self.current_step:
            self.powersupply.setCurrent(current - self.current_step)
        else:
            self.powersupply.setCurrent(self.current_lo)

    def ramp_to_nom_current(self):
        self.set_step_timeout(self.step_time)
        current = round(self.current(), 3)
        nom_current = self.get_nom_current()
        if current > self.get_nom_current():
            if round(current - nom_current, 3) > self.current_step:
                self.powersupply.setCurrent(current - self.current_step)
            else:
                self.powersupply.setCurrent(nom_current)

        else:
            if round(nom_current - current, 3) > self.current_step:
                self.powersupply.setCurrent(current + self.current_step)
            else:
                self.powersupply.setCurrent(nom_current)
