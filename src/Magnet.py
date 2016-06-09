#!/usr/bin/env python
# -*- coding:utf-8 -*- 

###############################################################################
##     Tango device for a generic magnet (dipole, quadrupole, etc)
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
###############################################################################

"""Tango device for generic magnet"""

__all__ = ["Magnet", "MagnetClass", "main"]

__docformat__ = 'restructuredtext'

import PyTango
import os
import numpy as np
import sys
from math import sqrt
from MagnetCircuit import MagnetCircuitClass, MagnetCircuit
from TrimCircuit import TrimCircuitClass, TrimCircuit
from magnetcircuitlib import calculate_fields  # do not need calculate_current
from processcalibrationlib import process_calibration_data


class Magnet(PyTango.Device_4Impl):
    # --------- Add you global variables here --------------------------
    _maxdim = 10  # Maximum number of multipole components

    def __init__(self, cl, name):
        self._state = None
        PyTango.Device_4Impl.__init__(self, cl, name)
        self.debug_stream("In __init__()")
        Magnet.init_device(self)

    def delete_device(self):
        self.debug_stream("In delete_device()")

    def init_device(self):
        self.debug_stream("In init_device()")
        self.set_state(PyTango.DevState.ON)

        # attributes are read only field vectors
        self.fieldA_main = np.zeros(shape=(self._maxdim), dtype=float)
        self.fieldANormalised_main = np.zeros(shape=(self._maxdim), dtype=float)
        self.fieldB_main = np.zeros(shape=(self._maxdim), dtype=float)
        self.fieldBNormalised_main = np.zeros(shape=(self._maxdim), dtype=float)
        #
        #self.fieldA_trim = np.zeros(shape=(self._maxdim), dtype=float)
        #self.fieldANormalised_trim = np.zeros(shape=(self._maxdim), dtype=float)
        #self.fieldB_trim = np.zeros(shape=(self._maxdim), dtype=float)
        #self.fieldBNormalised_trim = np.zeros(shape=(self._maxdim), dtype=float)

        # this will get length, polarity, orientation and the raw calibration data
        self.get_device_properties(self.get_device_class())
        self.PolTimesOrient = self.Orientation * self.Polarity
        self.is_sole = False  # hack for solenoids until configured properly
        self.field_out_of_range = False

        # get trim and main coil proxies
        self._main_circuit_device = None  #In R1 can be several circuits
        self._trim_circuit_devices = []

        # Some status strings
        self.status_str_ilk = ""
        self.status_str_snt = ""
        self.status_str_cfg = ""
        self.status_str_cir = ""
        self.status_str_trm = ""
        self.status_str_trmi = ""
        self.status_str_b = ""

        # interlock config
        self.isInterlocked = False
        self.interlock_descs = {}
        self.interlock_proxies = {}
        self.bad_Ilock_config = False
        self.no_Ilock_config = False
        self.get_interlock_config()

        # Shunt resistance config
        self.isShunted = False
        self.shunt_on_proxy = None
        self.shunt_off_proxy = None
        self.shunt_stat_proxy = None
        self.bad_shunt_config = False
        self.no_shunt_config = False
        self.get_shunt_config()

        # configure magnet type, needed to calculate fields
        self.allowed_component = 0
        self.configure_type()

        #print "--------------------"
        #print self.allowed_component
        #print self.MainCoil
        #print self.Type

        # boolean if magnet is controlled by voltage
        self.is_voltage_controlled = False
        self.physical_quantity_controlled = "current"
        if self.is_voltage_controlled:
            self.excitation_curve_setpoints = self.ExcitationCurveVoltages
            self.physical_quantity_controlled = "voltage"
        else:
            self.excitation_curve_setpoints = self.ExcitationCurveCurrents

        # process the calibration data into useful numpy arrays
        (self.hasCalibData, self.status_str_cfg, self.fieldsmatrix, self.ps_setpoint_matrix) \
            = process_calibration_data(self.excitation_curve_setpoints, self.ExcitationCurveFields,
                                       self.allowed_component)

        # option to disable use of trim coils
        self.applyTrim = True

    ###############################################################################
    #
    @property
    def main_circuit_device(self):
        if self._main_circuit_device is None:
            try:
                self._main_circuit_device = PyTango.DeviceProxy(self.MainCoilProxy)
            except (PyTango.DevFailed, PyTango.ConnectionFailed) as df:
                msg = "Failed to get main circuit proxy"
                self.set_status(msg)
                self.debug_stream(msg)
                self.set_state(PyTango.DevState.FAULT)
        return self._main_circuit_device
                
    ###############################################################################
    #
    @property
    def trim_circuit_devices(self):
        if self._trim_circuit_devices == [] and self.TrimCoilProxies!=[]:
            for proxy in self.TrimCoilProxies:
                try:
                    self._trim_circuit_devices.append(PyTango.DeviceProxy(proxy))
                except (PyTango.DevFailed, PyTango.ConnectionFailed) as df:
                    self.debug_stream("Failed to get trim circuit proxy\n" + df[0].desc)
                    self.set_state(PyTango.DevState.FAULT)
                    self._trim_circuit_devices = []
                    return self._trim_circuit_devices
        return self._trim_circuit_devices

    ###############################################################################
    #
    def get_interlock_config(self):
        # This is a list of strings of the form [(device,attribute,description),(dev,att,desc)...]
        # First see if we gave any interlock information in the property
        if self.TemperatureInterlock != [""]:
            for s in self.TemperatureInterlock:
                try:
                    s_l = s.split(",")
                    ilock_att = s_l[0] + "/" + s_l[1]
                    ilock_desc = s_l[2]
                    ilock_proxy = PyTango.AttributeProxy(ilock_att)
                    self.interlock_descs[ilock_att] = ilock_desc
                    self.interlock_proxies[ilock_att] = ilock_proxy
                except (IndexError, PyTango.DevFailed) as e:
                    msg = "Exception configuring interlock attribute proxy " + s
                    self.debug_stream(msg)
                    self.status_str_ilk = msg
                    self.bad_Ilock_config = True

        else:
            self.no_Ilock_config = True
            msg = "No temperature interlock tags specified in properties"
            self.status_str_ilk = msg 
            self.debug_stream(msg)

    ###############################################################################
    #
    def get_shunt_config(self):
        # This is a list of three strings of the form [(device,attribute,description),(dev,att,desc)...]
        # First entry is on tag, second is off tag, third is status tag
        # First see if we gave any shunt information in the property
        if self.ShuntResistance != [""]:
            if len(self.ShuntResistance) == 3:
                on_info = self.ShuntResistance[0]
                off_info = self.ShuntResistance[1]
                stat_info = self.ShuntResistance[2]
                try:
                    self.shunt_on_proxy = PyTango.AttributeProxy(on_info.split(",")[0] + "/" + on_info.split(",")[1])
                    self.shunt_off_proxy = PyTango.AttributeProxy(off_info.split(",")[0] + "/" + off_info.split(",")[1])
                    self.shunt_stat_proxy = PyTango.AttributeProxy(stat_info.split(",")[0] + "/" + stat_info.split(",")[1])
                except:
                    self.bad_shunt_config = True
                    msg = "Exception configuring shunt attribute proxies"
                    self.debug_stream(msg)
                    self.status_str_snt = msg
            else:
                self.bad_shunt_config = True
                msg = "Incomplete shunt resistance tags specified in properties"
                self.debug_stream(msg)
                self.status_str_snt = msg 
        else:
            self.no_shunt_config = True
            msg = "No shunt resistance tags specified in properties"
            self.status_str_snt = msg 
            self.debug_stream(msg)

    ###############################################################################
    #
    def configure_type(self):

        #set highest component according to type
        if self.Type == "kquad":
            self.allowed_component = 1
        elif self.Type == "ksext":
            self.allowed_component = 2
        elif self.Type == "koct":
            self.allowed_component = 3
        elif self.Type in ["hkick", "vkick", "csrcsbend", "sben", "rben", "sbend"]:
            self.allowed_component = 0
        elif self.Type == "sole":
            self.allowed_component = 0
            self.is_sole = True
        elif self.Type == "bumper":
            self.allowed_component = 0
            self.is_voltage_controlled = True
        else:
            self.status_str_cfg = 'Magnet type invalid %s' % self.Type
            self.debug_stream(self.status_str_cfg)
            self.set_state(PyTango.DevState.FAULT)
            return


    ###############################################################################
    #
    def check_interlock(self):

        self.isInterlocked = False

        # If we have some interlock properties, see how they are set in the PLC
        if self.no_Ilock_config == True:
            return

        if self.bad_Ilock_config == False:
            self.status_str_ilk = ""
            try:
                for key in self.interlock_proxies:
                    TempInterlockValue = self.interlock_proxies[key].read().value
                    if TempInterlockValue == True:
                        self.status_str_ilk = self.status_str_ilk + "\nTemperature Interlock Set! " + key + " (" + \
                                              self.interlock_descs[key] + ")"
                        self.set_state(PyTango.DevState.ALARM)
                        self.isInterlocked = True
            except (IndexError, PyTango.DevFailed) as e:
                msg = "Cannot read specified interlock tag (s) "
                self.debug_stream(msg)
                self.status_str_ilk = msg

    ###############################################################################
    #
    def check_shunt(self):

        self.isShunted = False

        # If we have shunt status attr proxy, read from PLC
        if self.no_shunt_config == True:
            return

        if self.bad_shunt_config == False:
            self.status_str_snt = ""
            try:
                self.isShunted = self.shunt_stat_proxy.read().value
            except (IndexError, PyTango.DevFailed) as e:
                msg = "Cannot read specified shunt status tag"
                self.debug_stream(msg)
                self.status_str_snt = msg

    ###############################################################################
    #
    def get_main_circuit_state(self):

        self.debug_stream("In get_main_circuit_state()")
        if self.main_circuit_device:
            try:
                cir_state = self.main_circuit_device.read_attribute("State").value
                self.status_str_cir = "Connected to main circuit %s in state %s " % (self.MainCoilProxy, cir_state)
            except (AttributeError, PyTango.DevFailed) as e:
                self.status_str_cir = "Cannot get state of main circuit device " + self.MainCoilProxy
                self.debug_stream(self.status_str_cir)
                return PyTango.DevState.FAULT
        else:
            self.status_str_cir = "Cannot get proxy to main coil " + self.MainCoilProxy
            cir_state = PyTango.DevState.FAULT
        return cir_state

    ###############################################################################
    #
    def get_main_physical_quantity_and_field(self):
        self.debug_stream("In get_main_physical_quantity_and_field()")
        if self.main_circuit_device:
            try:
                self.debug_stream("Will read {0} from main circuit".format(self.physical_quantity_controlled))
                physical_quantity = self.main_circuit_device.PowerSupplyReadValue
                self.debug_stream("Will read BRho from main circuit")
                BRho = self.main_circuit_device.BRho
                self.status_str_b = ""

            except (AttributeError, PyTango.DevFailed) as e:
                self.debug_stream(
                    "Cannot get state or {0} from circuit device {1}".format(self.physical_quantity_controlled,
                                                                             self.MainCoilProxy))
                return False
            else:

                (success, MainFieldComponent_r, MainFieldComponent_w, self.fieldA_main, self.fieldANormalised_main,
                 self.fieldB_main, self.fieldBNormalised_main) \
                    = calculate_fields(self.allowed_component, self.ps_setpoint_matrix, self.fieldsmatrix, BRho,
                                       self.PolTimesOrient, self.Tilt, self.Type, self.Length, physical_quantity, None,
                                       self.is_sole)

                self.field_out_of_range = False
                if success == False:
                    self.status_str_b = "Cannot interpolate read {0} {1}".format(self.physical_quantity_controlled,
                                                                                 physical_quantity)
                    self.field_out_of_range = True
                return True
        else:
            self.debug_stream("Cannot get proxy to main coil " + self.MainCoilProxy)
            return False


    ###############################################################################
    #
    def get_trim_circuit_states(self):

        self.debug_stream("In get_trim_circuit_states()")
        cir_state = []
        self.status_str_trm = ""

        if self.trim_circuit_devices != []:
            for circuit in self.trim_circuit_devices:
                try:
                    thisdev = circuit.name()
                    thisstate = (circuit.read_attribute("State").value)
                    cir_state.append(thisstate)
                    self.status_str_trm += ("Connected to trim circuit %s in state %s\n" % (thisdev, thisstate))
                except (AttributeError, PyTango.DevFailed) as e:
                    #PJB can improve this message by giving device name of problematic trim
                    self.status_str_trm = "Cannot get state of trim circuit device "
                    self.debug_stream(self.status_str_trm)
                    return PyTango.DevState.FAULT
        else:
            self.status_str_trm = "Cannot get device proxies for given trim coil(s)"
            return PyTango.DevState.FAULT

        #return worst state of trim circuit
        return max(cir_state)

    ###############################################################################
    #
    def initialize_dynamic_attributes(self):

        self.debug_stream("In initialize_dynamic_attributes()")  

        if self.no_shunt_config == False and self.bad_shunt_config == False:

            shuntResistance = PyTango.Attr('shuntResistance', PyTango.DevBoolean, PyTango.READ_WRITE)
            self.add_attribute(shuntResistance, Magnet.read_shuntResistance, Magnet.write_shuntResistance)

            att = self.get_device_attr().get_attr_by_name('shuntResistance')
            multi_prop=PyTango.MultiAttrProp()
            att.get_properties(multi_prop)
            multi_prop.description = "show status and set the PLC-controlled shunt resistance"
            multi_prop.unit = "T/F"
            multi_prop.label = "shunt resistance on/off"
            att.set_properties(multi_prop)

    ###############################################################################
    #
    def always_executed_hook(self):

        self.debug_stream("In always_excuted_hook()")

        # There should be a main coil
        if self.MainCoilProxy == "":
            self.set_state(PyTango.DevState.FAULT)
            self.set_status("No main coil defined in properties")
            return
        else:
            # set state according to main circuit state
            self.set_state(self.get_main_circuit_state())
            #
            # maybe also a trim coil
            if self.TrimCoilProxies != [] and self.applyTrim:
                #check the main circuit state
                main_state = self.get_main_circuit_state()
                #check the trim circuit state
                trim_state = self.get_trim_circuit_states()
                #make use of Tango enum to set whatever is the highest state (On=0, Off=1,... Unknown=13)
                if int(trim_state)>int(main_state):
                    self.set_state(trim_state)
                else:
                    self.set_state(main_state)
                #note that alarm is higher state than fault
            else:
                if self.TrimCoilProxies != [] and not self.applyTrim:
                    self.status_str_trm = "Trim field available but not applied"
                else:
                    self.status_str_trm = "No trim for this circuit"

        # check interlock state
        self.check_interlock()

        # check shunt state
        self.check_shunt()

        # set status message
        msg = self.status_str_cfg + "\n" + self.status_str_cir + "\n" + self.status_str_b   + "\n" + \
              self.status_str_trm + "\n" + self.status_str_ilk + "\n" + self.status_str_snt + "\n" + self.status_str_trmi
        self.set_status(os.linesep.join([s for s in msg.splitlines() if s]))

    # -----------------------------------------------------------------------------
    #    Magnet read/write attribute methods
    # -----------------------------------------------------------------------------

    #method to sum the main and trim fields, when some elements will be NAN
    def sum_field(self, main_field, trim_field):
        flags = np.isnan(main_field) & np.isnan(trim_field)
        fM = main_field.copy()
        fT = trim_field.copy()
        #print "fM ", fM
        #print "fT ", fT
        fM[np.isnan(fM)] = 0.0
        fT[np.isnan(fT)] = 0.0
        out = fM + fT
        #print "sum 1", out
        out[flags] = np.NaN
        #print "sum 2", out
        return out

    #

    def read_fieldB(self, attr):
        self.debug_stream("In read_fieldB()")
        self.status_str_trmi = ""
        # look up field from trim
        if self.TrimCoilProxies != [] and self.applyTrim:
            if self.trim_circuit_devices != []:
                field = self.fieldB_main.copy()
                for trim_circuit in self.trim_circuit_devices:
                    try:
                        self.status_str_trmi += ("Summing trim field for %s\n" % trim_circuit.name())
                        field = self.sum_field(field, trim_circuit.fieldB)
                    except PyTango.DevFailed as e:
                        msg = "Not summing trim fields since cannot get field for " + trim_circuit.name()
                        self.debug_stream(msg)
                        self.status_str_trmi += (msg+"\n")
                        field =self.fieldB_main
                        break
                #set afer summing all
                attr.set_value(field)
            else:
                self.debug_stream("Cannot get proxies to trim coils, setting main field only")
                attr.set_value(self.fieldB_main)
        else:
            attr.set_value(self.fieldB_main)

    def is_fieldB_allowed(self, attr):
        self.debug_stream("In is_fieldB_allowed()")
        return self.get_state() not in [PyTango.DevState.FAULT,
                                        PyTango.DevState.UNKNOWN] and self.hasCalibData and \
               self.get_main_physical_quantity_and_field() and not self.field_out_of_range

    #

    def read_fieldA(self, attr):
        self.debug_stream("In read_fieldA()")
        self.status_str_trmi = ""
        # look up field from trim
        if self.TrimCoilProxies != [] and self.applyTrim:
            if self.trim_circuit_devices != []:
                field = self.fieldA_main.copy()
                for trim_circuit in self.trim_circuit_devices:
                    try:
                        self.status_str_trmi += ("Summing trim field for %s\n" % trim_circuit.name())
                        field = self.sum_field(field, trim_circuit.fieldA)
                    except PyTango.DevFailed as e:
                        msg = "Not summing trim fields since cannot get field for " + trim_circuit.name()
                        self.debug_stream(msg)
                        self.status_str_trmi += (msg+"\n")
                        field =self.fieldA_main
                        break
                #set afer summing all
                attr.set_value(field)
            else:
                self.debug_stream("Cannot get proxies to trim coils, setting main field only")
                attr.set_value(self.fieldA_main)
        else:
            attr.set_value(self.fieldA_main)

    def is_fieldA_allowed(self, attr):
        self.debug_stream("In is_fieldA_allowed()")
        return self.get_state() not in [PyTango.DevState.FAULT,
                                        PyTango.DevState.UNKNOWN] and self.hasCalibData and \
               self.get_main_physical_quantity_and_field() and not self.field_out_of_range

    #

    def read_fieldBNormalised(self, attr):
        self.debug_stream("In read_fieldBNormalised()")
        self.status_str_trmi = ""
        # look up field from trim
        if self.TrimCoilProxies != [] and self.applyTrim:
            if self.trim_circuit_devices != []:
                field = self.fieldBNormalised_main.copy()
                for trim_circuit in self.trim_circuit_devices:
                    try:
                        self.status_str_trmi += ("Summing trim field for %s\n" % trim_circuit.name())
                        field = self.sum_field(field, trim_circuit.fieldBNormalised)
                    except PyTango.DevFailed as e:
                        msg = "Not summing trim fields since cannot get field for " + trim_circuit.name()
                        self.debug_stream(msg)
                        self.status_str_trmi += (msg+"\n")
                        field =self.fieldBNormalised_main
                        break
                #set afer summing all
                attr.set_value(field)
            else:
                self.debug_stream("Cannot get proxies to trim coils, setting main field only")
                attr.set_value(self.fieldBNormalised_main)
        else:
            attr.set_value(self.fieldBNormalised_main)

    def is_fieldBNormalised_allowed(self, attr):
        self.debug_stream("In is_fieldBNormalised_allowed()")
        return self.get_state() not in [PyTango.DevState.FAULT,
                                        PyTango.DevState.UNKNOWN] and self.hasCalibData and \
               self.get_main_physical_quantity_and_field() and not self.field_out_of_range

    #

    def read_fieldANormalised(self, attr):
        self.debug_stream("In read_fieldANormalised()")
        self.status_str_trmi = ""
        # look up field from trim
        if self.TrimCoilProxies != [] and self.applyTrim:
            if self.trim_circuit_devices != []:
                field = self.fieldANormalised_main.copy()
                for trim_circuit in self.trim_circuit_devices:
                    try:
                        self.status_str_trmi += ("Summing trim field for %s\n" % trim_circuit.name())
                        field = self.sum_field(field, trim_circuit.fieldANormalised)
                    except PyTango.DevFailed as e:
                        msg = "Not summing trim fields since cannot get field for " + trim_circuit.name()
                        self.debug_stream(msg)
                        self.status_str_trmi += (msg+"\n")
                        field =self.fieldANormalised_main
                        break
                #set afer summing all
                attr.set_value(field)
            else:
                self.debug_stream("Cannot get proxies to trim coils, setting main field only")
                attr.set_value(self.fieldANormalised_main)
        else:
            attr.set_value(self.fieldANormalised_main)

    def is_fieldANormalised_allowed(self, attr):
        self.debug_stream("In is_fieldANormalised_allowed()")
        return self.get_state() not in [PyTango.DevState.FAULT,
                                        PyTango.DevState.UNKNOWN] and self.hasCalibData and \
               self.get_main_physical_quantity_and_field() and not self.field_out_of_range

    #

    def read_temperatureInterlock(self, attr):
        self.debug_stream("In read_temperatureInterlock()")
        attr.set_value(self.isInterlocked)

    #

    def read_shuntResistance(self, attr):
        self.debug_stream("In read_shuntResistance()")
        attr.set_value(self.isShunted)

    def write_shuntResistance(self, attr):
        self.debug_stream("In write_shuntResistance()")
        #Only write if set value different to read value
        new_shunt_state = attr.get_write_value()
        if new_shunt_state != self.isShunted:
            self.debug_stream("Will change shunt state")
            if new_shunt_state == True:
                try:
                    self.shunt_on_proxy.write(1)
                except (IndexError, PyTango.DevFailed) as e:
                    msg = "Cannot write to SHUNT ON attribute proxy"
                    self.debug_stream(msg)
                    self.status_str_snt = msg
            else:
                try:
                    self.shunt_off_proxy.write(1)
                except (IndexError, PyTango.DevFailed) as e:                    
                    msg = "Cannot write to SHUNT OFF attribute proxy"
                    self.debug_stream(msg)
                    self.status_str_snt = msg

    #

    def read_applyTrim(self, attr):
        self.debug_stream("In read_applyTrim()")
        attr.set_value(self.applyTrim)
        attr.set_write_value(self.applyTrim)

    def write_applyTrim(self, attr):
        self.debug_stream("In write_applyTrim()")
        self.applyTrim = attr.get_write_value()

        # -----------------------------------------------------------------------------
        #    Magnet command methods
        # -----------------------------------------------------------------------------


class MagnetClass(PyTango.DeviceClass):

    def dyn_attr(self, dev_list):
        for dev in dev_list:
            dev.initialize_dynamic_attributes()


    # Class Properties
    class_property_list = {
    }


    # Device Properties
    device_property_list = {
        'MainCoilProxy':
            [PyTango.DevString,
             "Associated main circuit",
             [""]],
        'TrimCoilProxies':
            [PyTango.DevVarStringArray,
             "Associated trim circuit(s)",
             []],
        'Length':
            [PyTango.DevFloat,
             "Length",
             [0.0]],
        'Polarity':
            [PyTango.DevShort,
             "Polarity",
             [1]],
        'Orientation':
            [PyTango.DevShort,
             "Orientation",
             [1]],
        'Tilt':
            [PyTango.DevShort,
             "Tilt",
             [0]],
        'Type':
            [PyTango.DevString,
             "Type",
             [""]],
        'TemperatureInterlock':
            [PyTango.DevVarStringArray,
             "TemperatureInterlock",
             [""]],
        'ShuntResistance':
            [PyTango.DevVarStringArray,
             "ShuntResistance",
             [""]],
        # PJB I use strings below since I can't have a 2d array of floats?
        # So now I end up with a list of lists instead. See above for conversion.
        'ExcitationCurveCurrents':
            [PyTango.DevVarStringArray,
             "Measured calibration currents for each multipole",
             []],
        'ExcitationCurveVoltages':
            [PyTango.DevVarStringArray,
             "Measured calibration voltages for each multipole",
             []],
        'ExcitationCurveFields':
            [PyTango.DevVarStringArray,
             "Measured calibration fields for each multipole",
             []],
    }


    # Command definitions
    cmd_list = {
    }


    # Attribute definitions
    attr_list = {
        'applyTrim':
            [[PyTango.DevBoolean,
              PyTango.SCALAR,
              PyTango.READ_WRITE],
             {
                 'label': "apply trim field",
                 'unit': "T/F",
                 'doc': "Toggles whether the magnet device adds the trim field to the field of the main circuit",
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
                 'doc': "field B (skew) components",
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
                 'format': "%6.5e"
             }],
        'fieldBNormalised':
            [[PyTango.DevFloat,
              PyTango.SPECTRUM,
              PyTango.READ, 10],
             {
                 'label': "e/p B_n",
                 'unit': "m^-n",
                 'doc': "field B normalised (skew) components",
                 'format': "%6.5e"
             }],
        'temperatureInterlock':
            [[PyTango.DevBoolean,
              PyTango.SCALAR,
              PyTango.READ],
             {
                 'label': "temperature interlock",
                 'unit': "T/F",
                 'doc': "indicates if a thermoswitch read by PLC is over temperature"
             }]
    }


def main():
    try:

        py = PyTango.Util(sys.argv)

        py.add_class(MagnetClass, Magnet, 'Magnet')
        py.add_class(MagnetCircuitClass, MagnetCircuit, 'MagnetCircuit')

        U = PyTango.Util.instance()

        #Trim circuit class needed for ring magnets only, not linac
        if U.get_ds_name().split("/")[1].startswith("R3"):
            py.add_class(TrimCircuitClass, TrimCircuit, 'TrimCircuit')

        U.server_init()
        U.server_run()

    except PyTango.DevFailed, e:
        print '-------> Received a DevFailed exception:', e
    except Exception, e:
        print '-------> An unforeseen exception occured....', e


if __name__ == '__main__':
    main()
