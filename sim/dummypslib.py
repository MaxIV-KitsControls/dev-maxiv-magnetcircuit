"""

A "mock" Tango device that simulates a pressure on an ion pump
following a predetermined ramp pattern

"""

import math
from time import time
from threading import Thread, Lock
import PyTango


def ramp(v0, v1, dt):
    """A generator which will yield values corresponding to a linear
    "ramp" from v0 to v1 taking dt seconds. Thereafter it yields
    v1.
    """
        
    t0 = time()
    dv = (v1 - v0) / dt
    while time() <= t0 + dt:
        t = time() - t0
        yield v0 + t * dv
    raise StopIteration("stopped")

class DummyPSLib:

    def __init__(self, p0=0):
        self.current = 0.0
        self.voltage = 0.0
        self._prog = []
        self._progv = []
        self.last = 0.0
        self.moving = False

    def getCurrent(self):
        #        print "getcurrent", len(self._prog)

        sum = 0.0
        for p in self._prog:
            try:
                now = next(p)
                sum += now
                self.last = sum
                #print "now ", now
            except StopIteration as e:
                self._prog.remove(p)
                self.moving = False

        #self.current = sum(next(p) for p in self._prog)
        self.current = self.last
        #print "current ", self.current
        #print "moving ", self.moving
        return self.current

    def setCurrent(self,data):
        self.moving = True
        init = self.current
        #self._prog.append(ramp(init, data, 20))
        if len(self._prog)==0:
            self._prog.append(ramp(init, data, 3))
        else:
            self._prog[0]=ramp(init, data, 3)

    def getVoltage(self):
        #        print "getvoltage", len(self._prog)

        sum = 0.0
        for p in self._progv:
            try:
                now = next(p)
                sum += now
                self.last = sum
                #print "now ", now
            except StopIteration as e:
                self._progv.remove(p)
                self.moving = False

        #self.current = sum(next(p) for p in self._prog)
        self.voltage = self.last
        #print "current ", self.current
        #print "moving ", self.moving
        return self.voltage

    def setVoltage(self,data):
        self.moving = True
        init = self.voltage
        #self._prog.append(ramp(init, data, 20))
        if len(self._progv)==0:
            self._progv.append(ramp(init, data, 20))
        else:
            self._progv[0]=ramp(init, data, 20)

    def getMoving(self):
        return self.moving
