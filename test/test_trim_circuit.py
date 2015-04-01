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
        cls.swb_proxy = make_swb_proxy()
        cls.ps_proxy = make_ps_proxy()


        def proxy_result(devname):
            if devname in cls.magnets:
                return cls.magnet_proxies[devname]
            if "PS" in devname:
                return cls.ps_proxy
            if "SWB" in devname:
                return cls.swb_proxy

        cls.device_proxy = TrimCircuit.PyTango.DeviceProxy = MagicMock(side_effect=proxy_result)

    #Test 1
    def test_trim_state_on_when_ps_and_swb_on(self):
        print "Test 2.1"
        self.ps_proxy.State.return_value = PyTango.DevState.ON   #because state called as function
        self.swb_proxy.State.return_value = PyTango.DevState.ON
        #self.swb_proxy.Mode = "SKEW QUADRUPOLE"  
        #self.device.Init() #if wish to change, since Mode set in init
        #print self.device.Status()
        self.assertEqual(self.device.State(), PyTango.DevState.ON)

    #Test 2
    def test_trim_state_fault_when_ps_is_down(self):
        print "Test 2.2"
        self.ps_proxy.State.side_effect = PyTango.DevFailed
        self.assertEqual(self.device.State(), PyTango.DevState.FAULT)

    #Test 3
    def test_trim_state_fault_when_swb_is_down(self):
        print "Test 2.3"
        self.swb_proxy.State.side_effect = PyTango.DevFailed
        self.assertEqual(self.device.State(), PyTango.DevState.FAULT)
   
    #Test 4
    def test_k_zero_when_current_zero(self):
        print "Test 2.4"
        #have to set current on ps
        self.ps_proxy.read_attribute("Current").value = 0.0
        self.ps_proxy.read_attribute("Current").w_value = 0.0
        self.assertEqual(self.device.MainFieldComponent, self.ps_proxy.read_attribute("Current").value)

    #Test 5 - quad mode
    def test_k1_three_when_current_one(self):
        print "Test 2.5"

    	#have to set current on ps
    	self.ps_proxy.read_attribute("Current").value = 1.0
    	self.ps_proxy.read_attribute("Current").w_value = 1.0

        #set mode to sext
        self.swb_proxy.Mode = "NORMAL_QUADRUPOLE"  
        self.device.Init() 

        #print self.device.Status()
        field = -1.0 * self.device.MainFieldComponent
        #print "quad field is ", field
	self.assertTrue(field-0.01 < 3.0 < field+0.01)

    #Test 6 - corrector mode
    def test_k0_two_when_current_one(self):
        print "Test 2.6"

    	#have to set current on ps
    	self.ps_proxy.read_attribute("Current").value = 1.0
    	self.ps_proxy.read_attribute("Current").w_value = 1.0

        #set mode to sext
        self.swb_proxy.Mode = "X_CORRECTOR"  
        self.device.Init() 

        #print self.device.Status()
       	field = self.device.MainFieldComponent
        #print "corr field is ", field
	self.assertTrue(field-0.01 < 2.0 < field+0.01)

