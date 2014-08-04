import time

from state import StateMachine


class MagnetCycling(StateMachine):

    def __init__(self, powersupply,
                 current_hi, current_lo, wait, iterations_max):

        self.powersupply = powersupply

        self.current_hi = current_hi
        self.current_lo = current_lo   # the end ramp current
        self.wait = wait   # time (s) to wait at max and min currents
        self.iterations = 0
        self.interations_max = iterations_max

        self.iterationstatus = " (" + str(self.iterations) + "/" + str(self.interations_max) + ")"

        def print_state_change(old, new):
            print("\t%3.3f: %s -> %s" % (time.time(), old, new))

        states = ["INITIALISE",
                  "SET_MIN_CURRENT", 
                  "WAIT_LO",
                  "SET_MAX_CURRENT", 
                  "WAIT_HI",
                  "SET_NOM_CURRENT", 
                  "DONE"]

        StateMachine.__init__(self, states, on_state_change=print_state_change)

        # need this below
        def wait():
            #print "in wait()", self.iterations, self.interations_max
            self.set_timeout(self.wait)

        # initial state - need PS to be on, then set current to zero
        self.INITIALISE.when(lambda: self.powersupply.isOn()).goto(self.SET_MIN_CURRENT)
        self.SET_MIN_CURRENT.set_action(self.set_min_current)

        #when reached zero (ie no longer moving) wait 5s
        self.SET_MIN_CURRENT.when(lambda: self.powersupply.isMoving() == False).goto(self.WAIT_LO)
        self.WAIT_LO.set_action(wait)

        #exit the lo wait by moving to the max current 
        self.WAIT_LO.when(lambda: time.time() >= self.timeout).goto(self.SET_MAX_CURRENT)
        self.SET_MAX_CURRENT.set_action(self.set_max_current)

        #exit hi wait by moving to min current or to nom current if done all iterations
        self.WAIT_HI.when(lambda: self.iterations == self.interations_max).goto(self.SET_NOM_CURRENT)
        self.WAIT_HI.when(lambda: time.time() >= self.timeout).goto(self.SET_MIN_CURRENT)
        self.SET_NOM_CURRENT.set_action(self.set_nom_current)
        self.SET_NOM_CURRENT.when(lambda: self.powersupply.isMoving() == False).goto(self.DONE)

        #when reached max (ie no longer moving) wait 5s
        self.SET_MAX_CURRENT.when(lambda: self.powersupply.isMoving() == False).goto(self.WAIT_HI)
        self.WAIT_HI.set_action(wait)




    def set_max_current(self):
        self.powersupply.setCurrent(self.current_hi)
        self.iterations = self.iterations + 1
        self.iterationstatus = " (" + str(self.iterations) + "/" + str(self.interations_max) + ")"
        return True

    def set_nom_current(self):
        self.powersupply.setCurrent(self.current_hi/1.1) 
        return True

    def set_min_current(self):
        self.powersupply.setCurrent(self.current_lo)
        return True

    #@cached_property(ttl=0.1)  # Prevent incessant polling... maybe?
    #def current(self):
    #    return self.powersupply.getCurrent()

    def set_timeout(self, dt):
        self.timeout = dt + time.time()
