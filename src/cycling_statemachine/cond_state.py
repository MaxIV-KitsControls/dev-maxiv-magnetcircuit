import time

from functools import partial
from state import StateMachine

POWER_SUPPLY_IS_ON_SLEEP = 10  # s


class MagnetCycling(StateMachine):
    def __init__(self, powersupply, hi_setpoint, lo_setpoint, wait,
                 iterations_max, ramp_time, steps,
                 nominal_setpoint_percentage=0.9, event=None):
        self.powersupply = powersupply
        self.event = event
        if event:
            self.sleep = event.wait
        else:
            self.sleep = time.sleep
        self.hi_setpoint = hi_setpoint
        self.lo_setpoint = lo_setpoint
        # nominal value is a percentage of the max value
        self.nominal_setpoint_percentage = nominal_setpoint_percentage
        self.wait = wait  # time (s) to wait at max and min
        self.iterations = 0
        self.interations_max = iterations_max
        self.ref_time = 0
        try:
            # increase/decrease value and wait
            self.step_time = ramp_time / (steps - 1)
        except ZeroDivisionError:
            self.step_time = ramp_time
        self.setpoint_step = round((hi_setpoint - lo_setpoint) / steps, 3)
        self.step_timeout = 0
        self.iterationstatus = " (" + str(self.iterations) + "/"
        self.iterationstatus += str(self.interations_max) + ")"
        # Define state
        states = ["INITIALISE",
                  "SET_STEP_LO",
                  "WAIT_LO",
                  "SET_STEP_HI",
                  "WAIT_HI",
                  "SET_STEP_NOM_VALUE",
                  "DONE"]
        # Setup state machine
        StateMachine.__init__(self, states)
        # Setup State rules
        self._setup_states()

    def _setup_states(self):
        self._setup_init_state()
        self._setup_setlo_state()
        self._setup_waitlo_state()
        self._setup_stephi_state()
        self._setup_waithi_state()
        self._setup_stepnom_state()

    def _setup_init_state(self):
        # INITIALISE State
        nx_state = self.SET_STEP_LO
        self.INITIALISE.when(self.check_power_supply_state).goto(nx_state)

    def _setup_setlo_state(self):
        # SET_STEP_LO State
        # Decrease value by step
        self.SET_STEP_LO.set_action(self.init_ramp_to_min_value)
        # Decrease value at each step
        self.SET_STEP_LO.set_recurring_action(self.ramp_to_min_value)
        # Loop on this state condition
        loop_in = partial(
            self.is_step_finished,
            lambda: not self.powersupply.isMoving() and not self.is_low_value())
        self.SET_STEP_LO.when(loop_in).goto(self.SET_STEP_LO)
        # Go to the next state
        go_next = partial(
            self.is_step_finished,
            lambda: not self.powersupply.isMoving() and self.is_low_value())
        self.SET_STEP_LO.when(go_next).goto(self.WAIT_LO)

    def _setup_waitlo_state(self):
        # Waiting state when value is at minimum value
        self.WAIT_LO.when(lambda: not self.is_interupted()).do(
            self.sleep, self.wait).goto(self.SET_STEP_HI)

    def _setup_stephi_state(self):
        # Increase value by step
        self.SET_STEP_HI.set_action(self.init_ramp_to_max_value)
        self.SET_STEP_HI.set_recurring_action(self.ramp_to_max_value)
        loop_in = partial(
            self.is_step_finished,
            lambda: not self.powersupply.isMoving() and not self.is_high_value()
        )
        self.SET_STEP_HI.when(loop_in).goto(self.SET_STEP_HI)
        go_next = partial(
            self.is_step_finished,
            lambda: not self.powersupply.isMoving() and self.is_high_value())
        self.SET_STEP_HI.when(go_next).goto(self.WAIT_HI)

    def _setup_waithi_state(self):
        self.WAIT_HI.set_action(self.increase_interation)
        # End cycling
        end_cycling = partial(
            self.is_step_finished,
            lambda: self.iterations >= self.interations_max)
        self.WAIT_HI.when(end_cycling).do(self.sleep, self.wait).goto(
            self.SET_STEP_NOM_VALUE)
        # New cycle
        continue_cycle = partial(
            self.is_step_finished,
            lambda: self.iterations < self.interations_max)
        self.WAIT_HI.when(continue_cycle).do(self.sleep, self.wait).goto(
            self.SET_STEP_LO)

    def _setup_stepnom_state(self):
        # decrese value to nominal state
        self.SET_STEP_NOM_VALUE.set_action(self.init_ramp_to_nom_value)
        self.SET_STEP_NOM_VALUE.set_recurring_action(self.ramp_to_nom_value)
        loop_in = partial(self.is_step_finished,
                          lambda: not self.powersupply.isMoving() and
                          not self.is_nom_value())
        self.SET_STEP_NOM_VALUE.when(loop_in).goto(self.SET_STEP_NOM_VALUE)
        done = partial(
            self.is_step_finished,
            lambda: not self.powersupply.isMoving() and self.is_nom_value())
        self.SET_STEP_NOM_VALUE.when(done).goto(self.DONE)

    def increase_interation(self):
        self.iterations += 1
        self.iterationstatus = " (" + str(self.iterations)
        self.iterationstatus += "/" + str(self.interations_max) + ")"

    def check_power_supply_state(self):
        ps_is_on = self.powersupply.isOn()
        if not ps_is_on:
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
        # Negative current and negative percentage.
        if self.nominal_setpoint_percentage < 0 and self.lo_setpoint < 0:
            return self.lo_setpoint * abs(self.nominal_setpoint_percentage)
        else:
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
        if round(self.hi_setpoint - value, 3) > self.setpoint_step and \
                value + self.setpoint_step < self.hi_setpoint:
            self.powersupply.setValue(value + self.setpoint_step)
            self.sleep_step()
        else:
            self.powersupply.setValue(self.hi_setpoint)

    def init_ramp_to_min_value(self):
        self.ref_time = time.time()
        self.ramp_to_min_value()

    def ramp_to_min_value(self):
        value = round(self.get_actual_value(), 3)
        if round(value - self.lo_setpoint, 3) > self.setpoint_step and \
                value - self.setpoint_step > self.lo_setpoint:
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
