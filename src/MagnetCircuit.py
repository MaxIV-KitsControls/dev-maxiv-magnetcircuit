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
from magnetcircuitlib import calculate_fields, calculate_current
from cycling_statemachine.magnetcycling import MagnetCycling


#This power supply object is used by the cycling machine
#
class Wrapped_PS_Device(object):

    #pass ps device
    def __init__(self, psdev):
        self.psdev  = psdev

    def setCurrent(self, value):
        self.psdev.write_attribute("Current", value)

    #def getCurrent(self):
    #    return self.psdev.read_attribute("Current").w_value

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
class MagnetCircuit (PyTango.Device_4Impl):

    _maxdim = 10 #Maximum number of multipole components

    def __init__(self,cl, name):
        PyTango.Device_4Impl.__init__(self,cl,name)
        self.debug_stream("In __init__()")
        MagnetCircuit.init_device(self)


    def delete_device(self):
        self.debug_stream("In delete_device()")


    def init_device(self):
        self.debug_stream("In init_device()")
        self.set_state(PyTango.DevState.INIT)

        self.get_device_properties(self.get_device_class())

        self.energy_r = 100000000.0 #=100 MeV for testing, needs to be ready from somewhere
        self.energy_w = None
        self.calculate_brho() #a conversion factor that depends on energy

        #depending on the magnet type, variable component can be k1, k2, etc
        self.MainFieldComponent_w = None

        #sets whether field is scaled with energy
        self.scaleField=False

        #Some status strings
        self.status_str_prop  = ""
        self.status_str_ps    = ""
        self.status_str_cal   = ""
        self.status_str_cyc   = ""
        self.status_str_cfg   = ""
        self.cyclingphase = "Cycling not set up"
        self.hasCalibData=False 

        #Proxy to power supply device
        self._ps_device = None

        #read the properties from the Tango DB, not including calib data (type, length, powersupply proxy...)
        self.read_properties()
        #
        #The magnet type determines which row in the numpy field array we are interested in to control
        #Note that in the multipole expansion we have:
        # 1 - dipole, 2 - quadrupole, 3 - sextupole, 4 - octupole
        #which of course is row 0-3 in our numpy array
        self.config_type()

        #set limits on current
        self.set_current_limits()

        #read calibration data
        self.read_calibration_data()

        #set alarm levels on MainFieldComponent (etc) corresponding to the PS alarms
        if self.hasCalibData:
            self.set_field_limits()

        #from the PS limits, if available, set cycling boundaries
        self.setup_cycler()

        self.set_state(PyTango.DevState.ON)

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

    ##############################################################################################################
    #
    def read_properties(self):

        #Check length, tilt, type of actual magnet devices (should all be the same on one circuit)
        #magnet_property_types = {"Length": float, "Tilt": int, "Type": str, "Polarity": int, "Orientation": int}
        #Deal with polarity and orientation separately

        magnet_property_types = {"Length": float, "Tilt": int, "Type": str}

        problematic_devices = set()  # let's be optimistic
        for (i, magnet_device_name) in enumerate(self.MagnetProxies):
            magnet_device = PyTango.DeviceProxy(magnet_device_name)
            for prop, type_ in magnet_property_types.items():
                try:
                    prop_value = type_(magnet_device.get_property(prop)[prop][0])
                except ValueError,IndexError:
                    # undefined property gives an empty list as a value
                    print >> self.log_fatal, ("Couldn't read property '%s' from magnet device '%s'; "+
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

            #special case for polarity and orientation, check only the product
            newpolarity       = int(magnet_device.get_property("Polarity")["Polarity"][0])
            neworientation    = int(magnet_device.get_property("Orientation")["Orientation"][0])
            newpoltimesorient = newpolarity * neworientation
            if i == 0:
                self.PolTimesOrient = newpolarity * neworientation
                if self.PolTimesOrient != newpoltimesorient:
                    print >> self.log_fatal, ('Found magnets of different polarity times orientation (%s cf %s) on same circuit (%s)'
                                              % (self.PolTimesOrient, newpoltimesorient, magnet_device_name))
                    problematic_devices.add(magnet_device_name)

        # If there were any issues go to FAULT
        if problematic_devices:
            self.status_str_prop = 'Cannot start due to issues with magnet device(s): %s. Fix and do INIT' % ", ".join(problematic_devices)
            self.debug_stream(self.status_str_prop)
            self.set_state( PyTango.DevState.FAULT )
        else:
            self.debug_stream("Magnet length/type/tilt/polarity times orientation :  %f/%s/%d/%d " % (self.Length, self.Type, self.Tilt, self.PolTimesOrient))
        

    ##############################################################################################################
    #
    def config_type(self):
            
        att_vc = self.get_device_attr().get_attr_by_name("MainFieldComponent")
        multi_prop_vc = PyTango.MultiAttrProp()
        att_vc.get_properties(multi_prop_vc)
        multi_prop_vc.description = "The variable component of the field, which depends on the magnet type (k2 for sextupoles, k1 for quads, theta for dipoles)"

        att_ivc = self.get_device_attr().get_attr_by_name("IntMainFieldComponent")
        multi_prop_ivc = PyTango.MultiAttrProp()
        att_ivc.get_properties(multi_prop_ivc)
        multi_prop_ivc.description = "The length integrated variable component of the field for quadrupoles and sextupoles (k2*l for sextupoles, k1*l for quads). Just theta again for the dipoles"

        if self.Type in ["hkick","vkick","sole"]:
            #h and vkick also here using small theta. Large theta for bends.
            self.allowed_component = 0
            multi_prop_vc.unit   = "m ^-3"
            multi_prop_vc.label  = "k2"
            multi_prop_ivc.unit  = "m ^-2"
            multi_prop_ivc.label = "length integrated k2"
        elif self.Type == "csrcsbend":
            self.allowed_component = 0
            multi_prop_vc.unit   = "rad"
            multi_prop_vc.label  = "theta"
            multi_prop_ivc.unit  = "rad m"
            multi_prop_ivc.label = "length integrated theta"
        elif self.Type == "kquad":
            self.allowed_component = 1
            multi_prop_vc.unit   = "m ^-2"
            multi_prop_vc.label  = "k1"
            multi_prop_ivc.unit  = "m ^-1"
            multi_prop_ivc.label = "length integrated k1"
        elif self.Type == "ksext":
            self.allowed_component = 2
            multi_prop_vc.unit   = "m ^-3"
            multi_prop_vc.label  = "k2"
            multi_prop_ivc.unit  = "m ^-2"
            multi_prop_ivc.label = "length integrated k2"
        else:
            self.status_str_cfg = 'Magnet type invalid %s' % self.Type
            self.debug_stream(self.status_str_cfg)
            self.set_state( PyTango.DevState.FAULT )
            return

        att_vc.set_properties(multi_prop_vc)
        att_ivc.set_properties(multi_prop_ivc)


    ##############################################################################################################
    #
    def read_calibration_data(self):

        #try to read calibration data and power supply status
        try:
            #Check dimensions of current and field calibration data
            #(Should be n arrays of field values for n arrays of current values)
            if  len(self.ExcitationCurveCurrents) != len(self.ExcitationCurveFields):
                self.set_state( PyTango.DevState.FAULT )
                self.status_str_cal = 'Incompatible current and field calibration data'
                return

            #Read calib data from property if exists. No information corresponds to [""]
            if  self.ExcitationCurveCurrents[0] == '' or  self.ExcitationCurveCurrents[0] == 'not set':
                self.status_str_cal = "Field-current calibration data not available"
                return

            self.hasCalibData=True
            self.status_str_cal = "Field-current calibration data available"

            #Make numpy arrays for field and currents for each multipole component. 
            #At this point the calibration data are strings with comma separated values. Get the length by counting commas!
            array_length = self.ExcitationCurveCurrents[0].count(",")+1
            pos_fieldsmatrix   = np.empty(shape=(self._maxdim,array_length), dtype=float)
            pos_currentsmatrix = np.empty(shape=(self._maxdim,array_length), dtype=float)

            #Calibration points are for positive currents only, but full calibration curve should go negative. 
            #Make "reflected" arrays for negative currents and opposite sign on the fields, then merge the two later below
            neg_fieldsmatrix   = np.empty(shape=(self._maxdim,array_length-1), dtype=float)
            neg_currentsmatrix = np.empty(shape=(self._maxdim,array_length-1), dtype=float)

            self.fieldsmatrix   = np.empty(shape=(self._maxdim,(2*array_length)-1), dtype=float)
            self.currentsmatrix = np.empty(shape=(self._maxdim,(2*array_length)-1), dtype=float)
            self.fieldsmatrix[:] = np.NAN
            self.currentsmatrix[:] = np.NAN

            #Fill the numpy arrays, but first horrible conversion of list of chars to floats
            self.debug_stream("Multipole dimension %d " % len(self.ExcitationCurveCurrents))
            
            for i in range (0,len(self.ExcitationCurveCurrents)):
                MeasuredFields_l = []
                MeasuredCurrents_l = []
                #PJB hack since I use a string to start with like "[1,2,3]" No way to store a matrix of floats?
                if len(self.ExcitationCurveCurrents[i])>0:
                    #need to sort the currents and fields by absolute values for interpolation to work later
                    MeasuredFields_l   =  sorted([float(x) for x in "".join(self.ExcitationCurveFields[i][1:-1]).split(",")],key=abs)
                    MeasuredCurrents_l =  sorted([float(x) for x in "".join(self.ExcitationCurveCurrents[i][1:-1]).split(",")],key=abs)
                    pos_currentsmatrix[i] = MeasuredCurrents_l
                    pos_fieldsmatrix[i]   = MeasuredFields_l
                    
                #Check if the current is zero for the first entry, force the field to be zero as well
                #set zero point
                if pos_currentsmatrix[i][0] < 0.01:  #check abs?
                    pos_currentsmatrix[i][0] = 0.0
                    pos_fieldsmatrix[i][0] = 0.0
                #force current to be zero for first entry? NEED TO CHECK FOR BC1
                #pos_currentsmatrix[i][0] = 0.0

                #Also here merge the positive and negative ranges into the final array
                neg_fieldsmatrix[i]   = (-pos_fieldsmatrix[i][1:])[::-1]
                neg_currentsmatrix[i] = (-pos_currentsmatrix[i][1:])[::-1]
                #
                self.currentsmatrix[i] = np.concatenate((neg_currentsmatrix[i],pos_currentsmatrix[i]),axis=0)
                self.fieldsmatrix[i]   = np.concatenate((neg_fieldsmatrix[i],pos_fieldsmatrix[i]),axis=0)
            
        except ValueError:
            self.status_str_cal = 'Error reading calibration data from TangoDB'
            self.set_status(self.status_str_cal)
            self.debug_stream(self.status_str_cal)
            self.set_state(PyTango.DevState.FAULT)


    ##############################################################################################################
    #
    def setup_cycler(self):

        self._cycler = None
        self.status_str_cyc = ""

        #The cycling varies the current from min and max a number of times.
        #Need to get the current limits from the PS device; number of iterations and wait time can be properties

        if self.maxcurrent == None or self.mincurrent == None:
            self.status_str_cyc = 'Setup cycling: cannot read current limits from PS ' + self.PowerSupplyProxy
            self.debug_stream(self.status_str_cyc)
            return

        if self.ps_device:
            self.wrapped_ps_device = Wrapped_PS_Device(self.ps_device)
            self._cycler =  MagnetCycling(self.wrapped_ps_device, self.maxcurrent, self.mincurrent, 5.0, 4)
        else:
            self.status_str_cyc = "Setup cycling: cannot get proxy to %s " % self.PowerSupplyProxy 
            self.set_state(PyTango.DevState.FAULT)


    ##############################################################################################################
    #
    def set_current_limits(self):

        self.mincurrent = self.maxcurrent = None
        try:

            maxcurrent_s = self.ps_device.get_attribute_config("Current").max_value
            mincurrent_s = self.ps_device.get_attribute_config("Current").min_value

            if maxcurrent_s == 'Not specified' or mincurrent_s == 'Not specified':
                self.debug_stream("Current limits not specified, cannot do cycling") #! We assume if there are limits then they are good!

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
            minMainFieldComponent = calculate_fields(self.allowed_component, self.currentsmatrix, self.fieldsmatrix, self.BRho, self.PolTimesOrient, self.Tilt, self.Length,  self.mincurrent)[0]
            maxMainFieldComponent = calculate_fields(self.allowed_component, self.currentsmatrix, self.fieldsmatrix, self.BRho, self.PolTimesOrient, self.Tilt, self.Length,  self.maxcurrent)[0]
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

                self.status_str_ps = "Reading current from %s " % self.PowerSupplyProxy  

                ps_state = self.ps_device.State()
                self.actual_current =  self.ps_device.Current

                #Just assume the calculated current is whatever we wrote to the ps device
                self.calc_current =  self.ps_device.read_attribute("Current").w_value

            except:
                self.status_str_ps = "Cannot read current on PS " + self.PowerSupplyProxy
                self.debug_stream(self.status_str_ps)
                self._cycler = None
                self.cyclingphase = "Cycling not set up"
                ps_state = PyTango.DevState.FAULT

        else:
            self.status_str_ps = "Read current:  cannot get proxy to " + self.PowerSupplyProxy 
            self._cycler = None   
            self.cyclingphase = "Cycling not set up"
            ps_state = PyTango.DevState.FAULT

        return ps_state


    ##############################################################################################################
    #
    def always_executed_hook(self):
        self.debug_stream("In always_excuted_hook()")

        #Always recalc fields for actual current. If the current changes we need to check how fields change.
        #NB if we change the i'th component we need to see how other components change as a result
        ps_state = self.get_ps_state_and_current()

        #calculate the fields, since used by many attribute readings
        if self.hasCalibData and self.get_state() not in [PyTango.DevState.FAULT, PyTango.DevState.UNKNOWN]:
            (self.MainFieldComponent_r, self.fieldA, self.fieldANormalised, self.fieldB, self.fieldBNormalised)  \
                = calculate_fields(self.allowed_component, self.currentsmatrix, self.fieldsmatrix, self.BRho, self.PolTimesOrient, self.Tilt, self.Length, self.actual_current)

        #check phase of magnet cycling (may need to setup cycler again)
        if self._cycler is None: 
            self.set_current_limits()
            self.setup_cycler()
        if self._cycler is None: 
            self.cyclingphase  = "Cycling not set up"
        else:
            self.cyclingphase  = self._cycler.phase

        #Generally the circuit should echo the ps state
        #If we are in RUNNING, ie cycling, stay there unless ps goes to fault
        if self.get_state() == PyTango.DevState.RUNNING and ps_state in [PyTango.DevState.ON, PyTango.DevState.MOVING]:
            self.debug_stream("Currently RUNNING")
            #if we are running state but cycling has stopped, go back to ps state
            if  "NOT CYCLING" in self.cyclingphase:
                self.set_state(ps_state)
        else:
            self.set_state(ps_state)
        
        #set status message
        msg = self.status_str_prop +"\n"+ self.status_str_cfg +"\n"+ self.status_str_cal +"\n"+ self.status_str_ps +"\n"+ self.status_str_cyc + "\nCycling status: " +  self.cyclingphase
        self.set_status(os.linesep.join([s for s in msg.splitlines() if s]))


    ##############################################################################################################

    #Special function to set zeroth element of field vector to zero, as it should be for dipoles
    #(We use the zeroth element to store theta, but should not be returned)
    def convert_dipole_vector(self,vector):
        returnvector = list(vector)
        returnvector[0]=0.0
        return returnvector


    def calculate_brho(self):
        #Bρ = sqrt(T(T+2M0)/(qc0) where M0 = rest mass of the electron in MeV, q = 1 and c0 = speed of light Mm/s (mega m!) Energy is in eV to start.
        self.BRho = sqrt( self.energy_r/1000000.0 * (self.energy_r/1000000.0 + (2 * 0.000511) ) ) / (300.0)


    def set_current(self):
        #Set the current on the ps
        if self.calc_current > self.maxcurrent:
            self.debug_stream("Requested current %f above limit of PS (%f)" % (self.calc_current,self.maxcurrent))
            self.calc_current = self.maxcurrent
        if self.calc_current < self.mincurrent:
            self.debug_stream("Requested current %f below limit of PS (%f)" % (self.calc_current,self.mincurrent))
            self.calc_current = self.mincurrent
        self.debug_stream("SETTING CURRENT ON THE PS TO: %f ", self.calc_current)
        try:
            self.ps_device.write_attribute("Current", self.calc_current)
        except PyTango.DevFailed as e:
            self.set_state(PyTango.DevState.ALARM)
            self.status_str_ps = "Cannot set current on PS" + self.PowerSupplyProxy


    #-----------------------------------------------------------------------------
    #    MagnetCircuit read/write attribute methods
    #-----------------------------------------------------------------------------

    def read_currentCalculated(self, attr):
        self.debug_stream("In read_currentCalculated()")
        attr.set_value(self.calc_current)

    def is_currentCalculated_allowed(self, attr):
        return self.hasCalibData and self.get_state() not in [PyTango.DevState.FAULT,PyTango.DevState.UNKNOWN]
       
    #

    def read_currentActual(self, attr):
        self.debug_stream("In read_currentActual()")
        attr.set_value(self.actual_current)

    def is_currentActual_allowed(self, attr):
        return self.get_state() not in [PyTango.DevState.FAULT,PyTango.DevState.UNKNOWN]

    #

    def read_fieldA(self, attr):
        self.debug_stream("In read_fieldA()")
        #For dipoles, we store theta (theta * BRho) in zeroth element of fieldX (fieldX normalised)
        #BUT in reality zeroth element is zero. See wiki page for details.
        if self.allowed_component == 0:
            attr.set_value(self.convert_dipole_vector(self.fieldA))
        else:
            attr.set_value(self.fieldA)

    def is_fieldA_allowed(self, attr):
        return self.hasCalibData and self.get_state() not in [PyTango.DevState.FAULT,PyTango.DevState.UNKNOWN]

    #

    def read_fieldB(self, attr):
        self.debug_stream("In read_fieldB()")
        #For dipoles, we store theta (theta * BRho) in zeroth element of fieldX (fieldX normalised)
        #BUT in reality zeroth element is zero. See wiki page for details.
        if self.allowed_component == 0:
            attr.set_value(self.convert_dipole_vector(self.fieldB))
        else:
            attr.set_value(self.fieldB)

    def is_fieldB_allowed(self, attr):
        return self.hasCalibData and self.get_state() not in [PyTango.DevState.FAULT,PyTango.DevState.UNKNOWN]

    #

    def read_fieldANormalised(self, attr):
        self.debug_stream("In read_fieldANormalised()")
        #For dipoles, we store theta (theta * BRho) in zeroth element of fieldX (fieldX normalised)
        #BUT in reality zeroth element is zero. See wiki page for details.
        if self.allowed_component == 0:
            attr.set_value(self.convert_dipole_vector(self.fieldANormalised))
        else:
            attr.set_value(self.fieldANormalised)

    def is_fieldANormalised_allowed(self, attr):
        return self.hasCalibData and self.get_state() not in [PyTango.DevState.FAULT,PyTango.DevState.UNKNOWN]

    #

    def read_fieldBNormalised(self, attr):
        self.debug_stream("In read_fieldBNormalised()")
        #For dipoles, we store theta (theta * BRho) in zeroth element of fieldX (fieldX normalised)
        #BUT in reality zeroth element is zero. See wiki page for details.
        if self.allowed_component == 0:
            attr.set_value(self.convert_dipole_vector(self.fieldBNormalised))
        else:
            attr.set_value(self.fieldBNormalised)

    def is_fieldBNormalised_allowed(self, attr):
        return self.hasCalibData and self.get_state() not in [PyTango.DevState.FAULT,PyTango.DevState.UNKNOWN]

    #

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
        if self.hasCalibData:
            self.set_field_limits()

        #If energy changes, current or field must also change
        #Only do something if the current from the PS is known
        if self.scaleField:
            self.debug_stream("Energy (Brho) changed to %f (%f): will recalculate current to preserve field" % (self.energy_r, self.BRho) )
            #since brho changed, need to recalc the field
            if self.Tilt == 0:
                self.fieldB[self.allowed_component]  = self.MainFieldComponent_r * self.BRho
            else:
                self.fieldA[self.allowed_component]  = self.MainFieldComponent_r * self.BRho
            #now find the current if possible
            if self.hasCalibData:
                self.calc_current \
                    = calculate_current(self.allowed_component, self.currentsmatrix, self.fieldsmatrix, self.BRho,  self.PolTimesOrient, self.Tilt, self.Length, self.fieldA, self.fieldB)
                ###########################################################
                #Set the current on the ps
                self.set_current()
        else:
            self.debug_stream("Energy changed: will recalculate fields for the PS current")
            if self.hasCalibData:
                (self.MainFieldComponent_r, self.fieldA, self.fieldANormalised, self.fieldB, self.fieldBNormalised) \
                    = calculate_fields(self.allowed_component, self.currentsmatrix, self.fieldsmatrix, self.BRho,  self.PolTimesOrient, self.Tilt, self.Length, self.actual_current)
                #if we changed the read value of MainFieldComponent now, change the set value to correspond
                self.MainFieldComponent_w = self.MainFieldComponent_r

    def is_energy_allowed(self, attr):
        return self.hasCalibData and self.get_state() not in [PyTango.DevState.FAULT,PyTango.DevState.UNKNOWN]

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

    def is_BRho_allowed(self, attr):
        return self.hasCalibData and self.get_state() not in [PyTango.DevState.FAULT,PyTango.DevState.UNKNOWN]
        
    #

    def read_MainFieldComponent(self, attr):
        self.debug_stream("In read_MainFieldComponent()")
        if self.hasCalibData == True:
            attr_MainFieldComponent_read = self.MainFieldComponent_r
            attr.set_value(attr_MainFieldComponent_read)
            if self.MainFieldComponent_w == None: #true at initialise
                self.MainFieldComponent_w = self.MainFieldComponent_r
            attr.set_write_value(self.MainFieldComponent_w)

    def write_MainFieldComponent(self, attr):
        self.debug_stream("In write_MainFieldComponent()")
        if self.hasCalibData:
            attr_MainFieldComponent_write=attr.get_write_value()
            self.MainFieldComponent_w = attr_MainFieldComponent_write
            #Note that we set the component of the field vector directly here, but
            #calling calculate_fields will in turn set the whole vector, including this component again
            if self.Tilt == 0:
                self.fieldB[self.allowed_component]  = attr_MainFieldComponent_write * self.BRho
            else:
                self.fieldA[self.allowed_component]  = attr_MainFieldComponent_write * self.BRho

            self.calc_current \
                = calculate_current(self.allowed_component, self.currentsmatrix, self.fieldsmatrix, self.BRho,  self.PolTimesOrient, self.Tilt, self.Length, self.fieldA, self.fieldB)
            ###########################################################
            #Set the current on the ps
            self.set_current()

    def is_MainFieldComponent_allowed(self, attr):
        return self.hasCalibData and self.get_state() not in [PyTango.DevState.FAULT,PyTango.DevState.UNKNOWN]

    #

    def read_IntMainFieldComponent(self, attr):
        self.debug_stream("In read_IntMainFieldComponent()")
        if self.hasCalibData == True:
            attr_IntMainFieldComponent_read = self.MainFieldComponent_r * self.Length
            attr.set_value(attr_IntMainFieldComponent_read)

    def is_IntMainFieldComponent_allowed(self, attr):
        return self.hasCalibData and self.get_state() not in [PyTango.DevState.FAULT,PyTango.DevState.UNKNOWN]

    #

    def read_CyclingStatus(self, attr):
        self.debug_stream("In read_CyclingStatus()")
        attr_CyclingStatus_read = self.cyclingphase
        attr.set_value(attr_CyclingStatus_read)

    def read_CyclingState(self, attr):
        self.debug_stream("In read_CyclingState()")
        if self.get_state() == PyTango.DevState.RUNNING:
            attr.set_value(True)
        else:
            attr.set_value(False)

    #-----------------------------------------------------------------------------
    #    MagnetCircuit command methods
    #-----------------------------------------------------------------------------

    def StartCycle(self):
        self.debug_stream("In StartCycle()")
        self._cycler.cycling= True
        self.set_state(PyTango.DevState.RUNNING)

    def StopCycle(self):
        self.debug_stream("In StopCycle()")
        self._cycler.cycling= False
        self.set_state(PyTango.DevState.ON)

    def is_StartCycle_allowed(self):
        allowed = self._cycler is not None and not self.get_state() in [PyTango.DevState.RUNNING]
        return allowed

    def is_StopCycle_allowed(self):
        if self.get_state() in [PyTango.DevState.RUNNING]:
            return  True
        else:
            return False

class MagnetCircuitClass(PyTango.DeviceClass):

    #Class Properties
    class_property_list = {
        }


    #Device Properties
    device_property_list = {
        #PJB I use strings since I can't have a 2d array of floats?
        #So now I end up with a list of lists instead. See above for conversion.
        'ExcitationCurveCurrents':
            [PyTango.DevVarStringArray,
             "Measured calibration currents for each multipole",
             [ "not set" ] ], #do not changed since used to check if data in DB
        'ExcitationCurveFields':
            [PyTango.DevVarStringArray,
            "Measured calibration fields for each multipole",
             [ "not set" ] ],
        'PowerSupplyProxy':
            [PyTango.DevString,
             "Associated powersupply",
             [ "not set" ] ],
        'MagnetProxies':
            [PyTango.DevVarStringArray,
             "List of magnets on this circuit",
             [ "not set" ] ],
        }


    #Command definitions
    cmd_list = {
        'StartCycle':
             [[PyTango.DevVoid, ""],
              [PyTango.DevBoolean, ""]],
        'StopCycle':
            [[PyTango.DevVoid, ""],
             [PyTango.DevBoolean, ""]],
    }


    #Attribute definitions
    attr_list = {
        'currentCalculated':
        [[PyTango.DevFloat,
          PyTango.SCALAR,
          PyTango.READ],
         {
             'label': "calculated current",
             'unit': "A",
             'description': "calculated current",
         } ],
        'currentActual':
        [[PyTango.DevFloat,
          PyTango.SCALAR,
          PyTango.READ],
         {
             'label': "actual current",
             'unit': "A",
             'description': "actual current on powersupply",
         } ],
        'fieldA':
        [[PyTango.DevFloat,
          PyTango.SPECTRUM,
          PyTango.READ, 10],
         {
             'label': "A_n",
             'unit': "T m^1-n",
             'description': "field A (skew) components",
         } ],
        'fieldB':
        [[PyTango.DevFloat,
          PyTango.SPECTRUM,
          PyTango.READ, 10],
         {
            'label': "B_n",
            'unit': "T m^1-n",
            'description': "field B (normal) components",
         } ],
        'fieldANormalised':
        [[PyTango.DevFloat,
          PyTango.SPECTRUM,
          PyTango.READ, 10],
        {
            'label': "e/p A_n",
            'unit': "m^-n",
            'description': "field A (skew) normalised components",
         } ],
        'fieldBNormalised':
        [[PyTango.DevFloat,
          PyTango.SPECTRUM,
          PyTango.READ, 10],
         {
             'label': "e/p B_n",
             'unit': "m^-n",
             'description': "field B (normal) normalised components",
        } ],
        'energy':
        [[PyTango.DevFloat,
          PyTango.SCALAR,
          PyTango.READ_WRITE],
         {
             'label': "electron energy",
             'unit': "eV",
             'format': "%6.2e",
             'description': "electron energy",
         } ],
        'fixNormFieldOnEnergyChange':
        [[PyTango.DevBoolean,
        PyTango.SCALAR,
          PyTango.READ_WRITE],
         {
             'label': "Preserve norm. field on energy change",
             'unit': "T/F",
             'description': "If true, if the energy changes the current is recalculated in order to preserve the normalised field",
         } ],
        'BRho':
        [[PyTango.DevFloat,
          PyTango.SCALAR,
          PyTango.READ],
         {
             'label': "b.rho",
             'unit': "eV s m^1",
             'description': "b.rho conversion factor",
         } ],
        'CyclingStatus':
        [[PyTango.DevString,
          PyTango.SCALAR,
          PyTango.READ],
         {
             'label': "Cycling Status",
             'description': "Status of cycling procedure",
         } ],
        'CyclingState':
        [[PyTango.DevBoolean,
          PyTango.SCALAR,
          PyTango.READ],
         {
             'label': "Cycling State",
             'description': "State of cycling procedure",
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
        py.add_class(MagnetCircuitClass,MagnetCircuit,'MagnetCircuit')

        U = PyTango.Util.instance()
        U.server_init()
        U.server_run()

    except PyTango.DevFailed,e:
        print '-------> Received a DevFailed exception:',e
    except Exception,e:
        print '-------> An unforeseen exception occured....',e

if __name__ == '__main__':
    main()
