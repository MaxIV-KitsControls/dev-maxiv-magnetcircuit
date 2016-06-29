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

    magnets = {
        "SECTION/MAG/MAG-01": {
            "Length": [
                "1.0"
            ],
            "Tilt": [
                "0"
            ],
            "Type": [
                "ksext"
            ]
        },
        "SECTION/MAG/MAG-02": {
            "Length": [
                "1.0"
            ],
            "Tilt": [
                "0"
            ],
            "Type": [
                "ksext"
            ]
        }
    }

    device = MagnetCircuit.MagnetCircuit
    device_cls = MagnetCircuit.MagnetCircuitClass

    properties = {
        "PowerSupplyProxy": [
            "SECTION/MAG/PSMAG-01"
        ],
        "ExcitationCurveCurrents": [
            "[2.0, 0.0]",
            "[2.0, 0.0]",
            "[2.0, 0.0]"
        ],
        "ExcitationCurveFields": [
            "[1.0, 0.0]",
            "[2.0, 0.0]",
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
            cls.mock_attr_read = MagicMock()
            cls.mock_attr_read.value = PyTango.DevState.ON
            mock_proxy.read_attribute.return_value = cls.mock_attr_read
            return mock_proxy

        def get_ps_attribute_config(attr):
            config = MagicMock()
            config.min_value = -10
            config.max_value = 10
            return config

        def make_ps_proxy():
            mock_proxy = make_proxy()
            mock_proxy.get_attribute_config = get_ps_attribute_config
            return mock_proxy

        def get_magnet_property(devname, prop):
            if not isinstance(getattr(cls.magnet_proxies[devname], prop), MagicMock):
                return {prop: getattr(cls.magnet_proxies[devname], prop)}
            if prop in cls.magnets[devname]:
                return {prop: cls.magnets[devname][prop]}

        def make_magnet_proxy(devname):
            mock_proxy = make_proxy()
            mock_proxy.get_property = partial(get_magnet_property, devname)
            return mock_proxy

        cls.magnet_proxies = dict((devname, make_magnet_proxy(devname))
                                  for devname in cls.properties["MagnetProxies"])
        cls.ps_proxy = make_ps_proxy()

        def proxy_result(devname):
            if devname in cls.magnets:
                return cls.magnet_proxies[devname]
            return cls.ps_proxy

        cls.device_proxy = MagnetCircuit.PyTango.DeviceProxy = MagicMock(side_effect=proxy_result)

    #Test 1
    def test_state_on_when_ps_is_on(self):
        print "Test 1.1"
        self.mock_attr_read.value = PyTango.DevState.ON
        self.assertEqual(self.device.State(), PyTango.DevState.ON)

    #Test 2
    def test_state_off_when_ps_is_off(self):
        print "Test 1.2"
        self.mock_attr_read.value = PyTango.DevState.OFF
        self.assertEqual(self.device.State(), PyTango.DevState.OFF)

    #Test 2.5
    def test_state_fault_when_ps_is_fault(self):
        print "Test 1.25"
        self.mock_attr_read.value  = PyTango.DevState.FAULT
        self.assertEqual(self.device.State(), PyTango.DevState.FAULT)

    #Test 3
    def test_state_fault_when_ps_is_down(self):
        print "Test 1.3"
        self.ps_proxy.read_attribute.side_effect = PyTango.DevFailed
        self.assertEqual(self.device.State(), PyTango.DevState.FAULT)

    #Test 4
    def test_state_recovers_when_ps_recovers(self):
        print "Test 1.4"
        # simulate PS device broken
        self.ps_proxy.read_attribute.side_effect = PyTango.DevFailed
        self.assertEqual(self.device.State(), PyTango.DevState.FAULT)
        # turn PS device on
        self.mock_attr_read.value = PyTango.DevState.ON
        self.ps_proxy.read_attribute.side_effect = None
        self.assertEqual(self.device.State(), PyTango.DevState.ON)


    #Test 5
    def test_status_shows_if_magnet_types_not_the_same(self):
        self.magnet_proxies["SECTION/MAG/MAG-01"].Type = ["kquad"]
        print "Test 1.5"
        self.device.Init()
        #print self.device.Status()
        self.assertIn("Problems with properties of magnet device", self.device.Status())


    #Test 6
    def test_status_shows_if_magnet_lengths_not_the_same(self):
        self.magnet_proxies["SECTION/MAG/MAG-01"].Length = ["2.0"]
        print "Test 1.6"
        self.device.Init()
        #print self.device.Status()
        self.assertIn("Problems with properties of magnet device", self.device.Status())

    #Test 7
    def test_status_shows_if_magnet_lengths_not_the_same(self):
        self.magnet_proxies["SECTION/MAG/MAG-01"].Tilt = ["90"]
        print "Test 1.7"
        self.device.Init()
        #print self.device.Status()
        self.assertIn("Problems with properties of magnet device", self.device.Status())

    #Test 8
    def test_status_shows_calibration_ok(self):
        print "Test 1.8"
        print self.device.Status()
        self.assertIn("Calibration available", self.device.Status())

