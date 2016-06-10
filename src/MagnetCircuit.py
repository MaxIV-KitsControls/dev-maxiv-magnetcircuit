#!/usr/bin/env python
# -*- coding:utf-8 -*-

##############################################################################################################
##     Tango device for a generic magnet circuit (controlling dipole, quadrupole, etc)
##     Paul Bell
##
##     This program is free software: you can redistribute it and/or modify
##     it under the terms of the GNU General Public License as published by
##     the Free Software Foundation, either version 3 of the License, or
##     (at your option) any later version.
##     This program is distributed in the hope that it will be useful,
##     but WITHOUT ANY WARRANTY; without even the implied warranty of
##     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
##     GNU General Public License for more details.
##
##     You should have received a copy of the GNU General Public License
##     along with this program.  If not, see [http://www.gnu.org/licenses/].
##############################################################################################################

"""Tango device for generic magnet"""

__all__ = ["MagnetCircuit", "MagnetCircuitClass", "main"]

__docformat__ = 'restructuredtext'

import PyTango
import os
import sys
import numpy as np
from math import sqrt
from magnetcircuitlib import calculate_fields, calculate_setpoint
from cycling_statemachine.magnetcycling import MagnetCycling
from processcalibrationlib import process_calibration_data



# This power supply object is used by the cycling machine
#
class Wrapped_PS_Device(object):
    # pass ps device
    def __init__(self, psdev, attr_name, use_cache=True):
        self.attr = attr_name
        if use_cache:
            self.psdev = psdev
        else:
            self.psdev = PyTango.DeviceProxy(psdev.dev_name())
            self.psdev.set_source(PyTango.DevSource.DEV)

    def setValue(self, value):
        self.psdev.write_attribute(self.attr, value)

    def getValue(self):
        return self.psdev.read_attribute(self.attr).w_value

    def isOn(self):
        if self.psdev.state() in [PyTango.DevState.ON]:
            return True
        else:
            return False

    def isMoving(self):
        if self.psdev.state() in [PyTango.DevState.MOVING]:
            return True
        else:
            return False


##############################################################################################################
#
class MagnetCircuit(PyTango.Device_4Impl):
    _maxdim = 10  # Maximum number of multipole components
    _default_iteration = 4
    _default_wait = 5.0
    _default_ramp_time = 10.  # default value of cycling waiting step
    _default_steps = 4

    def __init__(self, cl, name):
        PyTango.Device_4Impl.__init__(self, cl, name)
        self.debug_stream("In __init__()")
        MagnetCircuit.init_device(self)

    def delete_device(self):
        self.debug_stream("In delete_device()")

    def init_device(self):
        self.debug_stream("In init_device()")

        self.get_device_properties(self.get_device_class())

        # energy attribute eventually to be set by higher level device
        self.energy_r = 3000000000.0  # =100 MeV for testing,
        self.energy_w = None
        self.calculate_brho()  # a conversion factor that depends on energy

        # depending on the magnet type, variable component can be k1, k2, etc
        self.MainFieldComponent_w = None
        self.MainFieldComponent_r = None
        self.fieldA = np.zeros(shape=(self._maxdim), dtype=float)
        self.fieldANormalised = np.zeros(shape=(self._maxdim), dtype=float)
        self.fieldB = np.zeros(shape=(self._maxdim), dtype=float)
        self.fieldBNormalised = np.zeros(shape=(self._maxdim), dtype=float)

        # sets whether field is scaled with energy
        self.scaleField = False

        # Some status strings
        self.status_str_prop = ""
        self.status_str_ps = ""
        self.status_str_b = ""
        self.status_str_cal = ""
        self.status_str_cyc = ""
        self.status_str_cfg = ""
        self.status_str_fin = ""
        self.field_out_of_range = False
        self.iscycling = False
        self.cyclingphase = "Cycling not set up"
        self.IntFieldQ = PyTango.AttrQuality.ATTR_VALID
        self.is_sole = False  # hack for solenoids until configured properly
        self.is_corr = False  # correctors differ from dipoles (theta vs Theta)

        # Proxy to power supply device
        self._ps_device = None
        self.actual_measurement = None  # read value from the power supply (can be voltage or current)
        self.set_point = None  # set point for the ps (current or voltage)
        self.is_voltage_controlled = False  # define if magnet are controlled by voltage

        # read the properties from the Tango DB, including calib data (type, length, powersupply proxy...)
        self.PolTimesOrient = 1  # always one for circuit
        self.Tilt = 0
        self.Length = 0
        self.Type = ""
        self.hasCalibData = False
        magnet_properties_ok = self.read_magnet_properties()  # this is reading properties from the magnet,
        # not the circuit!


        #
        # The magnet type determines the allowed field component to be controlled.
        # Note that in the multipole expansion we have:
        # 1 - dipole, 2 - quadrupole, 3 - sextupole, 4 - octupole
        # which of course is row 0-3 in our numpy array
        self.allowed_component = 0
        config_type_ok = self.config_type()


        # if magnet are controlled by voltage, we need to measure and set Voltage value on the ps
        if self.is_voltage_controlled:
            self.ps_attribute = "voltage"
            self.ps_unit = 'V'
            self.excitation_curve_setpoints = self.ExcitationCurveVoltages
        else:
            self.ps_attribute = "Current"
            self.ps_unit = 'A'
            self.excitation_curve_setpoints = self.ExcitationCurveCurrents

        # process the calibration data into useful numpy arrays
        if magnet_properties_ok and config_type_ok:
            (self.hasCalibData, self.status_str_cal, self.fieldsmatrix, self.ps_setpoint_matrix) \
                = process_calibration_data(self.excitation_curve_setpoints, self.ExcitationCurveFields,
                                           self.allowed_component)

        # set limits on set point
        self.set_point_limits()

        # set alarm levels on MainFieldComponent (etc) corresponding to the PS alarms
        if self.hasCalibData:
            self.set_field_limits()

        # from the PS limits, if available, set cycling boundaries
        self._cycler = None
        self.setup_cycler()

    ###############################################################################
    #
    def calculate_brho(self):
        # Bρ = sqrt(T(T+2M0)/(qc0) where M0 = rest mass of the electron in MeV, q = 1 and c0 = speed of light Mm/s (
        # mega m!) Energy is in eV to start.
        self.BRho = sqrt(self.energy_r / 1000000.0 * (self.energy_r / 1000000.0 + (2 * 0.510998910))) / (299.792458)

    ###############################################################################
    #
    @property
    def ps_device(self):
        if self._ps_device is None:
            try:
                self._ps_device = PyTango.DeviceProxy(self.PowerSupplyProxy)
            except (PyTango.DevFailed, PyTango.ConnectionFailed) as df:
                self.debug_stream("Failed to get power supply proxy\n" + df[0].desc)
        return self._ps_device

    ##############################################################################################################
    #
    def read_magnet_properties(self):

        # Check length, tilt, type of actual magnet devices (should all be the same on one circuit)

        magnet_property_types = {"Length": float, "Tilt": int, "Type": str}

        problematic_devices = set()  # let's be optimistic
        for (i, magnet_device_name) in enumerate(self.MagnetProxies):
            magnet_device = PyTango.DeviceProxy(magnet_device_name)
            for prop, type_ in magnet_property_types.items():
                try:
                    prop_value = type_(magnet_device.get_property(prop)[prop][0])
                except (ValueError, IndexError):
                    # undefined property gives an empty list as a value
                    print >> self.log_fatal, ("Couldn't read property '%s' from magnet device '%s'; " +
                                              "is it configured properly?") % (prop, magnet_device_name)
                    problematic_devices.add(magnet_device_name)
                else:
                    # we've got the value OK
                    if i == 0:  # use first magnet as a default
                        setattr(self, prop, prop_value)
                    else:
                        # consistency check; all magnets must have the same values
                        self_value = getattr(self, prop, None)
                        if self_value is not None and self_value != prop_value:
                            print >> self.log_fatal, ('Found magnets of different %s on same circuit (%s)'
                                                      % (prop, magnet_device_name))
                            problematic_devices.add(magnet_device_name)



        # If there were any issues report in status but do not go to FAULT as device echoes PS state
        if problematic_devices:
            self.status_str_prop = 'Problems with properties of magnet device(s). Fix and do INIT.'
            self.debug_stream(self.status_str_prop)
            return False
        else:
            self.debug_stream("Magnet length/type/tilt :  %f/%s/%d " % (self.Length, self.Type, self.Tilt))
            return True

    ##############################################################################################################
    #
    def config_type(self):

        att_vc = self.get_device_attr().get_attr_by_name("MainFieldComponent")
        multi_prop_vc = PyTango.MultiAttrProp()
        att_vc.get_properties(multi_prop_vc)
        multi_prop_vc.description = "The variable component of the field, which depends on the magnet type (k2 for " \
                                    "sextupoles, k1 for quads, Theta for dipoles, theta for correctors, " \
                                    "B_s for solenoids)"

        att_ivc = self.get_device_attr().get_attr_by_name("IntMainFieldComponent")
        multi_prop_ivc = PyTango.MultiAttrProp()
        att_ivc.get_properties(multi_prop_ivc)
        multi_prop_ivc.description = "The length integrated variable component of the field for quadrupoles and " \
                                     "sextupoles (k2*l for sextupoles, k1*l for quads)."

        if self.Type == "kquad":
            self.allowed_component = 1
            multi_prop_vc.unit = "m ^-2"
            multi_prop_vc.label = "k1"
            multi_prop_ivc.unit = "m ^-1"
            multi_prop_ivc.label = "length integrated k1"
        elif self.Type == "ksext":
            self.allowed_component = 2
            multi_prop_vc.unit = "m ^-3"
            multi_prop_vc.label = "k2"
            multi_prop_ivc.unit = "m ^-2"
            multi_prop_ivc.label = "length integrated k2"
        elif self.Type == "koct":
            self.allowed_component = 3
            multi_prop_vc.unit = "m ^-4"
            multi_prop_vc.label = "k3"
            multi_prop_ivc.unit = "m ^-4"
            multi_prop_ivc.label = "length integrated k3"
        # h and vkick useg small theta
        elif self.Type in ["hkick", "vkick"]:
            self.allowed_component = 0
            multi_prop_vc.unit = "rad"
            multi_prop_vc.label = "theta"
            multi_prop_ivc.unit = "rad m"
            multi_prop_ivc.label = "length integrated theta"
            self.is_corr = True
        # Large theta for bends.  Note that first element of field is always zero, but use it to store Theta
        elif self.Type == "csrcsbend" or self.Type == "sben" or self.Type == "rben" or self.Type == "sbend":
            self.allowed_component = 0
            multi_prop_vc.unit = "rad"
            multi_prop_vc.label = "Theta"
            # integrated field not of interest
            multi_prop_ivc.unit = ""
            multi_prop_ivc.label = ""
            multi_prop_ivc.description = ""
            self.IntFieldQ = PyTango.AttrQuality.ATTR_INVALID
        # solenoid. All elements of field are zero, but use first to store B_s
        elif self.Type == "sole":
            self.allowed_component = 0
            multi_prop_vc.unit = "T"
            multi_prop_vc.label = "B_s"
            # integrated field not of interest
            multi_prop_ivc.unit = ""
            multi_prop_ivc.label = ""
            multi_prop_ivc.description = ""
            self.IntFieldQ = PyTango.AttrQuality.ATTR_INVALID
            self.is_sole = True
        elif self.Type == "bumper":
            self.allowed_component = 0
            multi_prop_vc.unit = "rad"
            multi_prop_vc.label = "theta"
            multi_prop_ivc.unit = "rad m"
            multi_prop_ivc.label = "length integrated theta"
            self.is_voltage_controlled = True

        else:
            self.status_str_cfg = 'Magnet type invalid %s' % self.Type
            self.debug_stream(self.status_str_cfg)
            return False

        att_vc.set_properties(multi_prop_vc)
        att_ivc.set_properties(multi_prop_ivc)

        unit = "A"
        attribute = "Current"
        if self.is_voltage_controlled:
            unit = "V"
            attribute = "Voltage"

        att_sp = self.get_device_attr().get_attr_by_name("PowerSupplySetPoint")
        multi_prop_sp = PyTango.MultiAttrProp()
        att_sp.get_properties(multi_prop_sp)

        att_mv = self.get_device_attr().get_attr_by_name("PowerSupplyReadValue")
        multi_prop_mv = PyTango.MultiAttrProp()
        att_mv.get_properties(multi_prop_mv)

        att_max_sp = self.get_device_attr().get_attr_by_name("MaxSetPointValue")
        multi_prop_max_sp = PyTango.MultiAttrProp()
        att_max_sp.get_properties(multi_prop_max_sp)

        att_min_sp = self.get_device_attr().get_attr_by_name("MinSetPointValue")
        multi_prop_min_sp = PyTango.MultiAttrProp()
        att_min_sp.get_properties(multi_prop_min_sp)

        multi_prop_sp.label = attribute + " Set Point"
        multi_prop_sp.unit = unit
        multi_prop_mv.label = "Actual " + attribute
        multi_prop_mv.unit = unit
        multi_prop_max_sp.unit = unit
        multi_prop_min_sp.unit = unit

        att_sp.set_properties(multi_prop_sp)
        att_mv.set_properties(multi_prop_mv)
        att_max_sp.set_properties(multi_prop_max_sp)
        att_min_sp.set_properties(multi_prop_min_sp)

        return True

    ##############################################################################################################
    #
    def set_point_limits(self):

        self.min_setpoint_value = self.max_setpoint_value = None
        try:

            max_setpoint_s = self.ps_device.get_attribute_config(self.ps_attribute).max_value
            min_setpoint_s = self.ps_device.get_attribute_config(self.ps_attribute).min_value

            if max_setpoint_s == 'Not specified' or min_setpoint_s == 'Not specified':
                self.debug_stream(
                    "{0} limits not specified, cannot do cycling".format(
                        self.ps_attribute))  # ! We assume if there are limits then they
                # are good!

            else:
                self.max_setpoint_value = float(max_setpoint_s)
                self.min_setpoint_value = float(min_setpoint_s)

        except (AttributeError, PyTango.DevFailed):
            self.debug_stream("Cannot read {0} limits from PS {1}".format(self.ps_attribute, self.PowerSupplyProxy))

    ##############################################################################################################
    #
    def set_field_limits(self):

        if self.max_setpoint_value != None and self.min_setpoint_value != None:

            # Set the limits on the variable component (k1 etc) which will change if the energy changes
            att = self.get_device_attr().get_attr_by_name("MainFieldComponent")
            multi_prop = PyTango.MultiAttrProp()
            att.get_properties(multi_prop)
            minMainFieldComponent = \
                calculate_fields(self.allowed_component, self.ps_setpoint_matrix, self.fieldsmatrix, self.BRho,
                                 self.PolTimesOrient, self.Tilt, self.Type, self.Length, self.min_setpoint_value,
                                 is_sole=self.is_sole, find_limit=True)[1]
            maxMainFieldComponent = \
                calculate_fields(self.allowed_component, self.ps_setpoint_matrix, self.fieldsmatrix, self.BRho,
                                 self.PolTimesOrient, self.Tilt, self.Type, self.Length, self.max_setpoint_value,
                                 is_sole=self.is_sole, find_limit=True)[1]

            if minMainFieldComponent < maxMainFieldComponent:
                multi_prop.min_value = minMainFieldComponent
                multi_prop.max_value = maxMainFieldComponent
            else:
                multi_prop.min_value = maxMainFieldComponent
                multi_prop.max_value = minMainFieldComponent

            att.set_properties(multi_prop)

    ##############################################################################################################
    #
    def setup_cycler(self):

        self.status_str_cyc = ""

        # The cycling varies the ps from min and max a number of times.
        # Need to get the set point limits from the PS device; number of iterations and wait time can be properties

        if self.max_setpoint_value == None or self.min_setpoint_value == None:
            self.status_str_cyc = 'Setup cycling: cannot read {0} limits from PS {1}'.format(self.ps_attribute,
                                                                                             self.PowerSupplyProxy)
            self.debug_stream(self.status_str_cyc)
            return

        if self.ps_device:
            self.wrapped_ps_device = Wrapped_PS_Device(self.ps_device, self.ps_attribute, use_cache=False)
            self._cycler = MagnetCycling(powersupply=self.wrapped_ps_device,
                                         hi_setpoint=self.max_setpoint_value,
                                         lo_setpoint=self.min_setpoint_value,
                                         wait=self._default_wait,
                                         iterations=self._default_iteration,
                                         ramp_time=self._default_ramp_time,
                                         steps=self._default_steps,
                                         unit=self.ps_unit)
        else:
            self.status_str_cyc = "Setup cycling: cannot get proxy to %s " % self.PowerSupplyProxy

    ##############################################################################################################
    #
    def get_ps_state(self):

        self.debug_stream("In get_ps_state()")
        if self.ps_device:
            try:
                self.status_str_ps = "Reading state from %s " % self.PowerSupplyProxy
                ps_state = self.ps_device.read_attribute("State").value
            except (AttributeError, PyTango.DevFailed):
                self.status_str_ps = "Cannot read state of PS " + self.PowerSupplyProxy
                self.debug_stream(self.status_str_ps)
                self._cycler = None
                return PyTango.DevState.FAULT

        else:
            self.status_str_ps = "Read PS state:  cannot get proxy to " + self.PowerSupplyProxy
            self._cycler = None
            ps_state = PyTango.DevState.FAULT

        return ps_state

    ##############################################################################################################
    #
    def get_main_physical_quantity_and_field(self):

        self.debug_stream("In get_main_physical_quantity_and_field()")
        if self.ps_device:
            try:
                measurement_attr = self.ps_device.read_attribute(self.ps_attribute)
                self.actual_measurement = measurement_attr.value
                self.set_point = measurement_attr.w_value
                self.status_str_b = ""
                # Just assume the set point is whatever is written on the ps device (could be written directly there!)
            except:
                self.debug_stream("Cannot read {0} on PS {1}".format(self.ps_attribute, self.PowerSupplyProxy))
                return False
            else:
                # if have calib data calculate the actual and set fields
                self.field_out_of_range = False
                if self.hasCalibData:
                    (success, self.MainFieldComponent_r, self.MainFieldComponent_w, self.fieldA, self.fieldANormalised,
                     self.fieldB, self.fieldBNormalised) \
                        = calculate_fields(self.allowed_component, self.ps_setpoint_matrix, self.fieldsmatrix,
                                           self.BRho,
                                           self.PolTimesOrient, self.Tilt, self.Type, self.Length,
                                           self.actual_measurement,
                                           self.set_point, is_sole=self.is_sole)
                    if success == False:
                        self.status_str_b = "Cannot interpolate read/set {0} {1} {2} ".format(self.ps_attribute,
                                                                                              self.actual_measurement,
                                                                                              self.set_point)
                        self.field_out_of_range = True
                    return True
                else:  # if not calib data, can read ps value but not field
                    self.status_str_b = "Circuit device may only read {0}".format(self.ps_attribute)
                    self.field_out_of_range = True
                    return True

        else:
            self.debug_stream("Cannot get proxy to PS " + self.PowerSupplyProxy)
            return False

    ##############################################################################################################
    #
    def dev_state(self):
        self.debug_stream("In dev_state()")
        result = PyTango.DevState.UNKNOWN

        # Check state of PS
        ps_state = self.get_ps_state()

        # if state ok but cycler not setup, then set it up
        if ps_state == PyTango.DevState.ON and self._cycler == None:
            # set limits on set point
            self.set_point_limits()
            # set alarm levels on MainFieldComponent (etc) corresponding to the PS alarms
            if self.hasCalibData:
                self.set_field_limits()
            self.setup_cycler()

        # Generally the circuit should echo the ps state
        # If we are in RUNNING, ie cycling, stay there unless ps goes to fault
        self.check_cycling_state()
        if self.iscycling == True and ps_state in [PyTango.DevState.ON, PyTango.DevState.MOVING]:
            result = PyTango.DevState.RUNNING

        else:
            result = ps_state

        self.set_state(result)
        return result

    def check_cycling_state(self):
        # see if reached end of cycle
        self.check_cycling_status()
        if self.iscycling == True and "NOT CYCLING" in self.cyclingphase:
            self.iscycling = False

    def check_cycling_status(self):
        if self._cycler is None:
            self.cyclingphase = "Cycling not set up"
        else:
            self.cyclingphase = self._cycler.phase

    def dev_status(self):

        self.debug_stream("In dev_status()")

        # need to check cycling status
        self.check_cycling_status()

        # set status message
        msg = self.status_str_prop + "\n" + self.status_str_cfg + "\n" + self.status_str_cal + "\n" + \
              self.status_str_ps + "\n" + self.status_str_b + "\n" + self.status_str_cyc + "\nCycling status: " + \
              self.cyclingphase
        self.status_str_fin = os.linesep.join([s for s in msg.splitlines() if s])
        return self.status_str_fin

    ##############################################################################################################

    # Special function to set zeroth element of field vector to zero, as it should be for dipoles
    # Dipoles and solenoids both have allowed component= 0
    # For dipoles, we store theta (theta * BRho) in zeroth element of fieldX (fieldX normalised)
    # For solenoids, we store Bs there. But n reality zeroth element is zero. See wiki page for details.
    # But for correctors small theta is the zeroth component.
    def convert_dipole_vector(self, vector):
        #vector = list(vector)
        vector[0] = np.NAN
        return vector

    def set_ps_setpoint(self):
        # Set the setpoint on the ps
        if self.set_point > self.max_setpoint_value:
            self.debug_stream("Requested {0} {1} above limit of PS ({2})".format(self.ps_attribute, self.set_point,
                                                                                 self.max_setpoint_value))
            self.set_point = self.max_setpoint_value
        if self.set_point < self.min_setpoint_value:
            self.debug_stream("Requested {0} {1} below limit of PS ({2})".format(self.ps_attribute, self.set_point,
                                                                                 self.max_setpoint_value))
            self.set_point = self.min_setpoint_value
        self.debug_stream("SETTING {0} ON THE PS TO: {1} ".format(self.ps_attribute.upper(), self.set_point))
        try:
            self.ps_device.write_attribute(self.ps_attribute, self.set_point)
        except PyTango.DevFailed as e:
            self.status_str_ps = "Cannot set {0} on PS {1}".format(self.ps_attribute, self.PowerSupplyProxy)

    # -----------------------------------------------------------------------------
    #    MagnetCircuit read/write attribute methods
    # -----------------------------------------------------------------------------

    def read_PowerSupplySetPoint(self, attr):
        self.debug_stream("In read_PowerSupplySetPoint()")
        attr.set_value(self.set_point)

    def is_PowerSupplySetPoint_allowed(self, attr):
        return self.get_main_physical_quantity_and_field()

    def read_PowerSupplyReadValue(self, attr):
        self.debug_stream("In read_PowerSupplyReadValue()")
        attr.set_value(self.actual_measurement)

    def is_PowerSupplyReadValue_allowed(self, attr):
        return self.get_main_physical_quantity_and_field()

    #

    def read_fieldA(self, attr):
        self.debug_stream("In read_fieldA()")
        if self.allowed_component == 0 and not self.is_corr:
            attr.set_value(self.convert_dipole_vector(self.fieldA))
        else:
            attr.set_value(self.fieldA)

    def is_fieldA_allowed(self, attr):
        return self.get_main_physical_quantity_and_field() and not self.field_out_of_range

    #

    def read_fieldB(self, attr):
        self.debug_stream("In read_fieldB()")
        if self.allowed_component == 0 and not self.is_corr:
            attr.set_value(self.convert_dipole_vector(self.fieldB))
        else:
            attr.set_value(self.fieldB)

    def is_fieldB_allowed(self, attr):
        return self.get_main_physical_quantity_and_field() and not self.field_out_of_range

    #

    def read_fieldANormalised(self, attr):
        self.debug_stream("In read_fieldANormalised()")
        if self.allowed_component == 0 and not self.is_corr:
            attr.set_value(self.convert_dipole_vector(self.fieldANormalised))
        else:
            attr.set_value(self.fieldANormalised)

    def is_fieldANormalised_allowed(self, attr):
        return self.get_main_physical_quantity_and_field() and not self.field_out_of_range

    #

    def read_fieldBNormalised(self, attr):
        self.debug_stream("In read_fieldBNormalised()")
        if self.allowed_component == 0 and not self.is_corr:
            attr.set_value(self.convert_dipole_vector(self.fieldBNormalised))
        else:
            attr.set_value(self.fieldBNormalised)

    def is_fieldBNormalised_allowed(self, attr):
        return self.get_main_physical_quantity_and_field() and not self.field_out_of_range

    #

    def read_energy(self, attr):
        self.debug_stream("In read_energy()")
        attr.set_value(self.energy_r)
        if self.energy_w == None:  # true at initialise
            self.energy_w = self.energy_r
            attr.set_write_value(self.energy_w)

    def write_energy(self, attr):
        self.debug_stream("In write_energy()")
        self.energy_r = attr.get_write_value()
        self.calculate_brho()

        # If energy changes, limits on k1 etc will also change
        if self.hasCalibData:
            self.set_field_limits()

        # If energy changes, voltage/current or field must also change
        # Can only do something if calibrated
        if self.hasCalibData:
            if self.scaleField:
                self.debug_stream(
                    "Energy (Brho) changed to {0}({1}): will recalculate {2} to preserve field".format(self.energy_r,
                                                                                                       self.BRho,
                                                                                                       self.ps_attribute))
                # since brho changed, need to recalc the field
                sign = -1
                if self.allowed_component == 0 and self.Type not in ["vkick", "Y_CORRECTOR"]:
                    sign = 1
                if self.Tilt == 0 and self.Type != "vkick":
                    self.fieldB[self.allowed_component] = self.MainFieldComponent_r * self.BRho * sign
                else:
                    self.fieldA[self.allowed_component] = self.MainFieldComponent_r * self.BRho * sign

                self.set_point \
                    = calculate_setpoint(self.allowed_component, self.ps_setpoint_matrix, self.fieldsmatrix, self.BRho,
                                         self.PolTimesOrient, self.Tilt, self.Type, self.Length, self.fieldA,
                                         self.fieldB, self.is_sole)
                ###########################################################
                # Set the new set point value on the ps
                self.set_ps_setpoint()
            else:
                self.debug_stream("Energy changed: will recalculate fields for the PS {0}".format(self.ps_attribute))
                (success, self.MainFieldComponent_r, self.MainFieldComponent_w, self.fieldA, self.fieldANormalised,
                 self.fieldB, self.fieldBNormalised) \
                    = calculate_fields(self.allowed_component, self.ps_setpoint_matrix, self.fieldsmatrix, self.BRho,
                                       self.PolTimesOrient, self.Tilt, self.Type, self.Length, self.actual_measurement,
                                       self.set_point, is_sole=self.is_sole)

    def is_energy_allowed(self, attr):
        # if writing then we need to know MeasurementValue etc
        if attr == PyTango.AttReqType.READ_REQ:
            return True
        else:
            return self.get_main_physical_quantity_and_field() and not self.field_out_of_range

    #

    def read_fixNormFieldOnEnergyChange(self, attr):
        self.debug_stream("In read_changeNormFieldWithEnergy()")
        attr.set_value(self.scaleField)
        attr.set_write_value(self.scaleField)

    def write_fixNormFieldOnEnergyChange(self, attr):
        self.debug_stream("In write_changeNormFieldWithEnergy()")
        self.scaleField = attr.get_write_value()

    def read_BRho(self, attr):
        self.debug_stream("In read_BRho()")
        attr.set_value(self.BRho)

    def read_MainFieldComponent(self, attr):
        self.debug_stream("In read_MainFieldComponent()")
        if self.hasCalibData == True:
            attr.set_value(self.MainFieldComponent_r)
            attr.set_write_value(self.MainFieldComponent_w)

    def write_MainFieldComponent(self, attr):
        self.debug_stream("In write_MainFieldComponent()")
        if self.hasCalibData:
            self.MainFieldComponent_w = attr.get_write_value()
            # Note that we set the component of the field vector directly here, but
            # calling calculate_fields will in turn set the whole vector, including this component again
            sign = -1
            if self.allowed_component == 0 and self.Type not in ["vkick", "Y_CORRECTOR"]:
                sign = 1
            if self.Tilt == 0 and self.Type != "vkick":
                self.fieldB[self.allowed_component] = self.MainFieldComponent_w * self.BRho * sign
            else:
                self.fieldA[self.allowed_component] = self.MainFieldComponent_w * self.BRho * sign
            self.set_point \
                = calculate_setpoint(self.allowed_component, self.ps_setpoint_matrix, self.fieldsmatrix, self.BRho,
                                     self.PolTimesOrient, self.Tilt, self.Type, self.Length, self.fieldA, self.fieldB,
                                     self.is_sole)

            ###########################################################
            # Set the value on the ps
            self.set_ps_setpoint()

    def is_MainFieldComponent_allowed(self, attr):
        return self.get_main_physical_quantity_and_field() and not self.field_out_of_range

    #

    def read_IntMainFieldComponent(self, attr):
        self.debug_stream("In read_IntMainFieldComponent()")
        if self.hasCalibData:
            main_field_component = self.MainFieldComponent_r * self.Length
            attr.set_value(main_field_component)
            attr.set_quality(self.IntFieldQ)

    def is_IntMainFieldComponent_allowed(self, attr):
        quantity_and_field = self.get_main_physical_quantity_and_field()
        return quantity_and_field and not self.field_out_of_range

    #
    def read_CyclingStatus(self, attr):
        self.debug_stream("In read_CyclingStatus()")
        # need to check cycling status
        self.check_cycling_status()
        attr.set_value(self.cyclingphase)

    def read_CyclingState(self, attr):
        self.debug_stream("In read_CyclingState()")
        # need to check cycling state
        self.check_cycling_state()
        attr.set_value(self.iscycling)

    def write_CyclingRampTime(self, attr):
        self.debug_stream("In write_CyclingRampTime()")
        self._cycler.ramp_time = attr.get_write_value()

    def read_CyclingRampTime(self, attr):
        self.debug_stream("In read_CyclingRampTime()")
        attr.set_value(self._cycler.ramp_time)

    def is_CyclingRampTime_allowed(self, attr):
        self.check_cycling_state()
        if attr == PyTango.AttReqType.WRITE_REQ:
            return self._cycler and not self.iscycling
        else:
            return bool(self._cycler)

    def write_CyclingIterations(self, attr):
        self.debug_stream("In write_CyclingIterations()")
        self._cycler.iterations = attr.get_write_value()

    def read_CyclingIterations(self, attr):
        self.debug_stream("In write_CyclingIterations()")
        attr.set_value(self._cycler.iterations)

    def is_CyclingIterations_allowed(self, attr):
        self.check_cycling_state()
        if attr == PyTango.AttReqType.WRITE_REQ:
            return self._cycler and not self.iscycling
        else:
            return bool(self._cycler)

    def write_CyclingTimePlateau(self, attr):
        self.debug_stream("In write_CyclingTimePlateau()")
        self._cycler.wait_time = attr.get_write_value()

    def read_CyclingTimePlateau(self, attr):
        self.debug_stream("In read_CyclingTimePlateau()")
        attr.set_value(self._cycler.wait_time)

    def is_CyclingTimePlateau_allowed(self, attr):
        self.check_cycling_state()
        if attr == PyTango.AttReqType.WRITE_REQ:
            return self._cycler and not self.iscycling
        else:
            return bool(self._cycler)

    def read_NominalSetPoint(self, attr):
        self.debug_stream("In read_NominalSetPoint()")
        attr.set_value(self._cycler.nominal_setpoint_percentage)

    def write_NominalSetPoint(self, attr):
        self.debug_stream("In write_NominalSetPoint()")
        self._cycler.nominal_setpoint_percentage = attr.get_write_value()

    def is_NominalSetPoint_allowed(self, attr):
        self.check_cycling_state()
        if attr == PyTango.AttReqType.WRITE_REQ:
            return self._cycler and not self.iscycling
        else:
            return bool(self._cycler)

    def read_CyclingSteps(self, attr):
        self.debug_stream("In read_CyclingSteps()")
        attr.set_value(self._cycler.steps)

    def write_CyclingSteps(self, attr):
        self.debug_stream("In write_CyclingSteps()")
        self._cycler.steps = attr.get_write_value()

    def is_CyclingSteps_allowed(self, attr):
        self.check_cycling_state()
        if attr == PyTango.AttReqType.WRITE_REQ:
            return self._cycler and not self.iscycling
        else:
            return bool(self._cycler)

    def read_MaxSetPointValue(self, attr):
        if not self.max_setpoint_value:
            self.set_point_limits()
        attr.set_value(self.max_setpoint_value)

    def read_MinSetPointValue(self, attr):
        if not self.min_setpoint_value:
            self.set_point_limits()
        attr.set_value(self.min_setpoint_value)

    # -----------------------------------------------------------------------------
    #    MagnetCircuit command methods
    # -----------------------------------------------------------------------------

    def StartCycle(self):
        self.debug_stream("In StartCycle()")
        self._cycler.cycling = True
        self.iscycling = True

    def StopCycle(self):
        self.debug_stream("In StopCycle()")
        self._cycler.cycling = False
        self.iscycling = False

    def is_StartCycle_allowed(self):
        self.check_cycling_state()
        ps_state_on = self.get_ps_state() in [PyTango.DevState.ON,
                                              PyTango.DevState.MOVING]
        allowed = self._cycler is not None and not self.iscycling
        allowed = allowed and ps_state_on
        return allowed

    def is_StopCycle_allowed(self):
        self.check_cycling_state()
        if self.iscycling:
            return True
        else:
            return False


class MagnetCircuitClass(PyTango.DeviceClass):
    # Class Properties
    class_property_list = {
    }


    # Device Properties
    device_property_list = {
        # PJB I use strings since I can't have a 2d array of floats?
        # So now I end up with a list of lists instead. See above for conversion.
        'ExcitationCurveCurrents':
            [PyTango.DevVarStringArray,
             "Measured calibration currents for each multipole",
             [[]]],
        'ExcitationCurveVoltages':
            [PyTango.DevVarStringArray,
             "Measured calibration voltages for each multipole",
             [[]]],
        'ExcitationCurveFields':
            [PyTango.DevVarStringArray,
             "Measured calibration fields for each multipole",
             [[]]],
        'PowerSupplyProxy':
            [PyTango.DevString,
             "Associated powersupply",
             ["not set"]],
        'MagnetProxies':
            [PyTango.DevVarStringArray,
             "List of magnets on this circuit",
             ["not set"]],
    }


    # Command definitions
    cmd_list = {
        'StartCycle':
            [[PyTango.DevVoid, ""],
             [PyTango.DevBoolean, ""]],
        'StopCycle':
            [[PyTango.DevVoid, ""],
             [PyTango.DevBoolean, ""]],
    }


    # Attribute definitions
    attr_list = {
        'PowerSupplySetPoint':
            [[PyTango.DevFloat,
              PyTango.SCALAR,
              PyTango.READ],
             {
                 'label': "Current Set point",
                 'unit': "A",
                 'doc': "Set point on PS (attribute write value)",
                 'Display level': PyTango.DispLevel.EXPERT,
                 'format': "%6.5f"

             }],
        'PowerSupplyReadValue':
            [[PyTango.DevFloat,
              PyTango.SCALAR,
              PyTango.READ],
             {
                 'label': "Actual Current",
                 'unit': "A",
                 'doc': "Read value on PS",
                 'Display level': PyTango.DispLevel.EXPERT,
                 'format': "%6.5f"
             }],

        'MaxSetPointValue':
            [[PyTango.DevFloat,
              PyTango.SCALAR,
              PyTango.READ],
             {
                 'label': "Maximal set point",
                 'unit': "A",
                 'doc': "Maximal set point on PS",
                 'Display level': PyTango.DispLevel.EXPERT,
                 'format': "%6.5f"
             }],

        'MinSetPointValue':
            [[PyTango.DevFloat,
              PyTango.SCALAR,
              PyTango.READ],
             {
                 'label': "Minimal set point",
                 'unit': "A",
                 'doc': "Minimal set point on PS",
                 'Display level': PyTango.DispLevel.EXPERT,
                 'format': "%6.5f"
             }],

        'fieldA':
            [[PyTango.DevFloat,
              PyTango.SPECTRUM,
              PyTango.READ, 10],
             {
                 'label': "A_n",
                 'unit': "T m^1-n",
                 'doc': "field A (skew) components",
                 'format': "%6.5e"
             }],
        'fieldB':
            [[PyTango.DevFloat,
              PyTango.SPECTRUM,
              PyTango.READ, 10],
             {
                 'label': "B_n",
                 'unit': "T m^1-n",
                 'doc': "field B (normal) components",
                 'format': "%6.5e"
             }],
        'fieldANormalised':
            [[PyTango.DevFloat,
              PyTango.SPECTRUM,
              PyTango.READ, 10],
             {
                 'label': "e/p A_n",
                 'unit': "m^-n",
                 'doc': "field A normalised (skew) components",
                 'format': "%6.5e",
             }],
        'fieldBNormalised':
            [[PyTango.DevFloat,
              PyTango.SPECTRUM,
              PyTango.READ, 10],
             {
                 'label': "e/p B_n",
                 'unit': "m^-n",
                 'doc': "field B normalised (skew) components",
                 'format': "%6.5e",
             }],
        'energy':
            [[PyTango.DevFloat,
              PyTango.SCALAR,
              PyTango.READ_WRITE],
             {
                 'label': "electron energy",
                 'unit': "eV",
                 'format': "%6.5e",
                 'doc': "electron energy"
             }],
        'fixNormFieldOnEnergyChange':
            [[PyTango.DevBoolean,
              PyTango.SCALAR,
              PyTango.READ_WRITE],
             {
                 'label': "Preserve norm. field",
                 'unit': "T/F",
                 'doc': "If true, if the energy changes the current/voltage is recalculated in order to preserve the "
                        "normalised field"
             }],
        'BRho':
            [[PyTango.DevFloat,
              PyTango.SCALAR,
              PyTango.READ],
             {
                 'label': "b.rho",
                 'unit': "eV s m^1",
                 'doc': "b.rho normalistion factor",
                 'format': "%6.5e"
             }],
        'CyclingStatus':
            [[PyTango.DevString,
              PyTango.SCALAR,
              PyTango.READ],
             {
                 'label': "Cycling Status",
                 'doc': "status of cycling procedure"
             }],
        'CyclingState':
            [[PyTango.DevBoolean,
              PyTango.SCALAR,
              PyTango.READ],
             {
                 'label': "Cycling State",
                 'doc': "state of cycling procedure"
             }],
        'CyclingRampTime':
            [[PyTango.DevDouble,
              PyTango.SCALAR,
              PyTango.READ_WRITE],
             {
                 'label': "Cycling Ramp Time",
                 'unit': "s",
                 'format': "%6.1f",
                 'doc': "Time to increase or decrease set point to min/max value"
             }],

        'CyclingSteps':
            [[PyTango.DevLong,
              PyTango.SCALAR,
              PyTango.READ_WRITE],
             {
                 'label': "Cycling steps",
                 'doc': "Number of steps to increase set point from low value to maximum"
             }],

        'CyclingIterations':
            [[PyTango.DevLong,
              PyTango.SCALAR,
              PyTango.READ_WRITE],
             {
                 'label': "Cycling Iteration",
                 'doc': "Number of cycling interations"
             }],

        'CyclingTimePlateau':
            [[PyTango.DevDouble,
              PyTango.SCALAR,
              PyTango.READ_WRITE],
             {
                 'label': "Cycling Wait Plateau",
                 'unit': "s",
                 'format': "%6.1f",
                 'doc': "Waiting time at maximum and minimum set points"
             }],

        'NominalSetPoint':
            [[PyTango.DevDouble,
              PyTango.SCALAR,
              PyTango.READ_WRITE],
             {
                 'label': "Nominal Set Point Percentage",
                 'format': "%6.6f",
                 'max value': "1.0",
                 'min value': "0.0",
                 'doc': "Nominal set point after cycling (it is a percentage of the max set point "
             }],

        'MainFieldComponent':
            [[PyTango.DevDouble,
              PyTango.SCALAR,
              PyTango.READ_WRITE],
             {
                 'format': "%6.6f"
             }],
        'IntMainFieldComponent':
            [[PyTango.DevDouble,
              PyTango.SCALAR,
              PyTango.READ],
             {
                 'format': "%6.6f"
             }]
    }


def main():
    try:
        py = PyTango.Util(sys.argv)
        py.add_class(MagnetCircuitClass, MagnetCircuit, 'MagnetCircuit')

        U = PyTango.Util.instance()
        U.server_init()
        U.server_run()

    except PyTango.DevFailed, e:
        print '-------> Received a DevFailed exception:', e
    except Exception, e:
        print '-------> An unforeseen exception occured....', e


if __name__ == '__main__':
    main()
