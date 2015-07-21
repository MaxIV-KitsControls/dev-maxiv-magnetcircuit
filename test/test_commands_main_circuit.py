import unittest

from mock import MagicMock
import PyTango

import MagnetCircuit

from functools import partial
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
                "[0.5, 0.0]",
                "[1.0, 0.0]",
                "[6.0, 0.0]"
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
                "[1.5, 0.0]",
                "[3.0, 0.0]",
                "[2.0, 0.0]"
            ],
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
        cls.magnetcicling = MagnetCircuit.MagnetCycling = MagicMock()

        def make_proxy():
            mock_proxy = MagicMock()
            mock_proxy.State.return_value = PyTango.DevState.ON
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

        def proxy_result(devname):
            if devname in cls.magnets:
                return cls.magnet_proxies[devname]
            return cls.ps_proxy

        cls.ps_proxy = make_ps_proxy()
        cls.magnet_proxies = dict((devname, make_magnet_proxy(devname))
                                  for devname in cls.properties["MagnetProxies"])
        cls.device_proxy = MagnetCircuit.PyTango.DeviceProxy = MagicMock(side_effect=proxy_result)

    def assertState(self, expected):
        present = self.device.state()
        self.assertEqual(present, expected,
                         "present state: %s, expected state: %s" % (present, expected))

    def test_Cycle(self):
        " StartCycle and StopCycle"
        self.assertState(PyTango.DevState.ON)
        self.device.StartCycle()
        self.assertState(PyTango.DevState.RUNNING)
        self.device.StopCycle()
        self.assertState(PyTango.DevState.ON)

    def test_CyclingCurrentStep(self):
        " set/read current step "
        set_value = 4.2
        other_value = 5.3
        self.device.CyclingCurrentStep = set_value
        read = self.device.CyclingCurrentStep
        self.assertEqual(read, set_value,
                         "present CyclingCurrentStep: %s, expected CyclingCurrentStep: %s" % (read, set_value))
        self.device.StartCycle()
        self.device.CyclingCurrentStep = other_value
        read = self.device.CyclingCurrentStep
        self.assertEqual(read, set_value,
                         "present CyclingCurrentStep: %s, expected CyclingCurrentStep: %s" % (read, set_value))
        self.device.StopCycle()
        self.device.CyclingCurrentStep = other_value
        read = self.device.CyclingCurrentStep
        self.assertEqual(read, other_value,
                         "present CyclingCurrentStep: %s, expected CyclingCurrentStep: %s" % (read, other_value))

    def test_CyclingTimeStep(self):
        " set/read time step "
        set_value = 4.1
        other_value = 5.2
        self.device.CyclingTimeStep = set_value
        read = self.device.CyclingTimeStep
        self.assertEqual(read, set_value,
                         "present CyclingTimeStep: %s, expected CyclingTimeStep: %s" % (read, set_value))
        self.device.StartCycle()
        self.device.CyclingTimeStep = other_value
        read = self.device.CyclingTimeStep
        self.assertEqual(read, set_value,
                         "present CyclingTimeStep: %s, expected CyclingTimeStep: %s" % (read, set_value))
        self.device.StopCycle()
        self.device.CyclingTimeStep = other_value
        read = self.device.CyclingTimeStep
        self.assertEqual(read, other_value,
                         "present CyclingTimeStep: %s, expected CyclingTimeStep: %s" % (read, other_value))
