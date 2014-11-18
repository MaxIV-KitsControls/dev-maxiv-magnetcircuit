"""Contains the tests for the TSP device server."""

# Imports
from functools import partial
from time import sleep
from mock import MagicMock

import PyTango

import Magnet

from devicetest import DeviceTestCase


# Device test case
class MagnetTestCase(DeviceTestCase):

    device = Magnet.Magnet
    device_cls = Magnet.MagnetClass

    properties = {
        "Polarity": [
            "1"
        ],
        "Length": [
            "0.1"
        ],
        "Orientation": [
            "1"
        ],
        "Tilt": [
            "0"
        ],
        "TemperatureInterlock": [
            "I-BC1/DIA/COOLING,B_I_BC1SXL2_DIA_TSW1_A,Temp > 60 alarm to TANGO",
            "I-BC1/DIA/COOLING,B_I_BC1SXL_DIA_TSW2_A,Temp > 70 alarm to TANGO"
        ],
        "Type": [
            "ksext"
        ],
        "CircuitProxies": [
            "I-BC1/MAG/CRSX-01"
        ]
    }

    @classmethod
    def mocking(cls):
        cls.circuit_proxy = MagicMock()
        cls.circuit_proxy.State = MagicMock(return_value=PyTango.DevState.ON)
        cls.device_proxy = Magnet.DeviceProxy = MagicMock(return_value=cls.circuit_proxy)

    # def test_test(self):
    #     self.circuit_proxy.State.assert_called_with()

    def test_soething(self):
        print "hehj"
        pass
