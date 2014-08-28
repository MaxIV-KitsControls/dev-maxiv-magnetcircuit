#!/usr/bin/env python
# -*- coding:utf-8 -*-

###############################################################################
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
###############################################################################

"""Tango device for generic magnet"""

__all__ = ["MagnetCircuit", "MagnetCircuitClass", "main"]

__docformat__ = 'restructuredtext'

import PyTango
import sys
import numpy as np
from math import sqrt
from magnetcircuitlib import calculate_fields, calculate_current
from cycling_statemachine.magnetcycling import MagnetCycling


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

class MagnetCircuit (PyTango.Device_4Impl):

    _maxdim = 10 #Maximum number of multipole components

    def __init__(self,cl, name):
        PyTango.Device_4Impl.__init__(self,cl,name)
        self.debug_stream("In __init__()")
        MagnetCircuit.init_device(self)

        self.set_change_event('State', True, False)

    def delete_device(self):
        self.debug_stream("In delete_device()")

    def init_device(self):
        self.debug_stream("In init_device()")
        self.get_device_properties(self.get_device_class())
        self.status_str_ps = ""
        self.status_str_cal = ""
        self.status_str_cyc = ""
        self.cyclingphase = "---"
        self.cyclingallowed = True

        #Check dimensions of current and field calibration data
        #(Should be n arrays of field values for n arrays of current values)
        if  len(self.ExcitationCurveCurrents) != len(self.ExcitationCurveFields):
            print >> self.log_fatal, 'Incompatible current and field calibration data'
            sys.exit(1)

        #No information corresponds to [""]
        self.hasCalibData=False
        if  self.ExcitationCurveCurrents[0] == '' or  self.ExcitationCurveCurrents[0] == 'not set':
            self.debug_stream("No calibration data")
        else:
            self.hasCalibData=True
            #Make numpy arrays for field and currents for each multipole component. 
            #At this point the calibration data are strings with comma separated values. Get the length by counting commas!
            array_length = self.ExcitationCurveCurrents[0].count(",")+1
            pos_fieldsmatrix   = np.zeros(shape=(self._maxdim,array_length), dtype=float)
            pos_currentsmatrix = np.zeros(shape=(self._maxdim,array_length), dtype=float)
            #Calibration points are for positive currents only, but full calibration curve should go negative. 
            #Make "reflected" arrays for negative currents and opposite sign on the fields, then merge the two later below
            neg_fieldsmatrix   = np.zeros(shape=(self._maxdim,array_length-1), dtype=float)
            neg_currentsmatrix = np.zeros(shape=(self._maxdim,array_length-1), dtype=float)
            #
            self.fieldsmatrix   = np.zeros(shape=(self._maxdim,(2*array_length)-1), dtype=float)
            self.currentsmatrix = np.zeros(shape=(self._maxdim,(2*array_length)-1), dtype=float)

            #Fill the numpy arrays, but first horrible conversion of list of chars to floats
            self.debug_stream("Multipole dimension %d " % len(self.ExcitationCurveCurrents))

            for i in range (0,len(self.ExcitationCurveCurrents)):
                MeasuredFields_l = []
                MeasuredCurrents_l = []
                #PJB hack since I use a string to start with like "[1,2,3]" No way to store a matrix of floats?
                if len(self.ExcitationCurveCurrents[i])>0:
                    #need to sort the currents and fields by absolute values for interpolation to work later
                    self.MeasuredFields_l   =  sorted([float(x) for x in "".join(self.ExcitationCurveFields[i][1:-1]).split(",")],key=abs)
                    self.MeasuredCurrents_l =  sorted([float(x) for x in "".join(self.ExcitationCurveCurrents[i][1:-1]).split(",")],key=abs)
                    pos_currentsmatrix[i]=self.MeasuredCurrents_l
                    pos_fieldsmatrix[i]=self.MeasuredFields_l

                #Check if the current is zero for the first entry, force the field to be zero as well
                #for i in range (0,len(self.ExcitationCurveCurrents)):
                #set zero point
                if pos_currentsmatrix[i][0] < 0.01:  #check abs?
                    pos_currentsmatrix[i][0] = 0.0
                    pos_fieldsmatrix[i][0] = 0.0

                #Also here merge the positive and negative ranges into the final array
                neg_fieldsmatrix[i]   = (-pos_fieldsmatrix[i][1:])[::-1]
                neg_currentsmatrix[i] = (-pos_currentsmatrix[i][1:])[::-1]
                #
                self.currentsmatrix[i] = np.concatenate((neg_currentsmatrix[i],pos_currentsmatrix[i]),axis=0)
                self.fieldsmatrix[i]   = np.concatenate((neg_fieldsmatrix[i],pos_fieldsmatrix[i]),axis=0)
                
                    
            #check finally the calibration data
            self.debug_stream("Final currents matrix: ")
            self.debug_stream(self.currentsmatrix)
            self.debug_stream("Final fields matrix:   ")
            self.debug_stream(self.fieldsmatrix)
   
        #Check length, tilt, type of actual magnet devices (should all be the same)
        self.Length=-1.0
        self.Type=""
        self.Tilt=-1
        #self.Polarity=1
        #self.Orientation=1
        self.PolTimesOrient=1

        #magnet_property_types = {"Length": float, "Tilt": int, "Type": str, "Polarity": int, "Orientation": int}
        #deal with polarity and orientation separately
        magnet_property_types = {"Length": float, "Tilt": int, "Type": str}
        problematic_devices = set()  # let's be optimistic
        for (i, magnet_device_name) in enumerate(self.MagnetProxies):
            magnet_device = PyTango.DeviceProxy(magnet_device_name)
            for prop, type_ in magnet_property_types.items():
                try:
                    prop_value = type_(magnet_device.get_property(prop)[prop][0])
                except IndexError as e:
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
            newpolarity = int(magnet_device.get_property("Polarity")["Polarity"][0])
            neworientation = int(magnet_device.get_property("Orientation")["Orientation"][0])
            newpoltimesorient = newpolarity * neworientation
            if i == 0:
                self.PolTimesOrient = newpolarity * neworientation
                if self.PolTimesOrient != newpoltimesorient:
                    print >> self.log_fatal, 'Found magnets of different polarity times orientation on same circuit', self.PolTimesOrient, newpoltimesorient, magnet_device_name
                    problematic_devices.add(magnet_device_name)

        # If there were any issues, we exit since things are not consistent
        if problematic_devices:
            print >> self.log_fatal, ('Cannot start due to issues with magnet device(s): %s' %
                                      ", ".join(problematic_devices))
            sys.exit(1)


        self.debug_stream("Magnet length is %f " % self.Length)
        self.debug_stream("Magnet type is %s  " %  self.Type)
        self.debug_stream("Magnet tilt is %d  " % self.Tilt)
        #self.debug_stream("Magnet polarity is %d    " % self.Polarity)
        #self.debug_stream("Magnet orientation is %d " % self.Orientation)
        self.debug_stream("Magnet polarity times orientation is %d " % self.PolTimesOrient)

        #The magnet type determines which row in the numpy array we are interested in to control
        #Note that in the multipole expansion we have:
        # 1 - dipole, 2 - quadrupole, 3 - sextupole, 4 - octupole
        #which of course is row 0-3 in our numpy array

        self.allowed_component = -1
        if self.Type in ["csrcsbend","hkick","vkick","sole"]:
            #h and vkick also here using small theta. Large theta for bends.
            self.allowed_component = 0
        elif self.Type == "kquad":
            self.allowed_component = 1
        elif self.Type == "ksext":
            self.allowed_component = 2
        else:
            print >> self.log_fatal, 'Magnet type invalid'
            sys.exit(1)

        #Energy needs to be ready from somewhere
        self.energy_r = 100000000.0 #=100 MeV for testing
        self.energy_w = None
        self.BRho = 1.0      #a conversion factor that depends on energy
        self.calculate_brho()

        #initial values - will update as soon as current is read from PS below
        self.fieldA = [-1.0,-1.0,-1.0,-1.0,-1.0,-1.0,-1.0,-1.0,-1.0,-1.0]
        self.fieldB = [-1.0,-1.0,-1.0,-1.0,-1.0,-1.0,-1.0,-1.0,-1.0,-1.0]
        self.fieldANormalised = [-1.0,-1.0,-1.0,-1.0,-1.0,-1.0,-1.0,-1.0,-1.0,-1.0]
        self.fieldBNormalised = [-1.0,-1.0,-1.0,-1.0,-1.0,-1.0,-1.0,-1.0,-1.0,-1.0]
        self.variableComponent_r = -1000.0
        self.variableComponent_w = None
        self.scaleField=False
        self.calc_current = -1.0
        self.actual_current = - 1.0
        self.current_quality =  PyTango.AttrQuality.ATTR_VALID
        self.field_quality =  PyTango.AttrQuality.ATTR_VALID

        #Get the PS device and the actual current. If cannot connect to PS device may as well just exit since probably misconfigured properties.
        try:
            self.ps_device = PyTango.DeviceProxy(self.PowerSupplyProxy)
            self.status_str_ps = "Connected to PS device " + self.PowerSupplyProxy
        except PyTango.DevFailed as e:
            self.debug_stream('Cannot connect to PS ' + self.PowerSupplyProxy)
            sys.exit(1)

        #if connected try to read current and state
        self.get_ps_state()

        #To give consistent starting conditions, now calculate the current given these fields
        #i.e. we calculate back the actual current we just read
        #Assuming that we have the calib data.
        if self.hasCalibData:
            self.calc_current \
                = calculate_current(self.allowed_component, self.currentsmatrix, self.fieldsmatrix, self.BRho, self.PolTimesOrient, self.Tilt, self.Length,  self.fieldA, self.fieldB)

        #Finally set up cycling machinery
        self.wrapped_ps_device = Wrapped_PS_Device(self.ps_device)
        #The cycling varies the current from min and max a number of times.
        #Need to get the current limits from the PS device; number of iterations and wait time can be properties
        self.maxcurrent = None
        self.mincurrent = None
        maxcurrent_s = self.ps_device.get_attribute_config("Current").max_value
        mincurrent_s = self.ps_device.get_attribute_config("Current").min_value
        if maxcurrent_s == 'Not specified' or mincurrent_s == 'Not specified':
            self.debug_stream("Current limits not specified, cannot do cycling")
            #cycling command should not be allowed
            self.cyclingallowed = False
            self._cycler = None
        #! We assume if there are limits then they are good!
        else:
            self.maxcurrent = float(maxcurrent_s)
            self.mincurrent = float(mincurrent_s)
            self._cycler =  MagnetCycling(self.wrapped_ps_device, self.maxcurrent, self.mincurrent, 5.0, 4)

    def get_ps_state(self):

        self.status_str_cal = ""
        try:

            self.current_quality =  PyTango.AttrQuality.ATTR_VALID
            self.field_quality =  PyTango.AttrQuality.ATTR_VALID

            #generally the circuit should echo the ps state. However, during cycling, we want the circuit to be running,
            #and not moving, but we do want to catch any ps errors
            ps_state = self.ps_device.State()
            if self.get_state() == PyTango.DevState.RUNNING and ps_state in [PyTango.DevState.ON, PyTango.DevState.MOVING]:
               pass
            else:
                self.set_state(ps_state)

            self.actual_current =  self.ps_device.Current

            #Just assume the calculated current is whatever we wrote to the ps device
            self.calc_current =  self.ps_device.read_attribute("Current").w_value

            if self.hasCalibData:
                (self.variableComponent_r, self.fieldA, self.fieldANormalised, self.fieldB, self.fieldBNormalised)  \
                    = calculate_fields(self.allowed_component, self.currentsmatrix, self.fieldsmatrix, self.BRho, self.PolTimesOrient, self.Tilt, self.Length, self.actual_current)
                self.status_str_cal = "Field-current calibration data available"

            else:
                self.status_str_cal = "No calibration data available, showing PS current only"
                self.calc_current =   self.actual_current
                self.field_quality =  PyTango.AttrQuality.ATTR_INVALID
                self.cyclingallowed = False

        except PyTango.DevFailed as e:
            self.current_quality =  PyTango.AttrQuality.ATTR_INVALID
            self.debug_stream('Cannot read current from PS ' + self.PowerSupplyProxy)
            self.status_str_cal = "Cannot read current on PS" + self.PowerSupplyProxy

    def calculate_brho(self):
        #Bρ = sqrt(T(T+2M0)/(qc0) where M0 = rest mass of the electron in MeV, q = 1 and c0 = speed of light Mm/s (mega m!) Energy is in eV to start.
        self.BRho = sqrt( self.energy_r/1000000.0 * (self.energy_r/1000000.0 + (2 * 0.000511) ) ) / (300.0)


    def set_current_limits(self):

        #Set the limits on the variable component (k1 etc) which will change if the energy changes
        att = self.get_device_attr().get_attr_by_name("variableComponent")
        multi_prop = PyTango.MultiAttrProp()
        att.get_properties(multi_prop)
        minvariableComponent = calculate_fields(self.allowed_component, self.currentsmatrix, self.fieldsmatrix, self.BRho, self.PolTimesOrient, self.Tilt, self.Length,  self.mincurrent)[0]
        maxvariableComponent = calculate_fields(self.allowed_component, self.currentsmatrix, self.fieldsmatrix, self.BRho, self.PolTimesOrient, self.Tilt, self.Length,  self.maxcurrent)[0]
        print "current limit ", self.maxcurrent
        print "field limit ", maxvariableComponent
        print "energy and brrho and length ", self.energy_r, self.BRho, self.Length
        
        if minvariableComponent<maxvariableComponent:
            multi_prop.min_value=minvariableComponent
            multi_prop.max_value=maxvariableComponent
        else:
            multi_prop.min_value=maxvariableComponent
            multi_prop.max_value=minvariableComponent
        att.set_properties(multi_prop)


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

    def always_executed_hook(self):
        self.debug_stream("In always_excuted_hook()")
        #Always recalc fields for actual current. If the current changes we need to check how fields change.
        #NB if we change the i'th component we need to see how other components change as a result
        self.get_ps_state()
        #check phase of magnet cycling (if never started any cycling, will return ---)
        if self.cyclingallowed:
            self.cyclingphase  = self._cycler.phase
            #need to check here if we should still be RUNNING, not ideal way, needs refactor since set already in get_ps_state
            if  self.cyclingphase == "NOT CYCLING":
                self.change_state(self.ps_device.State())
        else:
            self.cyclingphase  = "Cycling not permitted"


        self.set_status(self.status_str_ps + "\n" + self.status_str_cal + "\nCycling status: " +  self.cyclingphase)

    #-----------------------------------------------------------------------------
    #    MagnetCircuit read/write attribute methods
    #-----------------------------------------------------------------------------
    def read_currentCalculated(self, attr):
        self.debug_stream("In read_currentCalculated()")
        attr.set_value(self.calc_current)
        attr.set_quality(self.field_quality)

    def read_currentActual(self, attr):
        self.debug_stream("In read_currentActual()")
        attr.set_value(self.actual_current)
        attr.set_quality(self.current_quality)

    #Special function to set zeroth element of field vector to zero, as it should be for dipoles
    #(We use the zeroth element to store theta, but should not be returned)
    def ConvertDipoleVector(self,vector):
        returnvector = list(vector)
        returnvector[0]=0.0
        return returnvector

    def read_fieldA(self, attr):
        self.debug_stream("In read_fieldA()")
        #For dipoles, we store theta (theta * BRho) in zeroth element of fieldX (fieldX normalised)
        #BUT in reality zeroth element is zero. See wiki page for details.
        if self.allowed_component == 0:
            attr.set_value(self.ConvertDipoleVector(self.fieldA))
        else:
            attr.set_value(self.fieldA)
        attr.set_quality(self.current_quality)
        attr.set_quality(self.field_quality)

    def read_fieldB(self, attr):
        self.debug_stream("In read_fieldB()")
        #For dipoles, we store theta (theta * BRho) in zeroth element of fieldX (fieldX normalised)
        #BUT in reality zeroth element is zero. See wiki page for details.
        if self.allowed_component == 0:
            attr.set_value(self.ConvertDipoleVector(self.fieldB))
        else:
            attr.set_value(self.fieldB)
        attr.set_quality(self.current_quality)
        attr.set_quality(self.field_quality)

    def read_fieldANormalised(self, attr):
        self.debug_stream("In read_fieldANormalised()")
        #For dipoles, we store theta (theta * BRho) in zeroth element of fieldX (fieldX normalised)
        #BUT in reality zeroth element is zero. See wiki page for details.
        if self.allowed_component == 0:
            attr.set_value(self.ConvertDipoleVector(self.fieldANormalised))
        else:
            attr.set_value(self.fieldANormalised)
        attr.set_quality(self.current_quality)
        attr.set_quality(self.field_quality)

    def read_fieldBNormalised(self, attr):
        self.debug_stream("In read_fieldBNormalised()")
        #For dipoles, we store theta (theta * BRho) in zeroth element of fieldX (fieldX normalised)
        #BUT in reality zeroth element is zero. See wiki page for details.
        if self.allowed_component == 0:
            attr.set_value(self.ConvertDipoleVector(self.fieldBNormalised))
        else:
            attr.set_value(self.fieldBNormalised)
        attr.set_quality(self.current_quality)
        attr.set_quality(self.field_quality)

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
            self.set_current_limits()

        #If energy changes, current or field must also change
        #Only do something if the current from the PS is known
        if self.current_quality ==  PyTango.AttrQuality.ATTR_VALID:
            if self.scaleField:
                self.debug_stream("Energy (Brho) changed to %f (%f): will recalculate current to preserve field" % (self.energy_r, self.BRho) )
                #since brho changed, need to recalc the field
                if self.Tilt == 0:
                    self.fieldB[self.allowed_component]  = self.variableComponent_r * self.BRho
                else:
                    self.fieldA[self.allowed_component]  = self.variableComponent_r * self.BRho
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
                    (self.variableComponent_r, self.fieldA, self.fieldANormalised, self.fieldB, self.fieldBNormalised) \
                        = calculate_fields(self.allowed_component, self.currentsmatrix, self.fieldsmatrix, self.BRho,  self.PolTimesOrient, self.Tilt, self.Length, self.actual_current)
                    #if we changed the read value of variableComponent now, change the set value to correspond
                    self.variableComponent_w = self.variableComponent_r
        else:
            attr.set_quality(self.current_quality)

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

    def read_variableComponent(self, attr):
        self.debug_stream("In read_variableComponent()")
        if self.hasCalibData == False:
            attr.set_quality(PyTango.AttrQuality.ATTR_INVALID)
        else:
            attr_variableComponent_read = self.variableComponent_r
            attr.set_value(attr_variableComponent_read)
            if self.variableComponent_w == None: #true at initialise
                self.variableComponent_w = self.variableComponent_r
            attr.set_write_value(self.variableComponent_w)

    def read_intVariableComponent(self, attr):
        self.debug_stream("In read_intVariableComponent()")
        if self.hasCalibData == False:
            attr.set_quality(PyTango.AttrQuality.ATTR_INVALID)
        else:
            attr_intVariableComponent_read = self.variableComponent_r * self.Length
            attr.set_value(attr_intVariableComponent_read)

    def write_variableComponent(self, attr):
        self.debug_stream("In write_variableComponent()")
        if self.hasCalibData:
            attr_variableComponent_write=attr.get_write_value()
            self.variableComponent_w = attr_variableComponent_write
            #Note that we set the component of the field vector directly here, but
            #calling calculate_fields will in turn set the whole vector, including this component again
            if self.Tilt == 0:
                self.fieldB[self.allowed_component]  = attr_variableComponent_write * self.BRho
            else:
                self.fieldA[self.allowed_component]  = attr_variableComponent_write * self.BRho

            self.calc_current \
                = calculate_current(self.allowed_component, self.currentsmatrix, self.fieldsmatrix, self.BRho,  self.PolTimesOrient, self.Tilt, self.Length, self.fieldA, self.fieldB)
            ###########################################################
            #Set the current on the ps
            self.set_current()

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

    def read_attr_hardware(self, data):
        self.debug_stream("In read_attr_hardware()")

    #-----------------------------------------------------------------------------
    def initialize_dynamic_attributes(self):

        #there is always a single variable component of the field, but the units and label depend on the magnet type
        variableComponent = PyTango.Attr('variableComponent', PyTango.DevDouble, PyTango.READ_WRITE)
        self.add_attribute(variableComponent,MagnetCircuit.read_variableComponent, MagnetCircuit.write_variableComponent)

        att = self.get_device_attr().get_attr_by_name("variableComponent")
        multi_prop = PyTango.MultiAttrProp()
        att.get_properties(multi_prop)
        multi_prop.description = "The variable component of the field, which depends on the magnet type (k2 for sextupoles, k1 for quads, theta for dipoles)"

        if self.Type == "ksext":
            multi_prop.unit = "m ^-3"
            multi_prop.label = "k2"
        if self.Type == "kquad":
            multi_prop.unit = "m ^-2"
            multi_prop.label = "k1"
        if self.Type == "csrcsbend":
            multi_prop.unit = "rad"
            multi_prop.label = "theta"
        att.set_properties(multi_prop)

        #set alarm levels on variableComponent (etc) corresponding to the PS alarms, if we have calib data to convert
        if self.hasCalibData:
            self.set_current_limits()

        #similarly, there is always an integrated (by length) component of the field, different by type
        intVariableComponent = PyTango.Attr('intVariableComponent', PyTango.DevDouble, PyTango.READ)
        self.add_attribute(intVariableComponent,MagnetCircuit.read_intVariableComponent)

        att = self.get_device_attr().get_attr_by_name("intVariableComponent")
        multi_prop = PyTango.MultiAttrProp()
        att.get_properties(multi_prop)
        multi_prop.description = "The length integrated variable component of the field for quadrupoles and sextupoles (k2*l for sextupoles, k1*l for quads). Just theta again for the dipoles"

        if self.Type == "kquad":
            multi_prop.unit = "m ^-1"
            multi_prop.label = "length integrated k1"
        if self.Type == "ksext":
            multi_prop.unit = "m ^-2"
            multi_prop.label = "length integrated k2"
        if self.Type == "csrcsbend":
            multi_prop.unit = "rad"
            multi_prop.label = "theta"

        att.set_properties(multi_prop)


    #-----------------------------------------------------------------------------
    #    MagnetCircuit command methods
    #-----------------------------------------------------------------------------
    def change_state(self,newstate):
        oldstate = self.get_state()
        if newstate != oldstate:
            self.set_state(newstate)
            if oldstate == PyTango.DevState.RUNNING or newstate == PyTango.DevState.RUNNING:
                self.push_change_event("State", newstate)

    def StartCycle(self):
        self.debug_stream("In StartCycle()")
        self._cycler.cycling= True
        self.change_state(PyTango.DevState.RUNNING)

    def StopCycle(self):
        self.debug_stream("In StopCycle()")
        self._cycler.cycling= False
        self.change_state(PyTango.DevState.ON)

    def is_StartCycle_allowed(self):
        allowed = self.cyclingallowed and not self.get_state() in [PyTango.DevState.RUNNING]
        return allowed

    def is_StopCycle_allowed(self):
        if self.get_state() in [PyTango.DevState.RUNNING]:
            return  True
        else:
            return False

class MagnetCircuitClass(PyTango.DeviceClass):

    def dyn_attr(self, dev_list):
        """Invoked to create dynamic attributes for the given devices.
        Default implementation calls
        :meth:`Magnet.initialize_dynamic_attributes` for each device
        :type dev_list: :class:`PyTango.DeviceImpl`"""

        for dev in dev_list:
            dev.initialize_dynamic_attributes()


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
             'description': "calculated current",
             'label': "calculated current",
            'unit': "A",
         } ],
        'currentActual':
        [[PyTango.DevFloat,
          PyTango.SCALAR,
          PyTango.READ],
         {
             'description': "actual current on powersupply",
            'label': "actual current",
             'unit': "A",
         } ],
        'fieldA':
        [[PyTango.DevFloat,
          PyTango.SPECTRUM,
        PyTango.READ, 10],
         {
             'description': "field A (skew) components",
             'label': "A_n",
             'unit': "T m^1-n",
         } ],
        'fieldB':
        [[PyTango.DevFloat,
          PyTango.SPECTRUM,
          PyTango.READ, 10],
         {
             'description': "field B (normal) components",
             'label': "B_n",
             'unit': "T m^1-n",
        } ],
        'fieldANormalised':
        [[PyTango.DevFloat,
          PyTango.SPECTRUM,
          PyTango.READ, 10],
         {
             'description': "field A (skew) normalised components",
             'label': "e/p A_n",
             'unit': "m^-n",
         } ],
        'fieldBNormalised':
        [[PyTango.DevFloat,
          PyTango.SPECTRUM,
          PyTango.READ, 10],
         {
             'description': "field B (normal) normalised components",
             'label': "e/p B_n",
             'unit': "m^-n",
        } ],
        'energy':
        [[PyTango.DevFloat,
          PyTango.SCALAR,
          PyTango.READ_WRITE],
         {
             'description': "electron energy",
             'label': "electron energy",
             'unit': "eV",
         } ],
        'fixNormFieldOnEnergyChange':
        [[PyTango.DevBoolean,
        PyTango.SCALAR,
          PyTango.READ_WRITE],
         {
             'description': "If true, if the energy changes the current is recalculated in order to preserve the normalised field",
             'label': "Re-calc current to preserve norm. field on energy change",
             'unit': "T/F",
         } ],
        'BRho':
        [[PyTango.DevFloat,
          PyTango.SCALAR,
          PyTango.READ],
         {
             'description': "b.rho conversion factor",
             'label': "b.rho",
             'unit': "eV s m^1",
         } ],
        'CyclingStatus':
        [[PyTango.DevString,
          PyTango.SCALAR,
          PyTango.READ],
         {
             'description': "Status of cycling procedure",
             'label': "Cycling Status",
         } ],
        'CyclingState':
        [[PyTango.DevBoolean,
          PyTango.SCALAR,
          PyTango.READ],
         {
             'description': "State of cycling procedure",
             'label': "Cycling State",
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
