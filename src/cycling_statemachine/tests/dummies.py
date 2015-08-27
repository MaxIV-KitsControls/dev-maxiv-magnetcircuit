import math

class DummyPS:

    def __init__(self, p0=0):
        self.value = 0.0
        self.moving = False

    def getValue(self):
        return self.value

    def setValue(self,data):
        self.moving = True
        self.value = data

    def isMoving(self):
        return self.moving

    def isOn(self):
        return not self.moving
