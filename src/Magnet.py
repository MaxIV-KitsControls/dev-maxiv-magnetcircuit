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
from magnetcircuitlib import calculate_fields #do not need calculate_current
from processcalibrationlib import process_calibration_data

class Magnet (PyTango.Device_4Impl):

    #--------- Add you global variables here --------------------------
    _maxdim = 10 #Maximum number of multipole components

    def __init__(self,cl, name):
        self._state = None
        PyTango.Device_4Impl.__init__(self,cl,name)
        self.debug_stream("In __init__()")
        Magnet.init_device(self)

    def delete_device(self):
        self.debug_stream("In delete_device()")

    def init_device(self):
        self.debug_stream("In init_device()")        
        self.set_state(PyTango.DevState.ON)

        #attributes are read only field vectors
        self.fieldA           = np.zeros(shape=(self._maxdim), dtype=float)
        self.fieldANormalised = np.zeros(shape=(self._maxdim), dtype=float)
        self.fieldB           = np.zeros(shape=(self._maxdim), dtype=float)
        self.fieldBNormalised = np.zeros(shape=(self._maxdim), dtype=float)  

        #this will get length, polarity, orientation and the raw calibration data
        self.get_device_properties(self.get_device_class())
        self.PolTimesOrient = self.Orientation * self.Polarity
        self.is_sole = False #hack for solenoids until configured properly

        #Proxy to circuit device, provides BRho and curren
        self.debug_stream("Circuit device proxy: %s " % self.CircuitProxies)
        self._circuit_device = None
        self.BRho = 0.0
        self.current = 0.0

        #Some status strings
        self.status_str_ilock = ""
        self.status_str_cfg = ""

        #interlock config
        self.interlock_descs   = {}
        self.interlock_proxies = {}
        self.bad_Ilock_config = False
        self.get_interlock_config()

        #configure magnet type, needed to calculate fields
        self.configure_type()

        #process the calibration data into useful numpy arrays 
        (self.hasCalibData, self.status_str_cfg,  self.fieldsmatrix,  self.currentsmatrix) \
            = process_calibration_data(self.ExcitationCurveCurrents,self.ExcitationCurveFields)
   
    ###############################################################################
    #
    @property
    def circuit_device(self):
        if self._circuit_device is None:
            try:
                self._circuit_device = PyTango.DeviceProxy(self.CircuitProxies)
            except (PyTango.DevFailed, PyTango.ConnectionFailed) as df:
                self.debug_stream("Failed to get circuit proxy\n" + df[0].desc)
                self.set_state(PyTango.DevState.FAULT)
        return self._circuit_device

    ###############################################################################
    #
    def get_interlock_config(self):
        #This is a list of strings of the form [(device,attribute,description),(dev,att,desc)...]
        #First see if we gave any interlock information in the property
        if self.TemperatureInterlock !=  [ "" ]:
            for s in self.TemperatureInterlock:
                try:
                    s_l = s.split(",")
                    ilock_att   = s_l[0]+"/"+s_l[1]
                    ilock_desc  = s_l[2]
                    ilock_proxy = PyTango.AttributeProxy(ilock_att)
                    self.interlock_descs[ilock_att]=ilock_desc
                    self.interlock_proxies[ilock_att]=ilock_proxy
                except (IndexError, PyTango.DevFailed) as e:
                    self.debug_stream("Exception configuring interlocks %s " % self.TemperatureInterlock)
                    #if we fail to configure one interlock, don't configure any
                    self.bad_Ilock_config = True
             
        else:
            self.debug_stream("No interlock tags specified in properties")

    ###############################################################################
    #
    def configure_type(self):
            
        if self.Type == "kquad":
            self.allowed_component = 1
        elif self.Type == "ksext":
            self.allowed_component = 2
        elif self.Type in ["hkick","vkick","csrcsbend","sben","rben", "sbend"]:
            self.allowed_component = 0
        elif self.Type == "sole":
            self.allowed_component = 0
            self.is_sole = True
        else:
            self.status_str_cfg = 'Magnet type invalid %s' % self.Type
            self.debug_stream(self.status_str_cfg)
            self.set_state( PyTango.DevState.FAULT )

    ###############################################################################
    #
    def process_calibration_data(self):

        #process calibration data into usable numpy matrices

        #Check dimensions of current and field calibration data
        #(Should be n arrays of field values for n arrays of current values)
        if  len(self.ExcitationCurveCurrents) != len(self.ExcitationCurveFields):
            self.set_state(PyTango.DevState.FAULT)
            self.status_str_cfg = "Calibration data have mis-matched dimensions"
            return

        #Read calib data from property if exists. No information corresponds to [""]
        if self.ExcitationCurveCurrents == [] or self.ExcitationCurveFields == []:
            self.status_str_cfg = "No calibration data available."
            return

        #otherwise the magnet is calibrated
        self.status_str_cfg = "Magnet is calibrated"
        self.hasCalibData=True

        #Make numpy arrays for field and currents for each multipole component. 
        #At this point the calibration data are strings with comma separated values. Get the length by counting commas!
        array_length = self.ExcitationCurveCurrents[0].count(",")+1
                
        #Calibration points are for positive currents only, but full calibration curve should go negative. 
        #Make "reflected" arrays for negative currents and opposite sign on the fields, then merge the two later below
        pos_fieldsmatrix   = np.zeros(shape=(self._maxdim,array_length), dtype=float)
        pos_currentsmatrix = np.zeros(shape=(self._maxdim,array_length), dtype=float)
        neg_fieldsmatrix   = np.zeros(shape=(self._maxdim,array_length-1), dtype=float)
        neg_currentsmatrix = np.zeros(shape=(self._maxdim,array_length-1), dtype=float)
               
        self.fieldsmatrix   = np.zeros(shape=(self._maxdim,(2*array_length)-1), dtype=float)
        self.currentsmatrix = np.zeros(shape=(self._maxdim,(2*array_length)-1), dtype=float)
        self.fieldsmatrix[:]   = np.NAN
        self.currentsmatrix[:] = np.NAN
                
        #Fill the numpy arrays, but first horrible conversion of list of chars to floats
        self.debug_stream("Multipole dimension %d " % len(self.ExcitationCurveCurrents))

        for i in range (0,len(self.ExcitationCurveCurrents)):
            #PJB hack since I use a string to start with like "[1,2,3]" No way to store a matrix of floats?
            if len(self.ExcitationCurveCurrents[i])>0:
                #need to sort the currents and fields by absolute values for interpolation to work later
                pos_fieldsmatrix[i]   =  sorted([float(x) for x in "".join(self.ExcitationCurveFields[i][1:-1]).split(",")],key=abs)
                pos_currentsmatrix[i] =  sorted([float(x) for x in "".join(self.ExcitationCurveCurrents[i][1:-1]).split(",")],key=abs)
                    
            #Force field and current to be zero in first entry
            pos_currentsmatrix[i][0] = 0.0
            pos_fieldsmatrix[i][0] = 0.0
                    
            #Also here merge the positive and negative ranges into the final array
            neg_fieldsmatrix[i]   = (-pos_fieldsmatrix[i][1:])[::-1]
            neg_currentsmatrix[i] = (-pos_currentsmatrix[i][1:])[::-1]
            #
            self.currentsmatrix[i] = np.concatenate((neg_currentsmatrix[i],pos_currentsmatrix[i]),axis=0)
            self.fieldsmatrix[i]   = np.concatenate((neg_fieldsmatrix[i],pos_fieldsmatrix[i]),axis=0)

    ###############################################################################
    #
    def check_interlock(self):

        self.isInterlocked = False
        #If we have some interlock attributes, see how they are set
        if self.TemperatureInterlock !=  [ "" ]:
            self.status_str_ilock = ""
            if self.bad_Ilock_config:
                self.status_str_ilock =  "Interlock tag specified but interlock proxies could not be configured"
                return
            try:
                for key in self.interlock_proxies:
                    TempInterlockValue  = self.interlock_proxies[key].read().value
                    if TempInterlockValue == True:
                        self.status_str_ilock = self.status_str_ilock + "\nTemperature Interlock Set! " + key + " (" + self.interlock_descs[key] + ")"
                        self.set_state(PyTango.DevState.ALARM)  
                        self.isInterlocked = True

            except (IndexError, PyTango.DevFailed) as e:
                self.debug_stream("Exception reading interlock AttributeProxy")
                self.status_str_ilock = "Cannot read specified interlock tag (s) "
        else:
            self.status_str_ilock =  "No temperature interlock tags specified in properties"


    ###############################################################################
    #
    def get_circuit_state_and_current(self):

        if self.circuit_device:
            try:
                cir_state = self.circuit_device.State()
                self.current = self.circuit_device.currentActual
                self.BRho = self.circuit_device.BRho

                self.status_str_cir = "Connected to circuit %s in state %s " % (self.CircuitProxies, cir_state)
                
            except PyTango.DevFailed as e:
                self.status_str_cir = "Cannot get state of circuit device " + self.CircuitProxies
                self.debug_stream(self.status_str_cir)
                cir_state =PyTango.DevState.FAULT  

        else:
            self.status_str_cir = "Cannot get proxy to " + self.CircuitProxies
            cir_state = PyTango.DevState.FAULT

        return cir_state

    ###############################################################################
    #
    def always_executed_hook(self):

        self.debug_stream("In always_excuted_hook()")

        #set state according to circuit state
        self.set_state(self.get_circuit_state_and_current())

        #get interlock state
        self.check_interlock()

        #set status message
        msg = self.status_str_cfg +"\n"+ self.status_str_cir +"\n"+ self.status_str_ilock
        self.set_status(os.linesep.join([s for s in msg.splitlines() if s]))

        #calc fields
        if self.hasCalibData and self.get_state() not in [PyTango.DevState.FAULT, PyTango.DevState.UNKNOWN]:
            (MainFieldComponent_r, MainFieldComponent_w, self.fieldA, self.fieldANormalised, self.fieldB, self.fieldBNormalised)  \
                = calculate_fields(self.allowed_component, self.currentsmatrix, self.fieldsmatrix, self.BRho, self.PolTimesOrient, self.Tilt, self.Length, self.current, None, self.is_sole)


    #-----------------------------------------------------------------------------
    #    Magnet read/write attribute methods
    #-----------------------------------------------------------------------------
    #Special function to set zeroth element of field vector to zero, as it should be for dipoles
    #(We use the zeroth element to store theta, but should not be returned)
    def convert_dipole_vector(self,vector):
        returnvector = list(vector)
        returnvector[0]=np.NAN
        return returnvector

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
        return self.hasCalibData and self.get_state() not in [PyTango.DevState.FAULT,PyTango.DevState.UNKNOWN]

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
        return self.hasCalibData and self.get_state() not in [PyTango.DevState.FAULT,PyTango.DevState.UNKNOWN]

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
        return self.hasCalibData and self.get_state() not in [PyTango.DevState.FAULT,PyTango.DevState.UNKNOWN]

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
        return self.hasCalibData and self.get_state() not in [PyTango.DevState.FAULT,PyTango.DevState.UNKNOWN]

    #


    def read_temperatureInterlock(self, attr):
        self.debug_stream("In read_temperatureInterlock()")
        attr.set_value(self.isInterlocked)

    #-----------------------------------------------------------------------------
    #    Magnet command methods
    #-----------------------------------------------------------------------------
    

class MagnetClass(PyTango.DeviceClass):


    #Class Properties
    class_property_list = {
        }


    #Device Properties
    device_property_list = {
        'CircuitProxies':
        [PyTango.DevString,
         "Associated circuit",
         [ "" ] ],
        'Length':
        [PyTango.DevFloat,
         "Length",
         [ 0.0 ] ],
        'Polarity':
        [PyTango.DevShort,
         "Polarity",
         [ 1 ] ],
        'Orientation':
        [PyTango.DevShort,
         "Orientation",
         [ 1 ] ],
        'Tilt':
        [PyTango.DevShort,
         "Tilt",
         [ 0 ] ],
        'Type':
        [PyTango.DevString,
         "Tilt",
         [ "" ] ],
        'TemperatureInterlock':
        [PyTango.DevVarStringArray,
         "TemperatureInterlock",
         [ "" ] ],
        #PJB I use strings below since I can't have a 2d array of floats?
        #So now I end up with a list of lists instead. See above for conversion.
        'ExcitationCurveCurrents':
        [PyTango.DevVarStringArray,
         "Measured calibration currents for each multipole",
         [ ] ],
        'ExcitationCurveFields':
        [PyTango.DevVarStringArray,
         "Measured calibration fields for each multipole",
         [ ] ],
    }


    #Command definitions
    cmd_list = {
        }


    #Attribute definitions
    attr_list = {
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
        'temperatureInterlock':
        [[PyTango.DevBoolean,
          PyTango.SCALAR,
          PyTango.READ],
         {
             'label': "temperature interlock",
             'unit': "T/F",
         } ]
    }


def main():
    try:
        py = PyTango.Util(sys.argv)
        py.add_class(MagnetClass,Magnet,'Magnet')
        py.add_class(MagnetCircuitClass, MagnetCircuit,'MagnetCircuit')

        U = PyTango.Util.instance()
        U.server_init()
        U.server_run()

    except PyTango.DevFailed,e:
        print '-------> Received a DevFailed exception:',e
    except Exception,e:
        print '-------> An unforeseen exception occured....',e

if __name__ == '__main__':
    main()
