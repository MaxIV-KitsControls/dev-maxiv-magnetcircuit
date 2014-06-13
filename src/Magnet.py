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
        PyTango.Device_4Impl.__init__(self,cl,name)
        self.debug_stream("In __init__()")
        Magnet.init_device(self)

       
    def delete_device(self):
        self.debug_stream("In delete_device()")

    def init_device(self):
        self.debug_stream("In init_device()")
        self.get_device_properties(self.get_device_class())

        self.debug_stream("Circuit device proxy: ", self.CircuitProxies)

        self.status_str = ""
        self.fieldA           = []
        self.fieldANormalised = []
        self.fieldB           = []
        self.fieldBNormalised = []
      
        self.FieldQuality  = PyTango.AttrQuality.ATTR_VALID

        #Get proxy to circuit (only ever one?). If cannot connect may as well exit since probably misconfigured
        try:
            self.CircuitDev  = PyTango.DeviceProxy(self.CircuitProxies)
            self.status_str = "Connected to circuit device " + self.CircuitProxies
        except PyTango.DevFailed as e:
            self.debug_stream("Cannot connect to circuit device " + self.CircuitProxies)
            sys.exit(1)

        #if connected try to read field and state
        self.get_circuit_state()

        #Get attribute proxy to interlock tag in OPC access device
        #This is a vector of strings of the form [device,tag attribute,description]
        self.TempInterlockQuality = PyTango.AttrQuality.ATTR_VALID
        self.TempInterlockValue   = False
        #First see if we gave any interlock information in the property
        try:
            self.interlock_attribute = self.TemperatureInterlock[0]+"/"+ self.TemperatureInterlock[1]
        except Exception as e:
            self.interlock_attribute = None
            self.TempInterlockQuality = PyTango.AttrQuality.ATTR_INVALID
            self.status_str = self.status_str + "\n" + "No interlock tag specified"

        #check interlocks
        self.check_interlock()


    def check_interlock(self):

        #If we gave an interlock property, try to get that attribute
        if  self.interlock_attribute is not None:
            try:
                self.TempInterlockValue  = PyTango.AttributeProxy(self.interlock_attribute).read().value
                if self.TempInterlockValue == True:
                    if "Interlock is True" not in  self.status_str:
                        self.status_str =  self.status_str + "\n" + "Interlock is True! " + self.interlock_attribute
                    self.set_state(PyTango.DevState.ALARM)  

            except PyTango.DevFailed as e:
                self.debug_stream("Exception getting interlock AttributeProxy ", e)
                self.TempInterlockQuality = PyTango.AttrQuality.ATTR_INVALID
                self.status_str =  self.status_str + "\n" + "Cannot read specified interlock tag "



    def get_circuit_state(self):

        try:
            self.set_state(self.CircuitDev.State())

            fieldA_q  = self.CircuitDev.read_attribute("fieldA").quality
            fieldB_q  = self.CircuitDev.read_attribute("fieldA").quality
            fieldAN_q = self.CircuitDev.read_attribute("fieldA").quality
            fieldBN_q = self.CircuitDev.read_attribute("fieldA").quality

            if PyTango.AttrQuality.ATTR_INVALID in [fieldA_q, fieldB_q, fieldAN_q, fieldBN_q]:
                
                self.FieldQuality  = PyTango.AttrQuality.ATTR_INVALID
                if "Fields not calculated by circuit device" not in self.status_str:
                    self.status_str =  self.status_str + "\n" + "Fields not calculated by circuit device"
                    
            else:
                self.fieldA = (self.CircuitDev.fieldA)
                self.fieldB = (self.CircuitDev.fieldB)
                self.fieldANormalised = (self.CircuitDev.fieldANormalised)
                self.fieldBNormalised = (self.CircuitDev.fieldBNormalised)

        except PyTango.DevFailed as e:
            self.FieldQuality =  PyTango.AttrQuality.ATTR_INVALID
            self.debug_stream('Cannot read field from circuit ' + self.PowerSupplyProxy) 
            if "Cannot read field from circuit" not in self.status_str:
                self.status_str = self.status_str + "\n" + "Cannot read field from circuit"

        self.set_status(self.status_str)
                           

    def always_executed_hook(self):
        self.debug_stream("In always_excuted_hook()")
        self.get_circuit_state()
        self.check_interlock()

    #-----------------------------------------------------------------------------
    #    Magnet read/write attribute methods
    #-----------------------------------------------------------------------------
    
    def read_fieldA(self, attr):
        self.debug_stream("In read_fieldA()")
        attr.set_value(self.fieldA)
        attr.set_quality(self.FieldQuality)

    def read_fieldB(self, attr):
        self.debug_stream("In read_fieldB()")
        attr.set_value(self.fieldB)
        attr.set_quality(self.FieldQuality)

    def read_fieldANormalised(self, attr):
        self.debug_stream("In read_fieldANormalised()")
        attr.set_value(self.fieldANormalised)
        attr.set_quality(self.FieldQuality)

    def read_fieldBNormalised(self, attr):
        self.debug_stream("In read_fieldBNormalised()")
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
        'Tilt':
            [PyTango.DevShort,
            "Tilt",
            [ 0.0 ] ],
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
