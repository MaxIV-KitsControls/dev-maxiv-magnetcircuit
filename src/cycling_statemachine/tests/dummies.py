import math

class DummyPS:

    def __init__(self, p0=0):
        self.current = 0.0
        self.moving = False

    def getCurrent(self):

        return self.current

    def setCurrent(self,data):
        self.moving = True
        self.current = data
        self.moving = False

    def isMoving(self):
        return self.moving

    def isOn(self):
        return not self.moving
