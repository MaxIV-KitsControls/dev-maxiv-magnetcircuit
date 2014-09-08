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
import sys

class Magnet (PyTango.Device_4Impl):

    #--------- Add you global variables here --------------------------

    def __init__(self,cl, name):
        self._state = None
        PyTango.Device_4Impl.__init__(self,cl,name)
        self.debug_stream("In __init__()")
        Magnet.init_device(self)

        self.set_change_event('State', True, False)
       
    def delete_device(self):
        self.debug_stream("In delete_device()")

    def init_device(self):
        self.debug_stream("In init_device()")
        self.get_device_properties(self.get_device_class())

        self.debug_stream("Circuit device proxy: %s " % self.CircuitProxies)

        self.status_str_1 = ""
        self.status_str_2 = ""
        self.status_str_3 = ""
        self.fieldA           = []
        self.fieldANormalised = []
        self.fieldB           = []
        self.fieldBNormalised = []
      
        self.FieldQuality  = PyTango.AttrQuality.ATTR_VALID

        self.TempInterlockQuality = PyTango.AttrQuality.ATTR_VALID
        self.TempInterlockValue   = False
        self.TempInterProxy       = None 

        #try to connect to circuit device
        self.connect_to_circuit()

        #if connected, try to read state
        self.get_circuit_state()

        #Get attribute proxy to interlock tag in OPC access device
        self.get_interlock_config()

    def connect_to_circuit:
        #Get proxy to circuit (only ever one?). 
        try:
            self.CircuitDev  = PyTango.DeviceProxy(self.CircuitProxies)
            self.status_str_1 = "Connected to circuit device " + self.CircuitProxies
        except PyTango.DevFailed as e:
            msg = "Cannot connect to circuit device %s " % self.CircuitProxies
            self.debug_stream(msg)
            self.status_str_1 = msg
            self.set_state(PyTango.DevState.FAULT)  
            self.set_status(self.status_str_1)

    def get_circuit_state():
        if self.get_state() is not PyTango.DevState.FAULT:
            try:
                self.set_state(self.CircuitDev.State())
            except PyTango.DevFailed as e:
                msg = "Cannot get state of circuit device " + self.CircuitProxies
                self.debug_stream(msg)
                self.status_str_1 = msg
                self.set_state(PyTango.DevState.FAULT)  
                self.set_status(self.status_str_1)

    def get_interlock_config(self):
        if self.get_state() is not PyTango.DevState.FAULT:
            #This is a vector of strings of the form [device,tag attribute,description]
            #First see if we gave any interlock information in the property
            try:
                self.interlock_attribute = self.TemperatureInterlock[0]+"/"+ self.TemperatureInterlock[1]
                self.TempInterProxy  = PyTango.AttributeProxy(self.interlock_attribute)
            except Exception as e:
                self.interlock_attribute = None
                self.TempInterlockQuality = PyTango.AttrQuality.ATTR_INVALID
                self.status_str_1 =  "Cannot read interlock %s " % self.interlock_attribute

            #check interlocks
            self.check_interlock()



    def check_interlock(self):

        self.status_str_2 = ""
        #If we gave an interlock property, try to get that attribute
        if  self.interlock_attribute is not None:
            try:
                self.TempInterlockValue  = self.TempInterProxy.read().value
                if self.TempInterlockValue == True:
                    self.status_str_2 = "Interlock is True! " + self.interlock_attribute + " (" + self.TemperatureInterlock[2] + ")"
                    self.set_state(PyTango.DevState.ALARM)  
                else:
                    self.status_str_2 = "No Interlock"

            except PyTango.DevFailed as e:
                self.debug_stream("Exception getting interlock AttributeProxy %s" % e)
                self.TempInterlockQuality = PyTango.AttrQuality.ATTR_INVALID
                self.status_str_2 = "Cannot read specified interlock tag "

        else:
            self.status_str_2 =  "No interlock tag specified"


    def set_state(self, new_state):
        PyTango.Device_4Impl.set_state(self, new_state)
        self.push_change_event("State", new_state)


    def always_executed_hook(self):

        self.debug_stream("In always_excuted_hook()")
        self.FieldQuality  = PyTango.AttrQuality.ATTR_VALID

        #get circuit state
        self.get_circuit_state()
        #get interlock state
        self.check_interlock()

    #-----------------------------------------------------------------------------
    #    Magnet read/write attribute methods
    #-----------------------------------------------------------------------------
    
    def read_fieldA(self, attr):
        self.debug_stream("In read_fieldA()")
        self.status_str_3 = ""
        try:
            fieldA_q  = self.CircuitDev.read_attribute("fieldA").quality
            if PyTango.AttrQuality.ATTR_INVALID == fieldA_q:
                self.FieldQuality  = PyTango.AttrQuality.ATTR_INVALID
                self.status_str_3 =  "Field A not calculated by circuit device"
            else: 
                self.fieldA = (self.CircuitDev.fieldA)
                self.status_str_3 =  "Fields calculated by circuit device"
        except PyTango.DevFailed as e:
            self.FieldQuality =  PyTango.AttrQuality.ATTR_INVALID
            self.debug_stream('Cannot read field A from circuit %s ' % self.CircuitProxies) 
            self.status_str_3  = "Cannot read field A from circuit"

        self.set_status(self.status_str_1 + "\n" + self.status_str_2 + "\n" +  self.status_str_3)       
        attr.set_value(self.fieldA)
        attr.set_quality(self.FieldQuality)

    def read_fieldB(self, attr):
        self.debug_stream("In read_fieldB()")
        self.status_str_3 = ""
        try:
            fieldB_q  = self.CircuitDev.read_attribute("fieldB").quality
            if PyTango.AttrQuality.ATTR_INVALID == fieldB_q:
                self.FieldQuality  = PyTango.AttrQuality.ATTR_INVALID
                self.status_str_3 =  "Field B not calculated by circuit device"
            else:
                self.fieldB = (self.CircuitDev.fieldB)
                self.status_str_3 =  "Fields calculated by circuit device"
        except PyTango.DevFailed as e:
            self.FieldQuality =  PyTango.AttrQuality.ATTR_INVALID
            self.debug_stream('Cannot read field B from circuit %s ' % self.CircuitProxies) 
            self.status_str_3  = "Cannot read field B from circuit"

        self.set_status(self.status_str_1 + "\n" + self.status_str_2 + "\n" +  self.status_str_3)       
        attr.set_value(self.fieldB)
        attr.set_quality(self.FieldQuality)

    def read_fieldANormalised(self, attr):
        self.debug_stream("In read_fieldANormalised()")
        self.status_str_3 = ""
        try:
            fieldAN_q  = self.CircuitDev.read_attribute("fieldANormalised").quality
            if PyTango.AttrQuality.ATTR_INVALID == fieldAN_q:
                self.FieldQuality  = PyTango.AttrQuality.ATTR_INVALID
                self.status_str_3 =  "Field A not calculated by circuit device"
            else:
                self.fieldANormalised = (self.CircuitDev.fieldANormalised)
                self.status_str_3 =  "Fields calculated by circuit device"
        except PyTango.DevFailed as e:
            self.FieldQuality =  PyTango.AttrQuality.ATTR_INVALID
            self.debug_stream('Cannot read field A from circuit %s ' % self.CircuitProxies) 
            self.status_str_3  = "Cannot read field A from circuit"

        self.set_status(self.status_str_1 + "\n" + self.status_str_2 + "\n" +  self.status_str_3)   
        attr.set_value(self.fieldANormalised)
        attr.set_quality(self.FieldQuality)

    def read_fieldBNormalised(self, attr):
        self.debug_stream("In read_fieldBNormalised()")
        self.status_str_3 = ""
        try:
            fieldBN_q  = self.CircuitDev.read_attribute("fieldBNormalised").quality
            if PyTango.AttrQuality.ATTR_INVALID == fieldBN_q:
                self.FieldQuality  = PyTango.AttrQuality.ATTR_INVALID
                self.status_str_3 =  "Field B not calculated by circuit device"
            else:
                self.fieldBNormalised = (self.CircuitDev.fieldBNormalised)
                self.status_str_3 =  "Fields calculated by circuit device"
        except PyTango.DevFailed as e:
            self.FieldQuality =  PyTango.AttrQuality.ATTR_INVALID
            self.debug_stream('Cannot read field B from circuit %s ' % self.CircuitProxies) 
            self.status_str_3  = "Cannot read field B from circuit"

        self.set_status(self.status_str_1 + "\n" + self.status_str_2 + "\n" +  self.status_str_3)   
        attr.set_value(self.fieldBNormalised)
        attr.set_quality(self.FieldQuality)

    def read_temperatureInterlock(self, attr):
        self.debug_stream("In read_temperatureInterlock()")
        attr.set_value(self.TempInterlockValue)
        attr.set_quality(self.TempInterlockQuality)

    def read_attr_hardware(self, data):
        self.debug_stream("In read_attr_hardware()")

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
            [ "not set" ] ],
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
        'temperatureInterlock':
            [[PyTango.DevBoolean,
              PyTango.SCALAR,
              PyTango.READ],
             {
                'description': "temperature interlock from PLC device",
		'label': "temperature interlock",
                'unit': "T/F",
                } ],
        #'energy':
        #    [[PyTango.DevFloat,
        #      PyTango.SCALAR,
        #      PyTango.READ_WRITE],
        #     {
        #        'description': "electron energy",
	#	'label': "electron energy",
        #        'unit': "MeV",
        #       } ],
        }


def main():
    try:
        py = PyTango.Util(sys.argv)
        py.add_class(MagnetClass,Magnet,'Magnet')

        U = PyTango.Util.instance()
        U.server_init()
        U.server_run()

    except PyTango.DevFailed,e:
        print '-------> Received a DevFailed exception:',e
    except Exception,e:
        print '-------> An unforeseen exception occured....',e

if __name__ == '__main__':
    main()
