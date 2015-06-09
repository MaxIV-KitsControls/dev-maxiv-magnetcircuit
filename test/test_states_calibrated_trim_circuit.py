"""Contains the tests for the TSP device server."""

# Imports
from functools import partial
from time import sleep
from mock import MagicMock

import PyTango

import Magnet
import TrimCircuit

from unittest import skip
from devicetest import DeviceTestCase

# Device test case
class TrimCircuitTestCase(DeviceTestCase):

    magnets = {
        "SECTION/MAG/MAG-03": {
            "Length": [
                "1.0"
            ],
            "Tilt": [
                "0"
            ],
            "Type": [
                "ksext"
            ],
            "CircuitProxies": [
                "SECTION/MAG/CRMAG-01"
            ],
            "ExcitationCurveCurrents": [
                "[2.0, 0.0]",
                "[2.0, 0.0]",
                "[2.0, 0.0]"
            ],
            "ExcitationCurveFields": [
                "[3.0, 0.0]",
                "[3.0, 0.0]",
                "[3.0, 0.0]"
            ]
        }
    }

    device = TrimCircuit.TrimCircuit
    device_cls = TrimCircuit.TrimCircuitClass

    properties = {
        'TrimExcitationCurveCurrents_normal_sextupole': [
            "[2.0, 0.0]",
            "[2.0, 0.0]",
            "[2.0, 0.0]"
        ],
        'TrimExcitationCurveCurrents_normal_quadrupole': [
            "[2.0, 0.0]",
            "[2.0, 0.0]"
        ],
        'TrimExcitationCurveCurrents_skew_quadrupole': [
            "[2.0, 0.0]",
            "[2.0, 0.0]"
        ],
        'TrimExcitationCurveCurrents_x_corrector': [
            "[2.0, 0.0]"
        ],
        'TrimExcitationCurveCurrents_y_corrector': [
            "[2.0, 0.0]"
        ],
        'TrimExcitationCurveFields_normal_sextupole': [
            "[4.0, 0.0]",
            "[6.0, 0.0]",
            "[8.0, 0.0]"
        ],
        'TrimExcitationCurveFields_normal_quadrupole': [
            "[4.0, 0.0]",
            "[6.0, 0.0]"
        ],
        'TrimExcitationCurveFields_skew_quadrupole': [
            "[4.0, 0.0]",
            "[6.0, 0.0]"
        ],
        'TrimExcitationCurveFields_x_corrector': [
            "[4.0, 0.0]"
        ],
        'TrimExcitationCurveFields_y_corrector': [
            "[4.0, 0.0]"
        ],
        "PowerSupplyProxy": [
            "SECTION/MAG/TPSMAG-01"
        ],
        "SwitchBoardProxy": [
            "SECTION/MAG/SWB-01"
        ],
        "MagnetProxies": [
            "SECTION/MAG/MAG-03"
        ]
    }

    @classmethod
    def mocking(cls):

        "Setup mock proxies for magnets and power supply."

        def make_proxy():
            mock_proxy = MagicMock()
            mock_proxy.State.return_value=PyTango.DevState.ON
            mock_proxy.Mode="NORMAL_QUADRUPOLE"
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

        def make_swb_proxy():
            mock_proxy = make_proxy()
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
        cls.swb_proxy = make_swb_proxy()

        def proxy_result(devname):
            if devname in cls.magnets:
                return cls.magnet_proxies[devname]
            if "PS" in devname:
                return cls.ps_proxy
            if "SWB" in devname:
                return cls.swb_proxy

        cls.device_proxy = TrimCircuit.PyTango.DeviceProxy = MagicMock(side_effect=proxy_result)

    #Test 1
    #def test_trim_state_on_when_ps_and_swb_on(self):
    #    print "Test 1.1"
    #    self.ps_proxy.State.return_value = PyTango.DevState.ON
    #    self.assertEqual(self.device.State(), PyTango.DevState.ON)

    #Test 2
    #def test_trim_state_fault_when_ps_is_fault(self):
    #    print "Test 1.2"
    #    self.ps_proxy.State.return_value = PyTango.DevState.FAULT
    #    self.assertEqual(self.device.State(), PyTango.DevState.FAULT)

    #Test 2.5
    #def test_trim_state_fault_when_swb_is_fault(self):
    #    print "Test 1.25"
    #   self.swb_proxy.State.return_value = PyTango.DevState.FAULT
    #   self.assertEqual(self.device.State(), PyTango.DevState.FAULT)

    #Test 3
    #def test_trim_state_fault_when_ps_is_down(self):
    #    print "Test 4"
    #    self.ps_proxy.State.side_effect = PyTango.DevFailed
    #   self.assertEqual(self.device.State(), PyTango.DevState.FAULT)

    #Test 3.5
    #def test_trim_state_fault_when_swb_is_down(self):
    #    print "Test 3.5"
    #    self.swb_proxy.State.side_effect = PyTango.DevFailed
    #    self.assertEqual(self.device.State(), PyTango.DevState.FAULT)

    #Test 4
    #def test_status_shows_calibration_ok(self):
    #    print "Test 4"
    #    #print self.device.Status()
    #    self.assertIn("Calibration available", self.device.Status())

    #Test 5 
    #def test_mode_is_normal_quadrupole(self):
    #    print "Test 5"
    #    print self.device.Mode
    #    self.assertEqual("NORMAL_QUADRUPOLE", self.device.Mode)

    #Test 6 
    def test_invalid_mode(self):
        print "Test 6" 
        self.swb_proxy.Mode = "HECTOQUADRUPOLE"
        #need to actually read the mode
        self.device.Mode
        #print "2", self.device.Status()
        self.assertIn("SWB Mode is invalid", self.device.Status())
