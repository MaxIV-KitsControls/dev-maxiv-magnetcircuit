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
from magnetcircuitlib import calculate_fields, calculate_current
from processcalibrationlib import process_calibration_data

##############################################################################################################
#
class TrimCircuit (PyTango.Device_4Impl):

    _maxdim = 10 #Maximum number of multipole components

    def __init__(self,cl, name):
        PyTango.Device_4Impl.__init__(self,cl,name)
        self.debug_stream("In __init__()")
        TrimCircuit.init_device(self)


    def delete_device(self):
        self.debug_stream("In delete_device()")


    def init_device(self):
        self.debug_stream("In init_device()")
        self.set_state(PyTango.DevState.INIT)

        self.get_device_properties(self.get_device_class())

        #energy attribute eventually to be set by higher level device?
        self.energy_r = 100000000.0 #=100 MeV for testing, needs to be read from somewhere
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
        self.status_str_swb   = ""
        self.status_str_cal   = ""
        self.status_str_cfg   = ""
        self.IntFieldQ = PyTango.AttrQuality.ATTR_VALID

        #Proxy to switch board device
        self._swb_device = None
        self.Mode = None #this can be: octupole, sextupole, upright_q, skew_q, hor_corr, ver_corr
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
        #The switchboard mode determines the allowed field component to be controlled.
        #Note that in the multipole expansion we have:
        # 1 - dipole, 2 - quadrupole, 3 - sextupole, 4 - octupole
        #which of course is row 0-3 in our numpy array
        self.allowed_component = 0

        #process the calibration data into useful numpy arrays
        self.fieldsmatrix = {} #calibration data accessed via mode
        self.currentsmatrix = {}
        self.hasCalibData = {}

        #octupole
        (self.hasCalibData["octupole"], self.status_str_cal,  self.fieldsmatrix["octupole"],  self.currentsmatrix["octupole"]) \
            = process_calibration_data(self.TrimExcitationCurveCurrents_Octupole,self.TrimExcitationCurveFields_Octupole)
        #sextupole
        (self.hasCalibData["sextupole"], self.status_str_cal,  self.fieldsmatrix["sextupole"],  self.currentsmatrix["sextupole"]) \
            = process_calibration_data(self.TrimExcitationCurveCurrents_Sextupole,self.TrimExcitationCurveFields_Sextupole)
        #normal quadrupole
        (self.hasCalibData["upright_q"], self.status_str_cal,  self.fieldsmatrix["upright_q"],  self.currentsmatrix["upright_q"]) \
            = process_calibration_data(self.TrimExcitationCurveCurrents_Upright_Q,self.TrimExcitationCurveFields_Upright_Q)
        #skew quadrupole - fills An
        (self.hasCalibData["skew_q"], self.status_str_cal,  self.fieldsmatrix["skew_q"],  self.currentsmatrix["skew_q"]) \
            = process_calibration_data(self.TrimExcitationCurveCurrents_Skew_Q,self.TrimExcitationCurveFields_Skew_Q)
        #horizontal correction
        (self.hasCalibData["hor_corr"], self.status_str_cal,  self.fieldsmatrix["hor_corr"],  self.currentsmatrix["hor_corr"]) \
            = process_calibration_data(self.TrimExcitationCurveCurrents_Hor_Corr,self.TrimExcitationCurveFields_Hor_Corr)
        #vertical correction - fills An
        (self.hasCalibData["ver_corr"], self.status_str_cal,  self.fieldsmatrix["ver_corr"],  self.currentsmatrix["ver_corr"]) \
            = process_calibration_data(self.TrimExcitationCurveCurrents_Ver_Corr,self.TrimExcitationCurveFields_Ver_Corr)


    ###############################################################################
    #
    def calculate_brho(self):
        #Bρ = sqrt(T(T+2M0)/(qc0) where M0 = rest mass of the electron in MeV, q = 1 and c0 = speed of light Mm/s (mega m!) Energy is in eV to start.
        self.BRho = sqrt( self.energy_r/1000000.0 * (self.energy_r/1000000.0 + (2 * 0.000510998910) ) ) / (299.792458)

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
                newlength = int(magnet_device.get_property("Length")["Length"][0])
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

        print "in config type"
        att_vc = self.get_device_attr().get_attr_by_name("MainFieldComponent")
        multi_prop_vc = PyTango.MultiAttrProp()
        att_vc.get_properties(multi_prop_vc)
        multi_prop_vc.description = "The variable component of the field, which depends on the magnet type (k2 for sextupoles, k1 for quads, theta for dipoles, B_s for solenoids)"

        att_ivc = self.get_device_attr().get_attr_by_name("IntMainFieldComponent")
        multi_prop_ivc = PyTango.MultiAttrProp()
        att_ivc.get_properties(multi_prop_ivc)
        multi_prop_ivc.description = "The length integrated variable component of the field for quadrupoles and sextupoles (k2*l for sextupoles, k1*l for quads)."

        if self.Mode.lower() in ["skew_q","upright_q"]:
            self.allowed_component = 1
            multi_prop_vc.unit   = "m ^-2"
            multi_prop_vc.label  = "k1"
            multi_prop_ivc.unit  = "m ^-1"
            multi_prop_ivc.label = "length integrated k1"
        elif self.Mode.lower() == "sextupole":
            self.allowed_component = 2
            multi_prop_vc.unit   = "m ^-3"
            multi_prop_vc.label  = "k2"
            multi_prop_ivc.unit  = "m ^-2"
            multi_prop_ivc.label = "length integrated k2"
        elif self.Mode.lower() == "octupole":
            self.allowed_component = 3
            multi_prop_vc.unit   = "m ^-4"
            multi_prop_vc.label  = "k3"
            multi_prop_ivc.unit  = "m ^-3"
            multi_prop_ivc.label = "length integrated k3"
        elif self.Mode.lower() in ["hor_corr","ver_corr"]:
            self.allowed_component = 0
            multi_prop_vc.unit   = "rad"
            multi_prop_vc.label  = "theta"
            multi_prop_ivc.unit  = "rad m"
            multi_prop_ivc.label = "length integrated theta"
        else:
            self.status_str_cfg = 'Modet type invalid %s' % self.Mode
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


            minMainFieldComponent = calculate_fields(self.allowed_component, self.currentsmatrix[self.Mode], self.fieldsmatrix[self.Mode], self.BRho, self.PolTimesOrient, self.Tilt, self.Mode, self.Length,  self.mincurrent, False)[0]
            maxMainFieldComponent = calculate_fields(self.allowed_component, self.currentsmatrix[self.Mode], self.fieldsmatrix[self.Mode], self.BRho, self.PolTimesOrient, self.Tilt, self.Mode, self.Length,  self.maxcurrent, False)[0]

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
    def get_ps_state_and_current(self):

        if self.ps_device:
            try:

                self.status_str_ps = "Reading current from %s  " % self.PowerSupplyProxy  

                ps_state = self.ps_device.State()
                self.actual_current =  self.ps_device.Current

                #Just assume the set current is whatever is written on the ps device (could be written directly there!)
                self.set_current =  self.ps_device.read_attribute("Current").w_value

            except:
                self.status_str_ps = "Cannot read current on PS " + self.PowerSupplyProxy
                self.debug_stream(self.status_str_ps)
                ps_state = PyTango.DevState.FAULT

        else:
            self.status_str_ps = "Read current:  cannot get proxy to " + self.PowerSupplyProxy 
            ps_state = PyTango.DevState.FAULT

        return ps_state


    ##############################################################################################################
    #
    def get_swb_state_and_current(self):

        print "in get_swb_state_and_current"
        if self.swb_device:
            try:
                self.status_str_swb = "Reading SWB mode from %s " % self.SwitchBoardProxy  
                swb_state = self.swb_device.State()
                self.Mode =  self.swb_device.Mode

                print "SWB mode is ", self.Mode

                #whatever the mode is determines the type of behaviour of the trim coil (quad, sext, etc)
                #should maybe be event driven, not redetermine each time!
                if self.oldMode == None or self.Mode != self.oldMode:
                    print "mode changed"
                    self.oldMode=self.Mode
                    #set the allowed component, unit of k, etc
                    self.config_type() 
                    #set alarm levels on MainFieldComponent (etc) corresponding to the PS alarms
                    self.set_field_limits()

            except:
                self.status_str_swb = "Cannot read mode on SWB " + self.SwitchBoardProxy
                self.debug_stream(self.status_str_swb)
                swb_state = PyTango.DevState.FAULT

        else:
            self.status_str_swb = "Read mode:  cannot get proxy to " + self.SwitchBoardProxy
            swb_state = PyTango.DevState.FAULT

        return swb_state


    ##############################################################################################################
    #
    def always_executed_hook(self):
        self.debug_stream("In always_excuted_hook()")

        #Always check state of the SWB (ie the mode)
        swb_state = self.get_swb_state_and_current()

        if swb_state in ["PyTango.DevState.UNKNOWN","PyTango.DevState.ALARM""PyTango.DevState.FAULT"]:
            self.set_status("SwitchBoard Device is in state " + str(swb_state))
            self.set_state(swb_state)
            return


        print "mode is ", self.Mode

        #Always recalc fields for actual current. If the current changes we need to check how fields change.
        #NB if we change the i'th component we need to see how other components change as a result
        ps_state = self.get_ps_state_and_current()
        self.set_state(ps_state)
        
        #set status message
        msg = self.status_str_prop +"\n"+ self.status_str_cfg +"\n"+ self.status_str_cal +"\n"+ self.status_str_ps +"\n"+ self.status_str_swb 
        self.set_status(os.linesep.join([s for s in msg.splitlines() if s]))

        #calculate the actual and set fields, since used by many attribute readings
        if self.hasCalibData[self.Mode] and self.get_state() not in [PyTango.DevState.FAULT, PyTango.DevState.UNKNOWN]:
            (self.MainFieldComponent_r, self.MainFieldComponent_w, self.fieldA, self.fieldANormalised, self.fieldB, self.fieldBNormalised)  \
                = calculate_fields(self.allowed_component, self.currentsmatrix[self.Mode], self.fieldsmatrix[self.Mode], self.BRho, self.PolTimesOrient, self.Tilt, self.Mode, self.Length, self.actual_current, self.set_current, False)


        print "calculated fields ", self.MainFieldComponent_r, self.MainFieldComponent_w, self.fieldA, self.fieldANormalised, self.fieldB, self.fieldBNormalised

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
        return self.hasCalibData[self.Mode] and self.get_state() not in [PyTango.DevState.FAULT,PyTango.DevState.UNKNOWN]

    #

    def read_currentSet(self, attr):
        self.debug_stream("In read_currentSet()")
        attr.set_value(self.set_current)

    def is_currentCalculated_allowed(self, attr):
        return self.hasCalibData[self.Mode] and self.get_state() not in [PyTango.DevState.FAULT,PyTango.DevState.UNKNOWN]
       
    #

    def read_currentActual(self, attr):
        self.debug_stream("In read_currentActual()")
        attr.set_value(self.actual_current)

    def is_currentActual_allowed(self, attr):
        return self.get_state() not in [PyTango.DevState.FAULT,PyTango.DevState.UNKNOWN]

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
        return self.hasCalibData[self.Mode] and self.get_state() not in [PyTango.DevState.FAULT,PyTango.DevState.UNKNOWN]

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
        return self.hasCalibData[self.Mode] and self.get_state() not in [PyTango.DevState.FAULT,PyTango.DevState.UNKNOWN]

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
        return self.hasCalibData[self.Mode] and self.get_state() not in [PyTango.DevState.FAULT,PyTango.DevState.UNKNOWN]

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
        return self.hasCalibData[self.Mode] and self.get_state() not in [PyTango.DevState.FAULT,PyTango.DevState.UNKNOWN]

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
        #Only do something if the current from the PS is known
        if self.scaleField:
            self.debug_stream("Energy (Brho) changed to %f (%f): will recalculate current to preserve field" % (self.energy_r, self.BRho) )
            #since brho changed, need to recalc the field
            if self.Tilt == 0 and self.Mode != "ver_corr":
                self.fieldB[self.allowed_component]  = self.MainFieldComponent_r * self.BRho
            else:
                self.fieldA[self.allowed_component]  = self.MainFieldComponent_r * self.BRho
            #now find the current if possible
            if self.hasCalibData[self.Mode]:
                self.set_current \
                    = calculate_current(self.allowed_component, self.currentsmatrix[self.Mode], self.fieldsmatrix[self.Mode], self.BRho,  self.PolTimesOrient, self.Tilt, self.Mode, self.Length, self.fieldA, self.fieldB, False)
                ###########################################################
                #Set the current on the ps
                self.set_ps_current()
        else:
            self.debug_stream("Energy changed: will recalculate fields for the PS current")
            if self.hasCalibData[self.Mode]:
                (self.MainFieldComponent_r, self.MainFieldComponent_w, self.fieldA, self.fieldANormalised, self.fieldB, self.fieldBNormalised) \
                    = calculate_fields(self.allowed_component, self.currentsmatrix[self.Mode], self.fieldsmatrix[self.Mode], self.BRho,  self.PolTimesOrient, self.Tilt, self.Mode, self.Length, self.actual_current, self.set_current, False)
                print self.MainFieldComponent_r, self.MainFieldComponent_w, self.fieldA, self.fieldANormalised, self.fieldB, self.fieldBNormalised


    def is_energy_allowed(self, attr):
        return self.hasCalibData[self.Mode] and self.get_state() not in [PyTango.DevState.FAULT,PyTango.DevState.UNKNOWN]

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
            if self.Tilt == 0 and self.Mode != "ver_corr":
                self.fieldB[self.allowed_component]  = attr_MainFieldComponent_write * self.BRho
            else:
                self.fieldA[self.allowed_component]  = attr_MainFieldComponent_write * self.BRho

            self.set_current \
                = calculate_current(self.allowed_component, self.currentsmatrix[self.Mode], self.fieldsmatrix[self.Mode], self.BRho,  self.PolTimesOrient, self.Tilt, self.Mode, self.Length, self.fieldA, self.fieldB, False)
            ###########################################################
            #Set the current on the ps
            self.set_ps_current()

    def is_MainFieldComponent_allowed(self, attr):
        return self.hasCalibData[self.Mode] and self.get_state() not in [PyTango.DevState.FAULT,PyTango.DevState.UNKNOWN]

    #

    def read_IntMainFieldComponent(self, attr):
        self.debug_stream("In read_IntMainFieldComponent()")
        if self.hasCalibData[self.Mode] == True:
            attr_IntMainFieldComponent_read = self.MainFieldComponent_r * self.Length
            attr.set_value(attr_IntMainFieldComponent_read)
            attr.set_quality(self.IntFieldQ)

    def is_IntMainFieldComponent_allowed(self, attr):
        return self.hasCalibData[self.Mode] and self.get_state() not in [PyTango.DevState.FAULT,PyTango.DevState.UNKNOWN]


class TrimCircuitClass(PyTango.DeviceClass):

    #Class Properties
    class_property_list = {

        'TrimExcitationCurveCurrents_Sextupole':
        [PyTango.DevVarStringArray,
         "Measured calibration currents for each multipole",
         [ [] ] ],
        'TrimExcitationCurveFields_Sextupole':
        [PyTango.DevVarStringArray,
         "Measured calibration fields for each multipole",
         [ [] ] ],

        'TrimExcitationCurveCurrents_Octupole':
        [PyTango.DevVarStringArray,
         "Measured calibration currents for each multipole",
         [ [] ] ],
        'TrimExcitationCurveFields_Octupole':
        [PyTango.DevVarStringArray,
         "Measured calibration fields for each multipole",
         [ [] ] ],

        'TrimExcitationCurveCurrents_Upright_Q':
        [PyTango.DevVarStringArray,
         "Measured calibration currents for each multipole",
         [ [] ] ],
        'TrimExcitationCurveFields_Upright_Q':
        [PyTango.DevVarStringArray,
         "Measured calibration fields for each multipole",
         [ [] ] ],

        'TrimExcitationCurveCurrents_Skew_Q':
        [PyTango.DevVarStringArray,
         "Measured calibration currents for each multipole",
         [ [] ] ],
        'TrimExcitationCurveFields_Skew_Q':
        [PyTango.DevVarStringArray,
         "Measured calibration fields for each multipole",
         [ [] ] ],

        'TrimExcitationCurveCurrents_Hor_Corr':
        [PyTango.DevVarStringArray,
         "Measured calibration currents for each multipole",
         [ [] ] ],
        'TrimExcitationCurveFields_Hor_Corr':
        [PyTango.DevVarStringArray,
         "Measured calibration fields for each multipole",
         [ [] ] ],

        'TrimExcitationCurveCurrents_Ver_Corr':
        [PyTango.DevVarStringArray,
         "Measured calibration currents for each multipole",
         [ [] ] ],
        'TrimExcitationCurveFields_Ver_Corr':
        [PyTango.DevVarStringArray,
         "Measured calibration fields for each multipole",
         [ [] ] ],

    }


    #Device Properties
    device_property_list = {

        #override class level calibration if given

        'TrimExcitationCurveCurrents_Sextupole':
        [PyTango.DevVarStringArray,
         "Measured calibration currents for each multipole",
         [ [] ] ],
        'TrimExcitationCurveFields_Sextupole':
        [PyTango.DevVarStringArray,
         "Measured calibration fields for each multipole",
         [ [] ] ],

        'TrimExcitationCurveCurrents_Octupole':
        [PyTango.DevVarStringArray,
         "Measured calibration currents for each multipole",
         [ [] ] ],
        'TrimExcitationCurveFields_Octupole':
        [PyTango.DevVarStringArray,
         "Measured calibration fields for each multipole",
         [ [] ] ],

        'TrimExcitationCurveCurrents_Upright_Q':
        [PyTango.DevVarStringArray,
         "Measured calibration currents for each multipole",
         [ [] ] ],
        'TrimExcitationCurveFields_Upright_Q':
        [PyTango.DevVarStringArray,
         "Measured calibration fields for each multipole",
         [ [] ] ],

        'TrimExcitationCurveCurrents_Skew_Q':
        [PyTango.DevVarStringArray,
         "Measured calibration currents for each multipole",
         [ [] ] ],
        'TrimExcitationCurveFields_Skew_Q':
        [PyTango.DevVarStringArray,
         "Measured calibration fields for each multipole",
         [ [] ] ],

        'TrimExcitationCurveCurrents_Hor_Corr':
        [PyTango.DevVarStringArray,
         "Measured calibration currents for each multipole",
         [ [] ] ],
        'TrimExcitationCurveFields_Hor_Corr':
        [PyTango.DevVarStringArray,
         "Measured calibration fields for each multipole",
         [ [] ] ],

        'TrimExcitationCurveCurrents_Ver_Corr':
        [PyTango.DevVarStringArray,
         "Measured calibration currents for each multipole",
         [ [] ] ],
        'TrimExcitationCurveFields_Ver_Corr':
        [PyTango.DevVarStringArray,
         "Measured calibration fields for each multipole",
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
         } ],
        'currentSet':
        [[PyTango.DevFloat,
          PyTango.SCALAR,
          PyTango.READ],
         {
             'label': "set current",
             'unit': "A",
         } ],
        'currentActual':
        [[PyTango.DevFloat,
          PyTango.SCALAR,
          PyTango.READ],
         {
             'label': "actual current",
             'unit': "A",
         } ],
        'fieldA':
        [[PyTango.DevFloat,
          PyTango.SPECTRUM,
          PyTango.READ, 10],
         {
             'label': "A_n",
             'unit': "T m^1-n",
         } ],
        'fieldB':
        [[PyTango.DevFloat,
          PyTango.SPECTRUM,
          PyTango.READ, 10],
         {
            'label': "B_n",
            'unit': "T m^1-n",
         } ],
        'fieldANormalised':
        [[PyTango.DevFloat,
          PyTango.SPECTRUM,
          PyTango.READ, 10],
        {
            'label': "e/p A_n",
            'unit': "m^-n",
         } ],
        'fieldBNormalised':
        [[PyTango.DevFloat,
          PyTango.SPECTRUM,
          PyTango.READ, 10],
         {
             'label': "e/p B_n",
             'unit': "m^-n",
        } ],
        'energy':
        [[PyTango.DevFloat,
          PyTango.SCALAR,
          PyTango.READ_WRITE],
         {
             'label': "electron energy",
             'unit': "eV",
             'format': "%6.2e",
         } ],
        'fixNormFieldOnEnergyChange':
        [[PyTango.DevBoolean,
        PyTango.SCALAR,
          PyTango.READ_WRITE],
         {
             'label': "Preserve norm. field on energy change",
             'unit': "T/F",
         } ],
        'BRho':
        [[PyTango.DevFloat,
          PyTango.SCALAR,
          PyTango.READ],
         {
             'label': "b.rho",
             'unit': "eV s m^1",
         } ],
        'MainFieldComponent':
        [[PyTango.DevDouble,
          PyTango.SCALAR,
          PyTango.READ_WRITE],
         {
         } ],
        'IntMainFieldComponent':
        [[PyTango.DevDouble,
          PyTango.SCALAR,
          PyTango.READ],
         {
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