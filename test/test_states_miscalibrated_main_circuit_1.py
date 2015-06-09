"""Contains the tests for the TSP device server."""

# Imports
from functools import partial
from time import sleep
from mock import MagicMock

import PyTango

import Magnet
import MagnetCircuit

from unittest import skip
from devicetest import DeviceTestCase

# Device test case
class MagnetCircuitTestCase(DeviceTestCase):

    magnets = {} # not needed
    device = MagnetCircuit.MagnetCircuit
    device_cls = MagnetCircuit.MagnetCircuitClass

    properties = {
        "PowerSupplyProxy": [
            "SECTION/MAG/PSMAG-01"
        ],
        "ExcitationCurveCurrents": [
            "[2.0, 0.0]",
            "[2.0, 0.0]",
            "[2.0, 1.0, 0.0]"
        ],
        "ExcitationCurveFields": [
            "[1.0, 0.0]",
            "[2.0, 0.0]",
            "[4.0, 1.0]", 
            "[4.0, 0.0]"

        ],
        "MagnetProxies": [
            "SECTION/MAG/MAG-01",
            "SECTION/MAG/MAG-02"
        ]
    }

    @classmethod
    def mocking(cls):

        "Setup mock proxies for magnets and power supply."

        def make_proxy():
            mock_proxy = MagicMock()
            return mock_proxy

        def make_ps_proxy():
            mock_proxy = make_proxy()
            return mock_proxy

        def make_magnet_proxy(devname):
            mock_proxy = make_proxy()
            return mock_proxy

        cls.ps_proxy = make_ps_proxy()

        cls.magnet_proxies = dict((devname, make_magnet_proxy(devname))
                                  for devname in cls.properties["MagnetProxies"])

        def proxy_result(devname):
            if devname in cls.magnets:
                return cls.magnet_proxies[devname]
            return cls.ps_proxy

        cls.device_proxy = MagnetCircuit.PyTango.DeviceProxy = MagicMock(side_effect=proxy_result)


    #Test 1
    def test_status_shows_calibration_bad(self):
        print "Test 1"
        #print self.device.Status()
        self.assertIn("different number of multipoles in field and current data", self.device.Status())


