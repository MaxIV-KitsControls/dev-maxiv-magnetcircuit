"""Contains the tests for the TSP device server."""

# Imports
from functools import partial
from time import sleep
from mock import MagicMock

import PyTango

import Magnet
import MagnetCircuit
#from dummy_ps.DummyPS import DummyPS, DummyPSClass

print "hej"

from unittest import skip
from devicetest import DeviceTestCase

import devicetest
print devicetest.__path__


# Device test case
class MagnetCircuitQuadTestCase(DeviceTestCase):

    # device = Magnet.Magnet
    # device_cls = Magnet.MagnetClass

    magnets = {
        "I-BC1/MAG/SXL-01": {
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
        },
        "I-BC1/MAG/SXL-02": {
            "Polarity": [
                "-1"
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
                "I-BC1/DIA/COOLING,B_I_BC1SXL1_DIA_TSW1_A,Temp > 60 alarm to TANGO",
                "I-BC1/DIA/COOLING,B_I_BC1SXL_DIA_TSW2_A,Temp > 70 alarm to TANGO"
            ],
            "Type": [
                "ksext"
            ],
            "CircuitProxies": [
                "I-BC1/MAG/CRSX-01"
            ]
        }
    }

    device = MagnetCircuit.MagnetCircuit
    device_cls = MagnetCircuit.MagnetCircuitClass

    properties = {
        "PowerSupplyProxy": [
            "I-KBC1/MAG/PSPA-01"
        ],
        "RiseTime": [
            "0.0"
        ],
        "CoilNames": [
            "A"
        ],
        "ExcitationCurveCurrents": [
            "[0, 0]",
            "[0, 0]",
            "[8.710522, 0.0]"
        ],
        "ExcitationCurveFields": [
            "[0, 0]",
            "[0, 0]",
            "[2.8373088305302416, 0.02826327945820069]"
        ],
        "ResistanceReference": [
            "0.0"
        ],
        "MagnetProxies": [
            "I-BC1/MAG/SXL-01",
            "I-BC1/MAG/SXL-02"
        ]
    }

    @classmethod
    def mocking(cls):

        "Setup mock proxies for magnets and power supply."

        def make_proxy():
            mock_proxy = MagicMock()
            mock_proxy.State.return_value=PyTango.DevState.ON
            return mock_proxy

        def get_ps_attribute_config(attr):
            config = MagicMock()
            config.min_value = 0
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

        cls.device_proxy = MagnetCircuit.DeviceProxy = MagicMock(side_effect=proxy_result)

    def test_state_on_when_ps_is_on(self):
        self.ps_proxy.State.return_value = PyTango.DevState.ON
        self.assertEqual(self.device.State(), PyTango.DevState.ON)

    def test_state_off_when_ps_is_off(self):
        self.ps_proxy.State.return_value = PyTango.DevState.OFF
        self.assertEqual(self.device.State(), PyTango.DevState.OFF)

    def test_state_fault_when_ps_is_down(self):
        self.ps_proxy.State.side_effect = PyTango.DevFailed
        self.assertEqual(self.device.State(), PyTango.DevState.FAULT)

    def test_state_recovers_when_ps_recovers(self):

        # simulate PS device broken
        self.ps_proxy.State.side_effect = PyTango.DevFailed
        self.assertEqual(self.device.State(), PyTango.DevState.FAULT)

        # turn PS device on
        self.ps_proxy.State.return_value = PyTango.DevState.ON
        self.ps_proxy.State.side_effect = None
        self.assertEqual(self.device.State(), PyTango.DevState.ON)

    def test_in_fault_if_magnet_types_not_the_same(self):
        self.magnet_proxies.values()[0].Type = ["kquad"]
        self.device.Init()
        self.assertEqual(self.ps_proxy.State(), PyTango.DevState.ON)
        self.assertEqual(self.device.State(), PyTango.DevState.FAULT)

    @skip("requires properties to be changed, which is not supported for now")
    def test_in_fault_if_calibration_data_inconsistent(self):
        self.device.put_property({"ExcitationCurveCurrents": ["[0, 0]","[2.83]"]})
        self.device.Init()
        self.assertEqual(self.ps_proxy.State(), PyTango.DevState.ON)
        self.assertEqual(self.device.State(), PyTango.DevState.FAULT)

    def test_field_is_zero_when_current_is_zero(self):
        self.ps_proxy.Current = 0.0
        current = MagicMock()
        current.w_value = 0.0
        self.ps_proxy.read_attribute.side_effect = lambda _: current
        self.assertEqual(self.device.MainFieldComponent, 0.0)

    def test_field_is_max_when_current_is_max(self):
        self.ps_proxy.Current = 8.710522
        current = MagicMock()
        current.w_value = 8.71
        self.ps_proxy.read_attribute.side_effect = lambda _: current
        config = self.device.get_attribute_config("MainFieldComponent")
        epsilon = 0.00001
        min_value = float(config.min_value)
        self.assertTrue(min_value - epsilon < self.device.MainFieldComponent < min_value + epsilon)
