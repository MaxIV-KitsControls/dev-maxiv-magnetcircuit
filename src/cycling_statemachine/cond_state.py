import time

from functools import partial
from state import StateMachine

POWER_SUPPLY_IS_ON_SLEEP = 10  # s


class MagnetCycling(StateMachine):
    def __init__(self, powersupply,
                 hi_setpoint, lo_setpoint, wait, iterations_max,
                 ramp_time, steps, nominal_setpoint_percentage=0.9, event=None):
        self.powersupply = powersupply
        self.event = event
        if event:
            self.sleep = event.wait
        else:
            self.sleep = time.sleep
        self.hi_setpoint = hi_setpoint
        self.lo_setpoint = lo_setpoint
        self.nominal_setpoint_percentage = nominal_setpoint_percentage  # nominal value is a percentage of the max value
        self.wait = wait  # time (s) to wait at max and min
        self.iterations = 0
        self.interations_max = iterations_max
        self.ref_time = 0
        try:
            self.step_time = ramp_time / (steps - 1)  # increase/decrease value and wait
        except ZeroDivisionError:
            self.step_time = ramp_time
        self.setpoint_step = round((hi_setpoint - lo_setpoint) / steps, 3)
        self.step_timeout = 0
        self.iterationstatus = " (" + str(self.iterations) + "/" + str(self.interations_max) + ")"

        def print_state_change(old, new):
            print("\t iter : %d %3.3f: %s -> %s" % (self.iterations, time.time(), old, new))

        states = ["INITIALISE",
                  "SET_STEP_LO",
                  "WAIT_LO",
                  "SET_STEP_HI",
                  "WAIT_HI",
                  "SET_STEP_NOM_VALUE",
                  "DONE"]

        StateMachine.__init__(self, states)

        self.INITIALISE.when(self.check_power_supply_state).goto(self.SET_STEP_LO)

        # decrease value by step
        self.SET_STEP_LO.set_action(self.init_ramp_to_min_value)
        self.SET_STEP_LO.set_recurring_action(self.ramp_to_min_value)
        self.SET_STEP_LO.when(
            partial(self.is_step_finished, lambda: not self.powersupply.isMoving() and not self.is_low_value())).goto(
            self.SET_STEP_LO)
        self.SET_STEP_LO.when(
            partial(self.is_step_finished, lambda: not self.powersupply.isMoving() and self.is_low_value())).goto(
            self.WAIT_LO)

        # waiting state when value is at minimum value
        self.WAIT_LO.when(lambda: not self.is_interupted()).do(self.sleep, self.wait).goto(self.SET_STEP_HI)

        # increase value by step
        self.SET_STEP_HI.set_action(self.init_ramp_to_max_value)
        self.SET_STEP_HI.set_recurring_action(self.ramp_to_max_value)
        self.SET_STEP_HI.when(
            partial(self.is_step_finished, lambda: not self.powersupply.isMoving() and not self.is_high_value())).goto(
            self.SET_STEP_HI)
        self.SET_STEP_HI.when(
            partial(self.is_step_finished, lambda: not self.powersupply.isMoving() and self.is_high_value())).goto(
            self.WAIT_HI)

        # self.WAIT_HI.set_action(set_ref_time)
        self.WAIT_HI.when(partial(self.is_step_finished, lambda: self.iterations == self.interations_max)).do(
            self.sleep, self.wait).goto(self.SET_STEP_NOM_VALUE)
        self.WAIT_HI.when(partial(self.is_step_finished, lambda: self.iterations < self.interations_max)).do(self.sleep,
                                                                                                             self.wait).goto(
            self.SET_STEP_LO)

        # decrese value to nominal state
        self.SET_STEP_NOM_VALUE.set_action(self.init_ramp_to_nom_value)
        self.SET_STEP_NOM_VALUE.set_recurring_action(self.ramp_to_nom_value)
        self.SET_STEP_NOM_VALUE.when(
            partial(self.is_step_finished, lambda: not self.powersupply.isMoving() and not self.is_nom_value())).goto(
            self.SET_STEP_NOM_VALUE)
        self.SET_STEP_NOM_VALUE.when(
            partial(self.is_step_finished, lambda: not self.powersupply.isMoving() and self.is_nom_value())).goto(
            self.DONE)

    def check_power_supply_state(self):
        print self.powersupply.isOn()
        ps_is_on = self.powersupply.isOn()
        if ps_is_on == False:
            self.sleep(POWER_SUPPLY_IS_ON_SLEEP)
        return ps_is_on

    def is_step_finished(self, action):
        return not self.is_interupted() and action()

    def is_interupted(self):
        try:
            return self.event.isSet()
        except AttributeError:
            return False

    def sleep_step(self):
        dt = time.time() - self.ref_time
        self.sleep(self.step_time - dt)
        self.ref_time = time.time()

    def get_nom_value(self):
        return self.hi_setpoint * self.nominal_setpoint_percentage

    def get_actual_value(self):
        return self.powersupply.getValue()

    def is_low_value(self):
        return self.get_actual_value() == self.lo_setpoint

    def is_high_value(self):
        return self.get_actual_value() == self.hi_setpoint

    def is_nom_value(self):
        return self.get_actual_value() == self.get_nom_value()

    def set_timeout(self, dt):
        self.timeout = dt + time.time()

    def set_step_timeout(self, dt):
        self.step_timeout = dt + time.time()

    def init_ramp_to_max_value(self):
        self.ref_time = time.time()
        self.ramp_to_max_value()

    def ramp_to_max_value(self):
        value = round(self.get_actual_value(), 3)
        if round(self.hi_setpoint - value, 3) > self.setpoint_step and value + self.setpoint_step < self.hi_setpoint:
            self.powersupply.setValue(value + self.setpoint_step)
            self.sleep_step()
        else:
            self.powersupply.setValue(self.hi_setpoint)
            self.iterations = self.iterations + 1
            self.iterationstatus = " (" + str(self.iterations) + "/" + str(self.interations_max) + ")"

    def init_ramp_to_min_value(self):
        self.ref_time = time.time()
        self.ramp_to_min_value()

    def ramp_to_min_value(self):
        value = round(self.get_actual_value(), 3)
        if round(value - self.lo_setpoint) > self.setpoint_step and value - self.setpoint_step > self.lo_setpoint:
            self.powersupply.setValue(value - self.setpoint_step)
            self.sleep_step()
        else:
            self.powersupply.setValue(self.lo_setpoint)

    def init_ramp_to_nom_value(self):
        self.ref_time = time.time()
        self.ramp_to_nom_value()

    def ramp_to_nom_value(self):
        value = round(self.get_actual_value(), 3)
        nom_value = self.get_nom_value()
        if value > self.get_nom_value():
            if round(value - nom_value, 3) > self.setpoint_step:
                self.powersupply.setValue(value - self.setpoint_step)
                self.sleep_step()
            else:
                self.powersupply.setValue(nom_value)
        else:
            if round(nom_value - value, 3) > self.setpoint_step:
                self.powersupply.setValue(value + self.setpoint_step)
                self.sleep_step()
            else:
                self.powersupply.setValue(nom_value)
