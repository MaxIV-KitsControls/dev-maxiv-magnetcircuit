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

    def cycling_attribute(self, attribute_name, set_value, other_value):
        write_attribute = partial(self.device.write_attribute, attribute_name)
        read_attribute = lambda: self.device.read_attribute(attribute_name).w_value
        write_attribute(set_value)
        read = read_attribute()
        # check if write value is set
        self.assertEqual(read, set_value,
                         "present %s: %s, expected : %s" % (attribute_name, read, set_value))
        # while cycling, writing value do nothing
        self.device.StartCycle()
        with self.assertRaises(PyTango.DevFailed) as context:
            write_attribute(other_value)
        expected_message = "It is currently not allowed to write attribute %s. The device state is UNKNOWN" % (attribute_name)
        self.assertIn(expected_message, str(context.exception))
        read = read_attribute()
        self.assertEqual(read, set_value,
                         "present %s: %s, expected : %s" % (attribute_name, read, set_value))
        self.device.StopCycle()
        write_attribute(other_value)
        read = read_attribute()
        self.assertEqual(read, other_value,
                         "present %s: %s, expected : %s" % (attribute_name, read, other_value))

    def test_Cycle(self):
        " StartCycle and StopCycle"
        self.assertState(PyTango.DevState.ON)
        self.device.StartCycle()
        self.assertState(PyTango.DevState.RUNNING)
        self.device.StopCycle()
        self.assertState(PyTango.DevState.ON)
    '''
    def test_CyclingCurrentStep(self):
        " set/read cycling current step "
        self.cycling_attribute("CyclingCurrentStep", 4.2, 5.3)

    def test_CyclingTimeStep(self):
        " set/read cycling time step "
        self.cycling_attribute("CyclingCurrentStep", 4.1, 5.2)'''

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