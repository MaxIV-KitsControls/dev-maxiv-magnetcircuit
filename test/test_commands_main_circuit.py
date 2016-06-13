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
        """ mock """

        cls.magnetcycling = MagicMock()
        cls.magnetcycling.return_value = cls.magnetcycling
        MagnetCircuit.MagnetCycling = cls.magnetcycling

        def make_proxy():
            """ mock device proxy, set it to ON state"""
            mock_proxy = MagicMock()
            mock_proxy.State.return_value = PyTango.DevState.ON
            mock_attr = MagicMock()
            mock_attr.value = PyTango.DevState.ON
            mock_proxy.read_attribute.return_value = mock_attr
            return mock_proxy

        def get_ps_attribute_config(attr):
            """ mock power supply configuration """
            config = MagicMock()
            config.min_value = -10
            config.max_value = 10
            return config

        def make_ps_proxy():
            """" mock power supply proxy """
            mock_proxy = make_proxy()
            mock_proxy.get_attribute_config = get_ps_attribute_config
            return mock_proxy

        def get_magnet_property(devname, prop):
            magnet_property = getattr(cls.magnet_proxies[devname], prop)
            if not isinstance(magnet_property, MagicMock):
                return {prop: magnet_property}
            if prop in cls.magnets[devname]:
                return {prop: cls.magnets[devname][prop]}

        def make_magnet_proxy(devname):
            """ mock magnet proxy """
            mock_proxy = make_proxy()
            mock_proxy.get_property = partial(get_magnet_property, devname)
            return mock_proxy

        def proxy_result(devname):
            if devname in cls.magnets:
                return cls.magnet_proxies[devname]
            return cls.ps_proxy

        # create power supply mock
        cls.ps_proxy = make_ps_proxy()
        # create magnets mocks
        prop = cls.properties["MagnetProxies"]
        proxies = dict((name, make_magnet_proxy(name)) for name in prop)
        cls.magnet_proxies = proxies
        # mock DeviceProxy method to return magnets mocks or ps mock
        cls.device_proxy = MagicMock(side_effect=proxy_result)
        MagnetCircuit.PyTango.DeviceProxy = cls.device_proxy

    def assertState(self, expected):
        present = self.device.state()
        err_msg = "present state: %s, expected state: %s" % (present, expected)
        self.assertEqual(present, expected, err_msg)

    def cycling_attribute(self, attr_name, set_value, other_value):
        # write attribute method
        write_attr = partial(self.device.write_attribute, attr_name)
        # read attribute method
        read_attr = lambda: self.device.read_attribute(attr_name).w_value
        # basic assert msg
        err_msg = "present {}: {}, expected : {}"
        # write value to attribute and then read it
        write_attr(set_value)
        read = read_attr()
        # check if write value is set
        msg = err_msg.format(attr_name, read, set_value)
        self.assertEqual(read, set_value, msg)
        # while cycling, writing a value do nothing
        self.device.StartCycle()
        self.assertState(PyTango.DevState.RUNNING)
        with self.assertRaises(PyTango.DevFailed) as context:
            write_attr(other_value)
        expected_message = "It is currently not allowed to write attribute "
        expected_message += "%s. The device state is RUNNING" % (attr_name)
        self.assertIn(expected_message, str(context.exception))
        read = read_attr()
        msg = err_msg.format(attr_name, read, set_value)
        self.assertEqual(read, set_value, msg)
        self.device.StopCycle()
        write_attr(other_value)
        read = read_attr()
        msg = err_msg.format(attr_name, read, other_value)
        self.assertEqual(read, other_value, msg)

    def test_Cycle(self):
        " StartCycle and StopCycle"
        self.assertState(PyTango.DevState.ON)
        self.device.StartCycle()
        self.assertState(PyTango.DevState.RUNNING)
        self.device.StopCycle()
        self.assertState(PyTango.DevState.ON)

    def test_CyclingIterations(self):
        " set/read cycling iteration "
        self.cycling_attribute("CyclingIterations", 5, 22)

    def test_CyclingTimePlateau(self):
        " set/read cycling time plateau "
        self.cycling_attribute("CyclingTimePlateau", 3.2, 15.3)

    def test_CyclingRampTime(self):
        " set/read cycling ramp time "
        self.cycling_attribute("CyclingRampTime", 3.2, 15.3)

    def test_CyclingSteps(self):
        " set/read cycling steps "
        self.cycling_attribute("CyclingSteps", 12, 13)

    def test_CyclingErrors(self):
        assert "Errors" not in self.device.status()
        self.assertState(PyTango.DevState.ON)
        self.device.StartCycle()
        self.magnetcycling.phase = "Cycling"
        self.assertState(PyTango.DevState.RUNNING)
        assert "Errors" not in self.device.status()
        err_msg = "Put your exception message here"
        self.magnetcycling.cycling_errors = err_msg
        status = self.device.Status()
        print status, self.device, self.device.State()
        assert "Errors" in status
        assert err_msg in status
        self.device.StopCycle()
        self.assertState(PyTango.DevState.ON)
        status = self.device.status()
        assert "Errors" in status
        assert err_msg in status
        self.magnetcycling.cycling_errors = ""
        self.device.StartCycle()
        status = self.device.status()
        assert "Errors" not in status
        assert err_msg not in status
