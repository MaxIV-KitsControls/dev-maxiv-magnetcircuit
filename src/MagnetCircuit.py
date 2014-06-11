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
        self.get_device_properties(self.get_device_class())

        #Check dimensions of current and field calibration data
        #(Should be n arrays of field values for n arrays of current values)
        if  len(self.ExcitationCurveCurrents) != len(self.ExcitationCurveFields):
            print >> self.log_fatal, 'Incompatible current and field calibration data'
            sys.exit(1)

        #Make numpy arrays for field and currents for each multipole component. Assume max dimension is _maxdim with 11 measurements.
        self.fieldsmatrix   = np.zeros(shape=(self._maxdim,11), dtype=float) 
        self.currentsmatrix = np.zeros(shape=(self._maxdim,11), dtype=float) 

        #Fill the numpy arrays, but first horrible conversion of list of chars to floats
        self.debug_stream("Multipole dimension ",  len(self.ExcitationCurveCurrents))
        for i in range (0,len(self.ExcitationCurveCurrents)):
            MeasuredFields_l = []    
            MeasuredCurrents_l = []         
            #PJB hack since I use a string to start with like "[1,2,3]" No way to store a matrix of floats?
            if len(self.ExcitationCurveCurrents[i])>0:
                self.MeasuredFields_l   =   [float(x) for x in "".join(self.ExcitationCurveFields[i][1:-1]).split(",")]
                self.MeasuredCurrents_l =   [float(x) for x in "".join(self.ExcitationCurveCurrents[i][1:-1]).split(",")]
                self.currentsmatrix[i]=self.MeasuredCurrents_l
                self.fieldsmatrix[i]=self.MeasuredFields_l
                
        #Need to sort in ascending order in order for interpolate to work later
        self.fieldsmatrix.sort()       
        self.currentsmatrix.sort() 

        #Check if the current is zero for the first entry, force the field to be zero as well
        for i in range (0,len(self.ExcitationCurveCurrents)):
            if self.currentsmatrix[i][0] < 0.01:
               self.currentsmatrix[i][0] = 0.0
               self.fieldsmatrix[i][0] = 0.0

        #Check length, tilt, type of actual magnet devices (should all be the same)
        self.Length=-1.0
        self.Type=""
        self.Tilt=-1.0
        for (i, magnet_device_name) in enumerate(self.MagnetProxies):
            try:
                magnet_device = PyTango.DeviceProxy(magnet_device_name)
                newlength = float(magnet_device.get_property("Length")["Length"][0]) #is this really how to read properties?
                newtilt   = int(magnet_device.get_property("Tilt")["Tilt"][0])  
                newtype   = magnet_device.get_property("Type")["Type"][0]
                if i == 0:
                    self.Length = newlength
                    self.Type   = newtype
                    self.Tilt   = newtilt
                if self.Length != newlength:
                    print >> self.log_fatal, 'Found magnets of different length on same circuit', self.Length, newlength, magnet_device_name
                if self.Type   != newtype:
                    print >> self.log_fatal, 'Found magnets of different type on same circuit', self.Type, newtype, magnet_device_name
                if self.Tilt   != newtilt:
                    print >> self.log_fatal, 'Found magnets of different tilt on same circuit', self.Tilt, newtilt, magnet_device_name
            except PyTango.DevFailed as e:
                print >> self.log_fatal, 'Cannot get information from magnet device ' + magnet_device_name
                sys.exit(1)

        self.debug_stream("Magnet length is ", self.Length)
        self.debug_stream("Magnet type is   ", self.Type)     
        self.debug_stream("Magnet tilt is   ", self.Tilt)

        #The magnet type determines which row in the numpy array we are interested in to control
        #Note that in the multipole expansion we have:
        # 1 - dipole, 2 - quadrupole, 3 - sextupole, 4 - octupole
        #which of course is row 0-3 in our numpy array

        self.allowed_component = -1
        if self.Type == "csrcsbend":
            self.allowed_component = 0
        elif self.Type == "kquad":
            self.allowed_component = 1
        elif self.Type == "ksext":
            self.allowed_component = 2
        else:
            print >> self.log_fatal, 'Magnet type invalid'
            sys.exit(1)

        #Energy needs to be ready from somewhere
        self.energy = 100000.0 #=100 MeV for testing
        self.BRho = 1.0      #a conversion factor that depends on energy
        self.calculate_brho()

        #initial values - will update as soon as current is read from PS below
        self.fieldA = [-1.0,-1.0,-1.0,-1.0,-1.0,-1.0,-1.0,-1.0,-1.0,-1.0]
        self.fieldB = [-1.0,-1.0,-1.0,-1.0,-1.0,-1.0,-1.0,-1.0,-1.0,-1.0]
        self.fieldANormalised = [-1.0,-1.0,-1.0,-1.0,-1.0,-1.0,-1.0,-1.0,-1.0,-1.0]
        self.fieldBNormalised = [-1.0,-1.0,-1.0,-1.0,-1.0,-1.0,-1.0,-1.0,-1.0,-1.0]
        self.k1 = -1.0
        self.scaleField=False
        self.calc_current = -1.0
        self.actual_current = - 1.0
        self.actual_current_quality =  PyTango.AttrQuality.ATTR_VALID

        #Get the PS device and the actual current. If cannot connect to PS device may as well just exit.
        try:
            self.ps_device = PyTango.DeviceProxy(self.PowerSupplyProxy)        
            self.actual_current =  self.ps_device.Current
            self.set_state(self.ps_device.State())
            (self.k1, self.fieldA, self.fieldANormalised, self.fieldB, self.fieldBNormalised)  \
                = calculate_fields(self.allowed_component, self.currentsmatrix, self.fieldsmatrix, self.BRho, self.Tilt, self.Length, self.energy, self.ps_device.Current)

            #To give consistent starting conditions, now calculate the current given these fields
            #i.e. we calculate back the actual current we just read
            self.calc_current \
                = calculate_current(self.allowed_component, self.currentsmatrix, self.fieldsmatrix, self.BRho, self.Tilt, self.Length, self.energy,  self.fieldA, self.fieldB)

        except PyTango.DevFailed as e:
            self.debug_stream('Cannot read current from PS ' + self.PowerSupplyProxy) 
            sys.exit(1)

    def calculate_brho(self):
        #Bρ = sqrt(T(T+2M0)/(qc0) where M0 = rest mass of the electron in MeV, q = 1 and c0 = speed of light Mm/s (mega m!) Energy is in eV to start.
        self.BRho = sqrt( self.energy/1000.0 * (self.energy/1000.0 + (2 * 0.511) ) ) / (300.0) 

    def set_current(self):
        #Set the current on the ps
        self.debug_stream("SETTING CURRENT ON THE PS TO: ", self.calc_current)
        try:
            self.ps_device.write_attribute("Current", self.calc_current)
        except PyTango.DevFailed as e:
            self.set_state(PyTango.DevState.ALARM)
            self.set_status("Cannot set current on PS" + self.PowerSupplyProxy) 

    def always_executed_hook(self):
        self.debug_stream("In always_excuted_hook()")
        #Always recalc fields for actual current. If the current changes we need to check how fields change.
        #NB if we change the i'th component we need to see how other components change as a result
        try:            
            self.set_state(self.ps_device.State())
            self.actual_current =  self.ps_device.Current
            (self.k1, self.fieldA, self.fieldANormalised, self.fieldB, self.fieldBNormalised) \
                = calculate_fields(self.allowed_component, self.currentsmatrix, self.fieldsmatrix, self.BRho, self.Tilt, self.Length, self.energy, self.actual_current)
        except PyTango.DevFailed as e:
            self.actual_current_quality =  PyTango.AttrQuality.ATTR_INVALID
            self.set_state(PyTango.DevState.UNKNOWN)
            self.set_status("Cannot read current on PS" + self.PowerSupplyProxy) 


    #-----------------------------------------------------------------------------
    #    MagnetCircuit read/write attribute methods
    #-----------------------------------------------------------------------------
    def read_currentCalculated(self, attr):
        self.debug_stream("In read_currentCalculated()")
        attr.set_value(self.calc_current)

    def read_currentActual(self, attr):
        self.debug_stream("In read_currentActual()")
        attr.set_value(self.actual_current)
        attr.set_quality(self.actual_current_quality)

    def read_fieldA(self, attr):
        self.debug_stream("In read_fieldA()")
        attr.set_value(self.fieldA)
        attr.set_quality(self.actual_current_quality)

    def read_fieldB(self, attr):
        self.debug_stream("In read_fieldB()")
        attr.set_value(self.fieldB)
        attr.set_quality(self.actual_current_quality)

    def read_fieldANormalised(self, attr):
        self.debug_stream("In read_fieldANormalised()")
        attr.set_value(self.fieldANormalised)
        attr.set_quality(self.actual_current_quality)

    def read_fieldBNormalised(self, attr):
        self.debug_stream("In read_fieldBNormalised()")
        attr.set_value(self.fieldBNormalised)
        attr.set_quality(self.actual_current_quality)

    def read_energy(self, attr):
        self.debug_stream("In read_energy()")
        attr.set_value(self.energy)
        attr.set_write_value(self.energy)

    def write_energy(self, attr):
        self.debug_stream("In write_energy()")
        self.energy = attr.get_write_value()
        self.calculate_brho()
        #If energy changes, current or field must also change            
        #Only do something if the current from the PS is known
        if self.actual_current_quality ==  PyTango.AttrQuality.ATTR_VALID:
            if self.scaleField:
                self.debug_stream("Energy changed: will recalculate and set current")
                self.calc_current \
                    = calculate_current(self.allowed_component, self.currentsmatrix, self.fieldsmatrix, self.BRho, self.Tilt, self.Length, self.energy,  self.fieldA, self.fieldB)
                ###########################################################
                #Set the current on the ps
                self.set_current()
            else:
                self.debug_stream("Energy changed: will recalculate fields")
                (self.k1, self.fieldA, self.fieldANormalised, self.fieldB, self.fieldBNormalised) \
                    = calculate_fields(self.allowed_component, self.currentsmatrix, self.fieldsmatrix, self.BRho, self.Tilt, self.Length, self.energy, self.actual_current)
        else:
            attr.set_quality(self.actual_current_quality)

    def read_scaleFieldByEnergy(self, attr):
        self.debug_stream("In read_scaleFieldByEnergy()")
        attr.set_value(self.scaleField)
        attr.set_write_value(self.scaleField)

    def write_scaleFieldByEnergy(self, attr):
        self.debug_stream("In write_scaleFieldByEnergy()")
        self.scaleField = attr.get_write_value()

    def read_BRho(self, attr):
        self.debug_stream("In read_BRho()")
        attr.set_value(self.BRho)

    def read_k1(self, attr):
        self.debug_stream("In read_k1()")
        attr_k1_read = self.k1
        attr.set_value(attr_k1_read)

    def read_intk1(self, attr):
        self.debug_stream("In read_intk1()")
        attr_intk1_read = self.k1 * self.Length
        attr.set_value(attr_intk1_read)
   
    def write_k1(self, attr):
        self.debug_stream("In write_k1()")
        attr_k1_write=attr.get_write_value()
        self.k1 = attr_k1_write
        #Note that we set the component of the field vector directly here, but
        #calling calculate_fields (from calculate_current) will in turn set the whole vector, including this component again
        if self.Tilt == 0:
            self.fieldB[1]  = attr_k1_write
            self.fieldBNormalised[1]  = attr_k1_write/self.energy
        else:
            self.fieldA[1]  = attr_k1_write
            self.fieldANormalised[1]  = attr_k1_write/self.energy
        self.calc_current \
            = calculate_current(self.allowed_component, self.currentsmatrix, self.fieldsmatrix, self.BRho, self.Tilt, self.Length, self.energy,  self.fieldA, self.fieldB)
        ###########################################################
        #Set the current on the ps
        self.set_current()
        

    def read_attr_hardware(self, data):
        self.debug_stream("In read_attr_hardware()")

    #-----------------------------------------------------------------------------
    def initialize_dynamic_attributes(self):
        if self.Type == "kquad":
            k1 = PyTango.Attr('k1', PyTango.DevDouble, PyTango.READ_WRITE)
            self.add_attribute(k1,MagnetCircuit.read_k1, MagnetCircuit.write_k1)

            att = self.get_device_attr().get_attr_by_name("k1")
            multi_prop = PyTango.MultiAttrProp()
            att.get_properties(multi_prop)
            multi_prop.unit = "m ^-2"
            multi_prop.description = "k1"
            multi_prop.label = "k1"
            att.set_properties(multi_prop)

            intk1 = PyTango.Attr('intk1', PyTango.DevDouble, PyTango.READ)
            self.add_attribute(intk1,MagnetCircuit.read_intk1)
            
            att = self.get_device_attr().get_attr_by_name("intk1")
            multi_prop = PyTango.MultiAttrProp()
            att.get_properties(multi_prop)
            multi_prop.unit = "m ^-1"
            multi_prop.description = "length integrated k1"
            multi_prop.label = "length integrated k1"
            att.set_properties(multi_prop)
       #Need to deal with other magnet types as well. Mainly a question of setting units correctly. 

    #-----------------------------------------------------------------------------
    #    MagnetCircuit command methods
    #-----------------------------------------------------------------------------

    #def On(self):
    #    self.debug_stream("In On()")
    #    self.set_state(PyTango.DevState.ON)   

    #def is_On_allowed(self):
    #     return True

    #def Off(self):
    #    self.debug_stream("In Off()")
    #    self.set_state(PyTango.DevState.OFF)   

    #def is_Off_allowed(self):
    #    return True


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
            [ [] ] ],
        'ExcitationCurveFields':
            [PyTango.DevVarStringArray,
            "Measured calibration fields for each multipole",
            [ [] ] ],
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
        #'On':
        #    [[PyTango.DevVoid, ""],
        #    [PyTango.DevBoolean, ""]],
        #'Off':
        #    [[PyTango.DevVoid, ""],
        #    [PyTango.DevBoolean, ""]],
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
		'label': "actual current current",
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
                'unit': "m^1-n",
                } ],
        'fieldBNormalised':
            [[PyTango.DevFloat,
              PyTango.SPECTRUM,
              PyTango.READ, 10],
             {
                'description': "field B (normal) normalised components",
		'label': "e/p B_n",
                'unit': "m^1-n",
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
        'scaleFieldByEnergy':
            [[PyTango.DevBoolean,
              PyTango.SCALAR,
              PyTango.READ_WRITE],
             {
                'description': "option to scale field by energy",
		'label': "scale field by energy",
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
