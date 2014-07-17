import time
import math

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


class DummyPS:

    def __init__(self):
        self.current = 2.5
        self._prog = []
        self.last = 0.0
        self.atEnd = False

    def getCurrent(self):
        print "getcurrent", len(self._prog)

        sum = 0.0
        for p in self._prog:
            try:
                now = next(p)
                sum += now
                self.last = sum
                print "now ", now
            except StopIteration as e:
                self._prog.remove(p)
                self.atEnd = True

        #self.current = sum(next(p) for p in self._prog)
        self.current = self.last
        print "current ", self.current
        return self.current

    def setCurrent(self,data):
        init = self.current
        self.atEnd = False
        #self._prog.append(ramp(init, data, 20))
        if len(self._prog)==0:
            self._prog.append(ramp(init, data, 20))
        else:
            self._prog[0]=ramp(init, data, 20)


    def On(self):
        print "switching on the PS"

    def isOn(self):
        return True
    
    def atEnd(self):
        return self.atEnd
