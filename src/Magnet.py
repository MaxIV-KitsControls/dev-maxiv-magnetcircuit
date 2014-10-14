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
import sys

class Magnet (PyTango.Device_4Impl):

    #--------- Add you global variables here --------------------------

    def __init__(self,cl, name):
        self._state = None
        PyTango.Device_4Impl.__init__(self,cl,name)
        self.debug_stream("In __init__()")
        Magnet.init_device(self)

    def delete_device(self):
        self.debug_stream("In delete_device()")

    def init_device(self):
        self.debug_stream("In init_device()")        
        self.set_state(PyTango.DevState.INIT)

        self.get_device_properties(self.get_device_class())

        #Proxy to power supply device
        self.debug_stream("Circuit device proxy: %s " % self.CircuitProxies)
        self._circuit_device = None

        #Some status strings
        self.status_str_ilock = ""
        self.status_str_field = ""

        #interlock config
        self.interlock_descs   = {}
        self.interlock_proxies = {}
        self.bad_Ilock_config = False
        self.get_interlock_config()

        self.set_state(PyTango.DevState.ON)

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
    def get_circuit_state(self):

        if self.circuit_device:
            try:
                cir_state = self.circuit_device.State()
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
        self.set_state(self.get_circuit_state())

        #get interlock state
        self.check_interlock()

        #set status message
        msg = self.status_str_cir +"\n"+ self.status_str_ilock +"\n"+ self.status_str_field
        self.set_status(os.linesep.join([s for s in msg.splitlines() if s]))


    #-----------------------------------------------------------------------------
    #    Magnet read/write attribute methods
    #-----------------------------------------------------------------------------
    
    def read_fieldA(self, attr):
        self.debug_stream("In read_fieldA()")
        self.status_str_field = ""
        try:
            #fieldA_q  = self.CircuitDev.read_attribute("fieldA").quality
            #if PyTango.AttrQuality.ATTR_INVALID == fieldA_q:
            #    self.status_str_field =  "Field A not calculated by circuit device"
            #else: 
            self.fieldA = (self.circuit_device.fieldA)
            #self.status_str_field =  "Fields calculated by circuit device"
            attr.set_quality(PyTango.AttrQuality.VALID)
            attr.set_value(self.fieldA)
        except PyTango.DevFailed as e:
            self.debug_stream('Cannot read field A from circuit %s ' % self.CircuitProxies) 
            self.status_str_field = "Cannot read field A from circuit"
            attr.set_quality(PyTango.AttrQuality.ATTR_INVALID)


    def is_fieldA_allowed(self, attr):
        return self.get_state() not in [PyTango.DevState.FAULT,PyTango.DevState.UNKNOWN]
  
    def read_fieldB(self, attr):
        self.debug_stream("In read_fieldB()")
        self.status_str_field = ""
        try:
            #fieldB_q  = self.CircuitDev.read_attribute("fieldB").quality
            #if PyTango.AttrQuality.ATTR_INVALID == fieldB_q:
            #    self.status_str_field =  "Field B not calculated by circuit device"
            #else:
            self.fieldB = (self.circuit_device.fieldB)
            #self.status_str_field =  "Fields calculated by circuit device"
            attr.set_quality(PyTango.AttrQuality.VALID)
            attr.set_value(self.fieldB)
        except PyTango.DevFailed as e:
            self.debug_stream('Cannot read field B from circuit %s ' % self.CircuitProxies) 
            self.status_str_field  = "Cannot read field B from circuit"
            attr.set_quality(PyTango.AttrQuality.ATTR_INVALID)



    def is_fieldB_allowed(self, attr):
        return self.get_state() not in [PyTango.DevState.FAULT,PyTango.DevState.UNKNOWN]

    def read_fieldANormalised(self, attr):
        self.debug_stream("In read_fieldANormalised()")
        self.status_str_field = ""
        try:
            #fieldAN_q  = self.CircuitDev.read_attribute("fieldANormalised").quality
            #if PyTango.AttrQuality.ATTR_INVALID == fieldAN_q:
            #    self.status_str_field =  "Field A not calculated by circuit device"
            #else:
            self.fieldANormalised = (self.circuit_device.fieldANormalised)
            #self.status_str_field =  "Fields calculated by circuit device"
            attr.set_quality(PyTango.AttrQuality.VALID)
            attr.set_value(self.fieldANormalised)
        except PyTango.DevFailed as e:
            self.debug_stream('Cannot read field A from circuit %s ' % self.CircuitProxies) 
            self.status_str_field  = "Cannot read field A from circuit"
            attr.set_quality(PyTango.AttrQuality.ATTR_INVALID)


    def is_fieldANormalised_allowed(self, attr):
        return self.get_state() not in [PyTango.DevState.FAULT,PyTango.DevState.UNKNOWN]

    def read_fieldBNormalised(self, attr):
        self.debug_stream("In read_fieldBNormalised()")
        self.status_str_field = ""
        try:
            #fieldBN_q  = self.CircuitDev.read_attribute("fieldBNormalised").quality
            #3if PyTango.AttrQuality.ATTR_INVALID == fieldBN_q:
            #    self.status_str_field =  "Field B not calculated by circuit device"
            #else:
            self.fieldBNormalised = (self.circuit_device.fieldBNormalised)
            #self.status_str_field =  "Fields calculated by circuit device"
            attr.set_quality(PyTango.AttrQuality.VALID)
            attr.set_value(self.fieldBNormalised)
        except PyTango.DevFailed as e:
            self.debug_stream('Cannot read field B from circuit %s ' % self.CircuitProxies) 
            self.status_str_field  = "Cannot read field B from circuit"
            attr.set_quality(PyTango.AttrQuality.ATTR_INVALID)

    def is_fieldBNormalised_allowed(self, attr):
        return self.get_state() not in [PyTango.DevState.FAULT,PyTango.DevState.UNKNOWN]

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

        U = PyTango.Util.instance()
        U.server_init()
        U.server_run()

    except PyTango.DevFailed,e:
        print '-------> Received a DevFailed exception:',e
    except Exception,e:
        print '-------> An unforeseen exception occured....',e

if __name__ == '__main__':
    main()
