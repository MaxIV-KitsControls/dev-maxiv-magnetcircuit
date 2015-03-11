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
        self.fieldA_main           = []
        self.fieldANormalised_main = []
        self.fieldB_main           = [] 
        self.fieldBNormalised_main = [] 
        #
        self.fieldA_trim           = [] 
        self.fieldANormalised_trim = [] 
        self.fieldB_trim           = [] 
        self.fieldBNormalised_trim = [] 
        #
        self.fieldA           = [] 
        self.fieldANormalised = [] 
        self.fieldB           = [] 
        self.fieldBNormalised = [] 
        #

        #this will get length, polarity, orientation and the raw calibration data
        self.get_device_properties(self.get_device_class())
        self.PolTimesOrient = self.Orientation * self.Polarity
        self.is_sole = False #hack for solenoids until configured properly

        #get trim and main coil proxies
        self._main_circuit_device = None
        self._trim_circuit_device = None
        self.MainCoil = None
        self.TrimCoil = None
        self.get_coil_proxies()

        #Some status strings
        self.status_str_ilock = ""
        self.status_str_cfg = ""
        self.status_str_cir = ""
        self.status_str_trm = ""
        #self.status_str_cir_i = ""
        #self.status_str_trm_f = ""

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
    def get_coil_proxies(self):

        #CircuitProxies property can contain main and trim coil
        if len(self.CircuitProxies) == 1:
            print "magnet has one circuit, assume the main coil"
            self.MainCoil=self.CircuitProxies[0]
            print "main coil is ",   self.MainCoil
        elif len(self.CircuitProxies) == 2:
            print "magnet has two circuits, assume the main and trim coils"
            if "TRIM" in self.CircuitProxies[0]:
                self.TrimCoil = self.CircuitProxies[0]
                self.MainCoil = self.CircuitProxies[1]
            else:
                self.TrimCoil = self.CircuitProxies[1]
                self.MainCoil = self.CircuitProxies[0]
            print  "main coil is ",   self.MainCoil
            print  "trim coil is ",   self.TrimCoil
        else:
            print "invalid config"
            self.MainCoil=None
            self.TrimCoil=None

    ###############################################################################
    #
    @property
    def main_circuit_device(self):
        if self._main_circuit_device is None:
            try:
                self._main_circuit_device = PyTango.DeviceProxy(self.MainCoil)
            except (PyTango.DevFailed, PyTango.ConnectionFailed) as df:
                self.debug_stream("Failed to get main circuit proxy\n" + df[0].desc)
                self.set_state(PyTango.DevState.FAULT)
        return self._main_circuit_device

    ###############################################################################
    #
    @property
    def trim_circuit_device(self):
        if self._trim_circuit_device is None:
            try:
                self._trim_circuit_device = PyTango.DeviceProxy(self.TrimCoil)
            except (PyTango.DevFailed, PyTango.ConnectionFailed) as df:
                self.debug_stream("Failed to get main circuit proxy\n" + df[0].desc)
                self.set_state(PyTango.DevState.FAULT)
        return self._trim_circuit_device

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
    def get_main_circuit_state(self):

        if self.main_circuit_device:
            try:
                cir_state = self.main_circuit_device.State()
                self.status_str_cir = "Connected to main circuit %s in state %s " % (self.MainCoil, cir_state)
            except PyTango.DevFailed as e:
                self.status_str_cir = "Cannot get state of main circuit device " + self.MainCoil
                self.debug_stream(self.status_str_cir)
                cir_state =PyTango.DevState.FAULT
        else:
            self.status_str_cir = "Cannot get proxy to main coil " + self.MainCoil
            cir_state = PyTango.DevState.FAULT
        return cir_state

    ###############################################################################
    #
    def get_trim_circuit_state(self):

        if self.trim_circuit_device:
            try:
                cir_state = self.trim_circuit_device.State()
                self.status_str_trm = "Connected to trim circuit %s in state %s " % (self.TrimCoil, cir_state)
            except PyTango.DevFailed as e:
                self.status_str_trm = "Cannot get state of trim circuit device " + self.TrimCoil
                self.debug_stream(self.status_str_trm)
                cir_state =PyTango.DevState.FAULT
        else:
            self.status_str_trm = "Cannot get proxy to trim coil " + self.TrimCoil
            cir_state = PyTango.DevState.FAULT
        return cir_state

    ###############################################################################
    #
    def always_executed_hook(self):

        self.debug_stream("In always_excuted_hook()")

        #There should be a main coil
        if self.MainCoil==None:
            self.set_state(PyTango.DevState.FAULT)
            self.set_status("No main coil defined in properties")
            return
        else:
            #set state according to main circuit state
            self.set_state(self.get_main_circuit_state())
            #get the current and calc the field
            #self.get_main_current_and_field()            

        #Maybe also a trim coil
        if self.TrimCoil!=None:
            print "also a trim coil"
            self.set_state(self.get_trim_circuit_state())

        #get interlock state
        self.check_interlock()

        #set status message
        msg = self.status_str_cfg +"\n"+ self.status_str_cir +"\n"+ self.status_str_trm +"\n" + self.status_str_ilock
        self.set_status(os.linesep.join([s for s in msg.splitlines() if s]))


    #-----------------------------------------------------------------------------
    #    Magnet read/write attribute methods
    #-----------------------------------------------------------------------------

    #Special function to set zeroth element of field vector to zero, as it should be for dipoles
    #(We use the zeroth element to store theta, but should not be returned)
    def convert_dipole_vector(self,vector):
        returnvector = list(vector)
        returnvector[0]=np.NAN
        return returnvector

    #

    def get_main_current_and_field(self):

        print "in get current and field"

        if self.main_circuit_device:
            try:
                print "will read current"
                Current = self.main_circuit_device.currentActual
                print "will read brho"
                BRho = self.main_circuit_device.BRho
                #self.status_str_cir_i = "Read current from main coil " + self.TrimCoil
            except PyTango.DevFailed as e:
                #self.status_str_cir_i = "Cannot get state of current from circuit device " + self.MainCoil
                self.debug_stream("Cannot get state or current from circuit device " + self.MainCoil)
                return False            
            else:
                print "will calc field"
                (MainFieldComponent_r, MainFieldComponent_w, self.fieldA_main, self.fieldANormalised_main, self.fieldB_main, self.fieldBNormalised_main) \
                    = calculate_fields(self.allowed_component, self.currentsmatrix, self.fieldsmatrix, BRho, self.PolTimesOrient, self.Tilt, self.Type, self.Length, Current, None, self.is_sole)
                return True
        else:
            self.debug_stream("Cannot get proxy to main coil " + self.MainCoil)
            #self.status_str_cir_i = "Cannot get proxy to main coil " + self.MainCoil
            return False

    #

    def get_trim_field(self):

        print "in get trim field"

        if self.trim_circuit_device:
            try:
                self.fieldA_trim = self.trim_circuit_device.fieldA
                #self.status_str_trm_f = "Read field from trim coil " + self.TrimCoil
            except PyTango.DevFailed as e:
                self.debug_stream("Cannot get field from trim circuit device " + self.TrimCoil)
                #self.status_str_trm_f = "Cannot get field from trim circuit device " + self.TrimCoil
                self.fieldA_trim = []
        else:
            #self.status_str_trm_f = "Cannot get proxy to trim coil " + self.TrimCoil
            self.debug_stream("Cannot get proxy to trim coil " + self.TrimCoil)
            self.fieldA_trim = []

    #


    def read_fieldA(self, attr):
        self.debug_stream("In read_fieldA()")

        #get current from main coil and calc field
        #self.get_main_current_and_field()

        #look up field from trim
        if self.TrimCoil!=None:
            self.get_trim_field()

        #do the sum
        attr.set_value(self.fieldA_trim+self.fieldA_main)
     
    def is_fieldA_allowed(self, attr):
        print "seeing if allowed"
        allowed = self.get_main_current_and_field() and self.hasCalibData and self.get_state() not in [PyTango.DevState.FAULT,PyTango.DevState.UNKNOWN] 
        print "in field a allowed", allowed
        return allowed

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
        [PyTango.DevVarStringArray,
         "Associated circuits",
         [ [] ] ],
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
         "Type",
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
        py.add_class(TrimCircuitClass, TrimCircuit,'TrimCircuit')

        U = PyTango.Util.instance()
        U.server_init()
        U.server_run()

    except PyTango.DevFailed,e:
        print '-------> Received a DevFailed exception:',e
    except Exception,e:
        print '-------> An unforeseen exception occured....',e

if __name__ == '__main__':
    main()
