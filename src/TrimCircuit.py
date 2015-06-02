#!/usr/bin/env python
# -*- coding:utf-8 -*-

##############################################################################################################
##     Tango device for a generic trim circuit 
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

__all__ = ["TrimCircuit", "TrimCircuitClass", "main"]

__docformat__ = 'restructuredtext'

import PyTango
import os
import sys
import numpy as np
from math import sqrt
import time
from magnetcircuitlib import calculate_fields, calculate_current
from processcalibrationlib import process_calibration_data

##############################################################################################################
#
class TrimCircuit (PyTango.Device_4Impl):

    _maxdim = 10 #Maximum number of multipole components

    #allowed trim coil modes
    MODE_NAMES = ["SEXTUPOLE",
                  "NORMAL_QUADRUPOLE",
                  "SKEW_QUADRUPOLE",
                  "X_CORRECTOR",
                  "Y_CORRECTOR"]

    #allowed types of trim coils (only SX type has sextupole mode!)
    #MODE_TYPES = ["OXX", "OXY", "OYY", "SXDE"]

    def __init__(self,cl, name):
        PyTango.Device_4Impl.__init__(self,cl,name)
        self.debug_stream("In __init__()")
        TrimCircuit.init_device(self)


    def delete_device(self):
        self.debug_stream("In delete_device()")


    def init_device(self):

        self.debug_stream("In init_device()")
        self.set_state(PyTango.DevState.ON)

        self.get_device_properties(self.get_device_class())

        #energy attribute eventually to be set by higher level device?
        self.energy_r = 3000000000.0 #=100 MeV for testing, needs to be read from somewhere
        self.energy_w = None
        self.calculate_brho() #a conversion factor that depends on energy

        #depending on the magnet type, variable component can be k1, k2, etc
        self.MainFieldComponent_w = None
        self.MainFieldComponent_r = None
        self.fieldA           = np.zeros(shape=(self._maxdim), dtype=float)
        self.fieldANormalised = np.zeros(shape=(self._maxdim), dtype=float)
        self.fieldB           = np.zeros(shape=(self._maxdim), dtype=float)
        self.fieldBNormalised = np.zeros(shape=(self._maxdim), dtype=float)  

        #sets whether field is scaled with energy
        self.scaleField=False

        #Some status strings
        self.status_str_prop  = ""
        self.status_str_ps    = ""
        self.status_str_b     = ""
        self.status_str_swb   = ""
        self.status_str_cal   = {}
        self.status_str_cfg   = ""
        self.status_str_fin   = ""
        self.field_out_of_range = False

        #Proxy to switch board device
        self._swb_device = None
        self.Mode = None #one of the allowed modes
        self.oldMode = None #keep track of mode changes

        #Proxy to power supply device
        self._ps_device = None
        self.actual_current = None
        self.set_current = None

        #set limits on current
        self.set_current_limits()

        #read the properties from the Tango DB, including calib data (length, powersupply proxy...)  
        self.PolTimesOrient = 1 #always one for circuit
        self.Tilt = 0 #irrelevant for trim, never tilted (but mode - skew or ver_corr - can fill An)
        self.Length = 0 #read from magnet below...
        self.get_magnet_length() #...this is reading from the magnet, not the circuit!
        #

        #process the calibration data into useful numpy arrays
        self.fieldsmatrix = {} #calibration data accessed via mode
        self.currentsmatrix = {}
        self.hasCalibData = {} #a flag per mode

        #need to know which type of trim circuit this is (SXDE, OXY, etc)
        #The device names contains the type, e.g R3-301M1/MAG/CRTOXX-01
        trim_type = self.get_name().split("/")[-1].split("-")[0]

        #normal quadrupole
        typearg="NORMAL_QUADRUPOLE"
        (self.hasCalibData[typearg], self.status_str_cal[typearg],  self.fieldsmatrix[typearg],  self.currentsmatrix[typearg]) \
            = process_calibration_data(self.TrimExcitationCurveCurrents_normal_quadrupole,self.TrimExcitationCurveFields_normal_quadrupole, 1)

        #skew quadrupole - fills An
        typearg="SKEW_QUADRUPOLE"
        (self.hasCalibData[typearg], self.status_str_cal[typearg],  self.fieldsmatrix[typearg],  self.currentsmatrix[typearg]) \
            = process_calibration_data(self.TrimExcitationCurveCurrents_skew_quadrupole,self.TrimExcitationCurveFields_skew_quadrupole, 1)


        #horizontal correction
        typearg="X_CORRECTOR"
        (self.hasCalibData[typearg], self.status_str_cal[typearg],  self.fieldsmatrix[typearg],  self.currentsmatrix[typearg]) \
            = process_calibration_data(self.TrimExcitationCurveCurrents_x_corrector,self.TrimExcitationCurveFields_x_corrector, 0)

        #vertical correction - fills An
        typearg="Y_CORRECTOR"
        (self.hasCalibData[typearg], self.status_str_cal[typearg],  self.fieldsmatrix[typearg],  self.currentsmatrix[typearg]) \
            = process_calibration_data(self.TrimExcitationCurveCurrents_y_corrector,self.TrimExcitationCurveFields_y_corrector, 0)

        #only sextupole types have sextupole modes:
        if "SX" in trim_type:
            typearg="SEXTUPOLE"
            (self.hasCalibData[typearg], self.status_str_cal[typearg],  self.fieldsmatrix[typearg],  self.currentsmatrix[typearg]) \
                = process_calibration_data(self.TrimExcitationCurveCurrents_normal_sextupole,self.TrimExcitationCurveFields_normal_sextupole, 2)


        #The switchboard mode determines the allowed field component to be controlled.
        #Note that in the multipole expansion we have:
        self.allowed_component = 0
        self.get_swb_mode()

    ###############################################################################
    #
    def calculate_brho(self):
        #Bρ = sqrt(T(T+2M0)/(qc0) where M0 = rest mass of the electron in MeV, q = 1 and c0 = speed of light Mm/s (mega m!) Energy is in eV to start.
        self.BRho = sqrt( self.energy_r/1000000.0 * (self.energy_r/1000000.0 + (2 * 0.510998910) ) ) / (299.792458)

    ###############################################################################
    #
    @property
    def ps_device(self):
        if self._ps_device is None:
            try:
                self._ps_device = PyTango.DeviceProxy(self.PowerSupplyProxy)
            except (PyTango.DevFailed, PyTango.ConnectionFailed) as df:
                self.debug_stream("Failed to get power supply proxy\n" + df[0].desc)
                self.set_state(PyTango.DevState.FAULT)
        return self._ps_device

    ###############################################################################
    #
    @property
    def swb_device(self):
        if self._swb_device is None:
            try:
                self._swb_device = PyTango.DeviceProxy(self.SwitchBoardProxy)
            except (PyTango.DevFailed, PyTango.ConnectionFailed) as df:
                self.debug_stream("Failed to get switch board proxy\n" + df[0].desc)
                self.set_state(PyTango.DevState.FAULT)
        return self._swb_device

    ##############################################################################################################
    #
    def get_magnet_length(self):

        #Check length of actual magnet devices (should all be the same on one circuit)
        problematic_devices = set()  # let's be optimistic
        for (i, magnet_device_name) in enumerate(self.MagnetProxies):
            magnet_device = PyTango.DeviceProxy(magnet_device_name)
            try:
                newlength = float(magnet_device.get_property("Length")["Length"][0])
            except (IndexError,PyTango.DevFailed):
                newlength = 1
            if i == 0:
                self.Length = newlength
            if self.Length != newlength:
                print >> self.log_fatal, ('Found magnets of different length on same circuit')
                problematic_devices.add(magnet_device_name)

        # If there were any issues go to FAULT
        if problematic_devices:
            self.status_str_prop = 'Problems with properties of magnet device(s): %s. Fix and do INIT' % ", ".join(problematic_devices)
            self.debug_stream(self.status_str_prop)
            self.set_state( PyTango.DevState.FAULT )
        else:
            self.debug_stream("Magnet length :  %f " % (self.Length))

    ##############################################################################################################
    #
    def config_type(self):

        att_vc = self.get_device_attr().get_attr_by_name("MainFieldComponent")
        multi_prop_vc = PyTango.MultiAttrProp()
        att_vc.get_properties(multi_prop_vc)
        multi_prop_vc.description = "The variable component of the field, which depends on the magnet type (k2 for sextupoles, k1 for quads, theta for dipoles, B_s for solenoids)"

        att_ivc = self.get_device_attr().get_attr_by_name("IntMainFieldComponent")
        multi_prop_ivc = PyTango.MultiAttrProp()
        att_ivc.get_properties(multi_prop_ivc)
        multi_prop_ivc.description = "The length integrated variable component of the field for quadrupoles and sextupoles (k2*l for sextupoles, k1*l for quads)."

        if self.Mode in ["SKEW_QUADRUPOLE","NORMAL_QUADRUPOLE"]:
            self.allowed_component = 1
            multi_prop_vc.unit   = "m ^-2"
            multi_prop_vc.label  = "k1"
            multi_prop_ivc.unit  = "m ^-1"
            multi_prop_ivc.label = "length integrated k1"
        elif self.Mode == "SEXTUPOLE":
            self.allowed_component = 2
            multi_prop_vc.unit   = "m ^-3"
            multi_prop_vc.label  = "k2"
            multi_prop_ivc.unit  = "m ^-2"
            multi_prop_ivc.label = "length integrated k2"
        elif self.Mode in ["X_CORRECTOR","Y_CORRECTOR"]:
            self.allowed_component = 0
            multi_prop_vc.unit   = "rad"
            multi_prop_vc.label  = "theta"
            multi_prop_ivc.unit  = "rad m"
            multi_prop_ivc.label = "length integrated theta"
        else:
            self.status_str_cfg = 'Mode type invalid %s' % self.Mode
            self.debug_stream(self.status_str_cfg)
            self.set_state( PyTango.DevState.FAULT )
            return

        att_vc.set_properties(multi_prop_vc)
        att_ivc.set_properties(multi_prop_ivc)


    ##############################################################################################################
    #
    def set_current_limits(self):

        self.mincurrent = self.maxcurrent = None
        try:

            maxcurrent_s = self.ps_device.get_attribute_config("Current").max_value
            mincurrent_s = self.ps_device.get_attribute_config("Current").min_value

            if maxcurrent_s == 'Not specified' or mincurrent_s == 'Not specified':
                self.debug_stream("Current limits not specified") 

            else:
                self.maxcurrent = float(maxcurrent_s)
                self.mincurrent = float(mincurrent_s)
                
        except (AttributeError, PyTango.DevFailed):
            self.debug_stream("Cannot read current limits from PS " + self.PowerSupplyProxy)


    ##############################################################################################################
    #
    def set_field_limits(self):

        if self.maxcurrent != None and self.mincurrent != None:

            #Set the limits on the variable component (k1 etc) which will change if the energy changes
            att = self.get_device_attr().get_attr_by_name("MainFieldComponent")
            multi_prop = PyTango.MultiAttrProp()
            att.get_properties(multi_prop)

            minMainFieldComponent = calculate_fields(self.allowed_component, self.currentsmatrix[self.Mode], self.fieldsmatrix[self.Mode], self.BRho, self.PolTimesOrient, self.Tilt, self.Mode, self.Length,  self.mincurrent, is_sole=False, find_limit=True)[1]
            maxMainFieldComponent = calculate_fields(self.allowed_component, self.currentsmatrix[self.Mode], self.fieldsmatrix[self.Mode], self.BRho, self.PolTimesOrient, self.Tilt, self.Mode, self.Length,  self.maxcurrent, is_sole=False, find_limit=True)[1]

            #print "calc min  limit for ", self.mincurrent, minMainFieldComponent
            #print "calc max  limit for ", self.maxcurrent, maxMainFieldComponent

            if minMainFieldComponent<maxMainFieldComponent:
                multi_prop.min_value=minMainFieldComponent
                multi_prop.max_value=maxMainFieldComponent
            else:
                multi_prop.min_value=maxMainFieldComponent
                multi_prop.max_value=minMainFieldComponent

            att.set_properties(multi_prop)


    ##############################################################################################################
    #
    def get_ps_state(self):

        self.debug_stream("In get_ps_state()")
        if self.ps_device:
            try:
                self.status_str_ps = "Reading state from %s  " % self.PowerSupplyProxy  
                ps_state = self.ps_device.State()
            except:
                self.status_str_ps = "Cannot read state of PS " + self.PowerSupplyProxy
                self.debug_stream(self.status_str_ps)
                return PyTango.DevState.FAULT

        else:
            self.status_str_ps = "Read PS state:  cannot get proxy to " + self.PowerSupplyProxy 
            ps_state = PyTango.DevState.FAULT

        return ps_state

    ##############################################################################################################
    #
    def get_current_and_field(self):

        self.debug_stream("In get_current_and_field()")

        if self.ps_device:
            try:
                current_att = self.ps_device.read_attribute("Current")
                self.actual_current = current_att.value
                self.set_current = current_att.w_value
                self.status_str_b = ""
                #Just assume the set current is whatever is written on the ps device (could be written directly there!)
            except:
                self.debug_stream("Cannot read current on PS " + self.PowerSupplyProxy)
                return False
            else:  
                self.field_out_of_range = False
                if self.hasCalibData[self.Mode]:
                    #calculate the actual and set fields
                    (success, self.MainFieldComponent_r, self.MainFieldComponent_w, self.fieldA, self.fieldANormalised, self.fieldB, self.fieldBNormalised)  \
                        = calculate_fields(self.allowed_component, self.currentsmatrix[self.Mode], self.fieldsmatrix[self.Mode], self.BRho, self.PolTimesOrient, self.Tilt, self.Mode, self.Length, self.actual_current, self.set_current, is_sole=False)
                    if success==False:
                        self.status_str_b = "Cannot interpolate read/set currents %f/%f " % (self.actual_current,self.set_current)
                        self.field_out_of_range = True
                    return True
                else: #if not calib data, can read current but not field
                    self.status_str_b = "Circuit device may only read current"
                    self.field_out_of_range = True
                    return True

        else:
            self.debug_stream("Cannot get proxy to PS " + self.PowerSupplyProxy)
            return False


    ##############################################################################################################
    #
    def get_swb_mode(self):

        self.debug_stream("In get_swb_mode()")

        if self.swb_device:
            try:
                self.Mode =  self.swb_device.Mode
            except:
                self.debug_stream("Cannot read mode on SWB " + self.SwitchBoardProxy)
                return False
            else:
                #whatever the mode is determines the type of behaviour of the trim coil (quad, sext, etc)
                #should maybe be event driven, not redetermine each time!
                if self.oldMode == None or self.Mode != self.oldMode:
                    self.debug_stream("SWB mode changed")
                    self.oldMode=self.Mode
                    if self.Mode not in self.MODE_NAMES:
                        self.Mode = None
                        self.oldMode = None
                        self.status_str_swb = 'Mode type invalid %s' % self.swb_device.Mode
                        self.set_state( PyTango.DevState.FAULT )
                        return False

                    #set the allowed component, unit of k, etc
                    self.config_type() 

                    #set alarm levels on MainFieldComponent (etc) corresponding to the PS alarms
                    if self.hasCalibData[self.Mode]:
                        self.set_field_limits()

                return True

        else:
            self.debug_stream("Read mode:  cannot get proxy to " + self.SwitchBoardProxy)
            return False

    ##############################################################################################################
    #
    def get_swb_state(self):

        self.debug_stream("In get_swb_state()")

        if self.swb_device:
            try:
                self.status_str_swb = "Reading SWB state from %s " % self.SwitchBoardProxy  
                swb_state = self.swb_device.State()
            except:
                self.status_str_swb = "Cannot read state on SWB " + self.SwitchBoardProxy
                self.debug_stream(self.status_str_swb)
                self.Mode = None
                return PyTango.DevState.FAULT
        else:
            self.status_str_swb = "Read SWB state:  cannot get proxy to " + self.SwitchBoardProxy
            swb_state = PyTango.DevState.FAULT
            self.Mode = None

        return swb_state


    ##############################################################################################################
    #
    def read_attr_hardware(self,data):
        pass

    def dev_state(self):

        #First check SWB state
        swb_state = self.get_swb_state()

        if swb_state in ["PyTango.DevState.UNKNOWN","PyTango.DevState.ALARM""PyTango.DevState.FAULT"]:
            self.status_str_swb = "SwitchBoard Device is in state " + str(swb_state)
            return swb_state

        #SWB might be OK but mode invalid
        if self.Mode == None:
            return PyTango.DevState.FAULT

        #Check PS state if SWB is OK
        ps_state = self.get_ps_state()
        return ps_state

    def dev_status(self):

        #set status messge
        if self.Mode != None:
            msg = "Mode: " + self.Mode +"\n"+ self.status_str_prop +"\n"+ self.status_str_cfg +"\n"+ self.status_str_cal[self.Mode] +"\n"+ self.status_str_ps +"\n"+ self.status_str_swb 
        else:
            msg = "Mode is invalid\n" + self.status_str_prop +"\n"+ self.status_str_cfg +"\n"+  self.status_str_ps +"\n"+ self.status_str_b + "\n" + self.status_str_swb 
        #self.set_status(os.linesep.join([s for s in self.status_str_fin.splitlines() if s]))
        self.status_str_fin = os.linesep.join([s for s in msg.splitlines() if s])
        return self.status_str_fin


    ##############################################################################################################

    #Special function to set zeroth element of field vector to zero, as it should be for dipoles
    #(We use the zeroth element to store theta, but should not be returned)
    def convert_dipole_vector(self,vector):
        returnvector = list(vector)
        returnvector[0]=np.NAN
        return returnvector

    def set_ps_current(self):
        #Set the current on the ps
        if self.set_current > self.maxcurrent:
            self.debug_stream("Requested current %f above limit of PS (%f)" % (self.set_current,self.maxcurrent))
            self.set_current = self.maxcurrent
        if self.set_current < self.mincurrent:
            self.debug_stream("Requested current %f below limit of PS (%f)" % (self.set_current,self.mincurrent))
            self.set_current = self.mincurrent
        self.debug_stream("SETTING CURRENT ON THE PS TO: %f ", self.set_current)
        try:
            self.ps_device.write_attribute("Current", self.set_current)
        except PyTango.DevFailed as e:
            self.set_state(PyTango.DevState.ALARM)
            self.status_str_ps = "Cannot set current on PS" + self.PowerSupplyProxy


    #-----------------------------------------------------------------------------
    #    TrimCircuit read/write attribute methods
    #-----------------------------------------------------------------------------

    def read_mode(self, attr):
        self.debug_stream("In read_mode()")
        attr.set_value(self.Mode)

    def is_mode_allowed(self, attr):
        self.debug_stream("In is_mode_allowed()")
        return self.get_state() not in [PyTango.DevState.FAULT,PyTango.DevState.UNKNOWN] and self.get_swb_mode()

    #

    def read_currentSet(self, attr):
        self.debug_stream("In read_currentSet()")
        attr.set_value(self.set_current)

    def is_currentCalculated_allowed(self, attr):
        self.debug_stream("In is_currentCalculated_allowed()")
        return self.get_state() not in [PyTango.DevState.FAULT,PyTango.DevState.UNKNOWN] and self.get_current_and_field()
       
    #

    def read_currentActual(self, attr):
        self.debug_stream("In read_currentActual()")
        attr.set_value(self.actual_current)

    def is_currentActual_allowed(self, attr):
        self.debug_stream("In is_currentActual_allowed()")
        return self.get_state() not in [PyTango.DevState.FAULT,PyTango.DevState.UNKNOWN] and self.get_current_and_field()

    #

    def read_fieldA(self, attr):
        self.debug_stream("In read_fieldA()")
        #Dipoles and solenoids both have allowed component= 0
        #For dipoles, we store theta (theta * BRho) in zeroth element of fieldX (fieldX normalised)
        #For solenoids, we store Bs there
        #BUT in reality zeroth element is zero. See wiki page for details.
        if self.allowed_component == 0:
            attr.set_value(self.convert_dipole_vector(self.fieldA))
        else:
            attr.set_value(self.fieldA)

    def is_fieldA_allowed(self, attr):
        self.debug_stream("In read_fieldA_allowed()")
        #note order here: get the mode before evaluating the field!
        return self.get_state() not in [PyTango.DevState.FAULT,PyTango.DevState.UNKNOWN] and self.get_swb_mode() and self.get_current_and_field() and not self.field_out_of_range

    #

    def read_fieldB(self, attr):
        self.debug_stream("In read_fieldB()")
        #Dipoles and solenoids both have allowed component= 0
        #For dipoles, we store theta (theta * BRho) in zeroth element of fieldX (fieldX normalised)
        #For solenoids, we store Bs there
        #BUT in reality zeroth element is zero. See wiki page for details.
        if self.allowed_component == 0:
            attr.set_value(self.convert_dipole_vector(self.fieldB))
        else:
            attr.set_value(self.fieldB)

    def is_fieldB_allowed(self, attr):
        self.debug_stream("In read_fieldB_allowed()")
        #note order here: get the mode before evaluating the field!
        return self.get_state() not in [PyTango.DevState.FAULT,PyTango.DevState.UNKNOWN] and self.get_swb_mode() and self.hasCalibData[self.Mode] and self.get_current_and_field() and not self.field_out_of_range 

    #

    def read_fieldANormalised(self, attr):
        self.debug_stream("In read_fieldANormalised()")
        #Dipoles and solenoids both have allowed component= 0
        #For dipoles, we store theta (theta * BRho) in zeroth element of fieldX (fieldX normalised)
        #For solenoids, we store Bs there
        #BUT in reality zeroth element is zero. See wiki page for details.
        if self.allowed_component == 0:
            attr.set_value(self.convert_dipole_vector(self.fieldANormalised))
        else:
            attr.set_value(self.fieldANormalised)

    def is_fieldANormalised_allowed(self, attr):
        self.debug_stream("In read_fieldANormalised_allowed()")
        #note order here: get the mode before evaluating the field!
        return self.get_state() not in [PyTango.DevState.FAULT,PyTango.DevState.UNKNOWN] and self.get_swb_mode() and self.hasCalibData[self.Mode] and self.get_current_and_field() and not self.field_out_of_range

    #

    def read_fieldBNormalised(self, attr):
        self.debug_stream("In read_fieldBNormalised()")
        #Dipoles and solenoids both have allowed component= 0
        #For dipoles, we store theta (theta * BRho) in zeroth element of fieldX (fieldX normalised)
        #For solenoids, we store Bs there
        #BUT in reality zeroth element is zero. See wiki page for details.
        if self.allowed_component == 0:
            attr.set_value(self.convert_dipole_vector(self.fieldBNormalised))
        else:
            attr.set_value(self.fieldBNormalised)

    def is_fieldBNormalised_allowed(self, attr):
        self.debug_stream("In read_fieldBNormalised_allowed()")
        #note order here: get the mode before evaluating the field!
        return self.get_state() not in [PyTango.DevState.FAULT,PyTango.DevState.UNKNOWN] and self.get_swb_mode() and self.hasCalibData[self.Mode] and self.get_current_and_field() and not self.field_out_of_range 

    #

    def read_BRho(self, attr):
        self.debug_stream("In read_BRho()")
        attr.set_value(self.BRho)

    def read_energy(self, attr):
        self.debug_stream("In read_energy()")
        attr.set_value(self.energy_r)
        if self.energy_w == None: #true at initialise
            self.energy_w = self.energy_r
            attr.set_write_value(self.energy_w)

    def write_energy(self, attr):
        self.debug_stream("In write_energy()")
        self.energy_r = attr.get_write_value()
        self.calculate_brho()

        #If energy changes, limits on k1 etc will also change
        if self.hasCalibData[self.Mode]:
            self.set_field_limits()

        #If energy changes, current or field must also change
        #Can only do something if calibrated
        if self.hasCalibData[self.Mode]:
            if self.scaleField:
                self.debug_stream("Energy (Brho) changed to %f (%f): will recalculate current to preserve field" % (self.energy_r, self.BRho) )
                #since brho changed, need to recalc the field
                if self.Tilt == 0 and self.Mode != "Y_CORRECTOR":
                    self.fieldB[self.allowed_component]  = self.MainFieldComponent_r * self.BRho
                else:
                    self.fieldA[self.allowed_component]  = self.MainFieldComponent_r * self.BRho
                self.set_current \
                    = calculate_current(self.allowed_component, self.currentsmatrix[self.Mode], self.fieldsmatrix[self.Mode], self.BRho,  self.PolTimesOrient, self.Tilt, self.Mode, self.Length, self.fieldA, self.fieldB, False)
                ###########################################################
                #Set the current on the ps
                self.set_ps_current()
            else:
                self.debug_stream("Energy changed: will recalculate fields for the PS current")
                (success, self.MainFieldComponent_r, self.MainFieldComponent_w, self.fieldA, self.fieldANormalised, self.fieldB, self.fieldBNormalised) \
                    = calculate_fields(self.allowed_component, self.currentsmatrix[self.Mode], self.fieldsmatrix[self.Mode], self.BRho,  self.PolTimesOrient, self.Tilt, self.Mode, self.Length, self.actual_current, self.set_current, is_sole=False)


    def is_energy_allowed(self, attr):
        return self.get_state() not in [PyTango.DevState.FAULT,PyTango.DevState.UNKNOWN]

    #

    def read_fixNormFieldOnEnergyChange(self, attr):
        self.debug_stream("In read_changeNormFieldWithEnergy()")
        attr.set_value(self.scaleField)
        attr.set_write_value(self.scaleField)

    def write_fixNormFieldOnEnergyChange(self, attr):
        self.debug_stream("In write_changeNormFieldWithEnergy()")
        self.scaleField = attr.get_write_value()

    #

    def read_MainFieldComponent(self, attr):
        self.debug_stream("In read_MainFieldComponent()")
        if self.hasCalibData[self.Mode] == True:
            attr_MainFieldComponent_read = self.MainFieldComponent_r
            attr.set_value(attr_MainFieldComponent_read)
            attr.set_write_value(self.MainFieldComponent_w)

    def write_MainFieldComponent(self, attr):
        self.debug_stream("In write_MainFieldComponent()")
        if self.hasCalibData[self.Mode]:
            attr_MainFieldComponent_write=attr.get_write_value()
            self.MainFieldComponent_w = attr_MainFieldComponent_write
            #Note that we set the component of the field vector directly here, but
            #calling calculate_fields will in turn set the whole vector, including this component again
            if self.Tilt == 0 and self.Mode != "Y_CORRECTOR":
                self.fieldB[self.allowed_component]  = attr_MainFieldComponent_write * self.BRho
            else:
                self.fieldA[self.allowed_component]  = attr_MainFieldComponent_write * self.BRho

            self.set_current \
                = calculate_current(self.allowed_component, self.currentsmatrix[self.Mode], self.fieldsmatrix[self.Mode], self.BRho,  self.PolTimesOrient, self.Tilt, self.Mode, self.Length, self.fieldA, self.fieldB, False)
            ###########################################################
            #Set the current on the ps
            self.set_ps_current()

    def is_MainFieldComponent_allowed(self, attr):
        return self.get_state() not in [PyTango.DevState.FAULT,PyTango.DevState.UNKNOWN] and self.get_swb_mode() and self.hasCalibData[self.Mode] and self.get_current_and_field() and not self.field_out_of_range

    #

    def read_IntMainFieldComponent(self, attr):
        self.debug_stream("In read_IntMainFieldComponent()")
        if self.hasCalibData[self.Mode] == True:
            attr_IntMainFieldComponent_read = self.MainFieldComponent_r * self.Length
            attr.set_value(attr_IntMainFieldComponent_read)

    def is_IntMainFieldComponent_allowed(self, attr):
        return self.get_state() not in [PyTango.DevState.FAULT,PyTango.DevState.UNKNOWN]  and self.hasCalibData[self.Mode] and self.get_current_and_field() and self.get_swb_mode() and not self.field_out_of_range


class TrimCircuitClass(PyTango.DeviceClass):

    device_property_list = {
        'TrimExcitationCurveCurrents_normal_sextupole':
        [PyTango.DevVarStringArray,
         "Measured calibration field or current for each multipole",
         [ [] ] ],
        'TrimExcitationCurveCurrents_normal_quadrupole':
        [PyTango.DevVarStringArray,
         "Measured calibration field or current for each multipole",
         [ [] ] ],
        'TrimExcitationCurveCurrents_skew_quadrupole':
        [PyTango.DevVarStringArray,
         "Measured calibration field or current for each multipole",
         [ [] ] ],
        'TrimExcitationCurveCurrents_x_corrector':
        [PyTango.DevVarStringArray,
         "Measured calibration field or current for each multipole",
         [ [] ] ],
        'TrimExcitationCurveCurrents_y_corrector':
        [PyTango.DevVarStringArray,
         "Measured calibration field or current for each multipole",
         [ [] ] ],
        'TrimExcitationCurveFields_normal_sextupole':
        [PyTango.DevVarStringArray,
         "Measured calibration field or current for each multipole",
         [ [] ] ],
        'TrimExcitationCurveFields_normal_quadrupole':
        [PyTango.DevVarStringArray,
         "Measured calibration field or current for each multipole",
         [ [] ] ],
        'TrimExcitationCurveFields_skew_quadrupole':
        [PyTango.DevVarStringArray,
         "Measured calibration field or current for each multipole",
         [ [] ] ],
        'TrimExcitationCurveFields_x_corrector':
        [PyTango.DevVarStringArray,
         "Measured calibration field or current for each multipole",
         [ [] ] ],
        'TrimExcitationCurveFields_y_corrector':
        [PyTango.DevVarStringArray,
         "Measured calibration field or current for each multipole",
         [ [] ] ],
        'PowerSupplyProxy':
        [PyTango.DevString,
         "Associated powersupply",
         [ "not set" ] ],
        'SwitchBoardProxy':
        [PyTango.DevString,
         "Associated switchboard",
         [ "not set" ] ],
        'MagnetProxies':
        [PyTango.DevVarStringArray,
         "List of magnets on this circuit",
         [ "not set" ] ],
        }
    
    #Attribute definitions
    attr_list = {
        'mode':
        [[PyTango.DevString,
          PyTango.SCALAR,
          PyTango.READ],
         {
             'label': "SWB mode",
             'doc': "Mode as set in the SWB device. Can be: SEXTUPOLE, NORMAL_QUADRUPOLE, SKEW_QUADRUPOLE, X_CORRECTOR, Y_CORRECTOR"
         } ],
        'currentSet':
        [[PyTango.DevFloat,
          PyTango.SCALAR,
          PyTango.READ],
         {
             'label': "set current",
             'unit': "A", 
             'doc': "Set current on PS (attribute write value)",
             'format': "%6.5f"
         } ],
        'currentActual':
        [[PyTango.DevFloat,
          PyTango.SCALAR,
          PyTango.READ],
         {
             'label': "actual current",
             'unit': "A",  
             'doc': "Read current on PS",
             'format': "%6.5f"
         } ],
        'fieldA':
        [[PyTango.DevFloat,
          PyTango.SPECTRUM,
          PyTango.READ, 10],
         {
             'label': "A_n",
             'unit': "T m^1-n",
             'doc': "field A (skew) components",
             'format': "%6.5e"
         } ],
        'fieldB':
        [[PyTango.DevFloat,
          PyTango.SPECTRUM,
          PyTango.READ, 10],
         {
            'label': "B_n",
            'unit': "T m^1-n",
             'doc': "field B (skew) components",
             'format': "%6.5e"
         } ],
        'fieldANormalised':
        [[PyTango.DevFloat,
          PyTango.SPECTRUM,
          PyTango.READ, 10],
        {
            'label': "e/p A_n",
            'unit': "m^-n",
            'doc': "field A normalised (skew) components",
            'format': "%6.5e"
        } ],
        'fieldBNormalised':
        [[PyTango.DevFloat,
          PyTango.SPECTRUM,
          PyTango.READ, 10],
         {
             'label': "e/p B_n",
             'unit': "m^-n",
             'doc': "field B normalised (skew) components",
             'format': "%6.5e"
        } ],
        'energy':
        [[PyTango.DevFloat,
          PyTango.SCALAR,
          PyTango.READ_WRITE],
         {
             'label': "electron energy",
             'unit': "eV",
             'format': "%6.5e",
             'doc': "electron energy"
         } ],
        'fixNormFieldOnEnergyChange':
        [[PyTango.DevBoolean,
        PyTango.SCALAR,
          PyTango.READ_WRITE],
         {
             'label': "Preserve norm. field on energy change",
             'unit': "T/F",
             'doc': "If true, if the energy changes the current is recalculated in order to preserve the normalised field"
         } ],
        'BRho':
        [[PyTango.DevFloat,
          PyTango.SCALAR,
          PyTango.READ],
         {
             'label': "b.rho",
             'unit': "eV s m^1",
             'doc': "b.rho normalistion factor",
             'format': "%6.5e"
         } ],
        'MainFieldComponent':
        [[PyTango.DevDouble,
          PyTango.SCALAR,
          PyTango.READ_WRITE],
         {
             'format': "%6.6f"
         } ],
        'IntMainFieldComponent':
        [[PyTango.DevDouble,
          PyTango.SCALAR,
          PyTango.READ],
         {
             'format': "%6.6f"
         } ]
    }


def main():
    try:
        py = PyTango.Util(sys.argv)
        py.add_class(TrimCircuitClass,TrimCircuit,'TrimCircuit')

        U = PyTango.Util.instance()
        U.server_init()
        U.server_run()

    except PyTango.DevFailed,e:
        print '-------> Received a DevFailed exception:',e
    except Exception,e:
        print '-------> An unforeseen exception occured....',e

if __name__ == '__main__':
    main()
