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

__all__ = ["MagnetCircuit", "MagnetCircuitClass", "main"]

__docformat__ = 'restructuredtext'

import PyTango
import sys

class MagnetCircuit (PyTango.Device_4Impl):

    #--------- Add you global variables here --------------------------

    def __init__(self,cl, name):
        PyTango.Device_4Impl.__init__(self,cl,name)
        self.debug_stream("In __init__()")
        MagnetCircuit.init_device(self)

       
    def delete_device(self):
        self.debug_stream("In delete_device()")

    def init_device(self):
        self.debug_stream("In init_device()")
        self.get_device_properties(self.get_device_class())

        print "Magnet type is ", self.Type
        #self.allowed_fieldA_components = []
        #self.allowed_fieldB_components = []
        #self.allowed_Angle = False

        #if self.Type == "kquad":
        #    self.allowed_fieldB_components = []
        #elif self.Type == "ksext":
        #    self.allowed_fieldB_components = []
        #elif self.Type == "csrcsbend":
        #    self.allowed_fieldB_components = []
        #    self.allowed_Angle = True
        #elif self.Type == "hkick":
        #    self.allowed_Angle = True
        #elif self.Type == "vkick":
        #    self.allowed_Angle = True
        #else:
        #    print >> self.log_fatal, 'Magnet type invalid'
        #    sys.exit(1)
        #
        #print "Allowed B components ", self.allowed_fieldB_components

        #initial values for testing
        self.attr_fieldA1 = 1
        self.attr_fieldB1 = 1
        self.attr_fieldA2 = 2
        self.attr_fieldB2 = 2
        self.attr_fieldA3 = 3
        self.attr_fieldB3 = 3

        self.attr_angle = 0.0

        self.set_state(PyTango.DevState.ON)

    def always_executed_hook(self):
        self.debug_stream("In always_excuted_hook()")


    #-----------------------------------------------------------------------------
    #    MagnetCircuit read/write attribute methods
    #-----------------------------------------------------------------------------
    
    def read_fieldA1(self, attr):
        self.debug_stream("In read_fieldA1()")
        attr_fieldA1_read = self.attr_fieldA1
        attr.set_value(attr_fieldA1_read)
        attr.set_write_value(attr_fieldA1_read)
    def write_fieldA1(self, attr):
        self.debug_stream("In write_fieldA1()")
        attr_fieldA1_write=attr.get_write_value()
        self.attr_fieldA1 = attr_fieldA1_write        
    def is_fieldA1_allowed(self, req_type):
        if req_type == PyTango.AttReqType.READ_REQ:
            return True
        else:
            return False
    #
    def read_fieldA2(self, attr):
        self.debug_stream("In read_fieldA2()")
        attr_fieldA2_read = self.attr_fieldA2
        attr.set_value(attr_fieldA2_read)
        attr.set_write_value(attr_fieldA2_read)
    def write_fieldA2(self, attr):
        self.debug_stream("In write_fieldA2()")
        attr_fieldA2_write=attr.get_write_value()
        self.attr_fieldA2 = attr_fieldA2_write        
    def is_fieldA2_allowed(self, req_type):
        if req_type == PyTango.AttReqType.READ_REQ:
             return True
        else:
            return False
    #
    def read_fieldA3(self, attr):
        self.debug_stream("In read_fieldA3()")
        attr_fieldA3_read = self.attr_fieldA3
        attr.set_value(attr_fieldA3_read)
        attr.set_write_value(attr_fieldA3_read)
    def write_fieldA3(self, attr):
        self.debug_stream("In write_fieldA3()")
        attr_fieldA3_write=attr.get_write_value()
        self.attr_fieldA3 = attr_fieldA3_write        
    def is_fieldA3_allowed(self, req_type):
        if req_type == PyTango.AttReqType.READ_REQ:
            return True
        else:
            return False

    def read_fieldB1(self, attr):
        self.debug_stream("In read_fieldB1()")
        attr_fieldB1_read = self.attr_fieldB1
        attr.set_value(attr_fieldB1_read)
        attr.set_write_value(attr_fieldB1_read)
    def write_fieldB1(self, attr):
        self.debug_stream("In write_fieldB1()")
        attr_fieldB1_write=attr.get_write_value()
        self.attr_fieldB1 = attr_fieldB1_write
    def is_fieldB1_allowed(self, req_type):
        if req_type == PyTango.AttReqType.READ_REQ:
            return True
        else:
            return False
    #
    def read_fieldB2(self, attr):
        self.debug_stream("In read_fieldB2()")
        attr_fieldB2_read = self.attr_fieldB2
        attr.set_value(attr_fieldB2_read)
        attr.set_write_value(attr_fieldB2_read)
    def write_fieldB2(self, attr):
        self.debug_stream("In write_fieldB2()")
        attr_fieldB2_write=attr.get_write_value()
        self.attr_fieldB2 = attr_fieldB2_write
    def is_fieldB2_allowed(self, req_type):
        if req_type == PyTango.AttReqType.READ_REQ:
            return True
        else:
            if self.Type == "kquad":
                return True
            else:
                return False
    #
    def read_fieldB3(self, attr):
        self.debug_stream("In read_fieldB3()")
        attr_fieldB3_read = self.attr_fieldB3
        attr.set_value(attr_fieldB3_read)
        attr.set_write_value(attr_fieldB3_read)
    def write_fieldB3(self, attr):
        self.debug_stream("In write_fieldB3()")
        attr_fieldB3_write=attr.get_write_value()
        self.attr_fieldB3 = attr_fieldB3_write
    def is_fieldB3_allowed(self, req_type):
        if req_type == PyTango.AttReqType.READ_REQ:
            return True
        else:
            return False

    def read_angle(self, attr):
        self.debug_stream("In read_angle()")
        attr_angle_read = self.attr_angle
        attr.set_value(attr_angle_read)
        attr.set_write_value(attr_angle_read)
    def write_angle(self, attr):
        self.debug_stream("In write_angle()")
        attr_angle_write=attr.get_write_value()
        self.attr_angle = attr_angle_write

            
    def read_attr_hardware(self, data):
        self.debug_stream("In read_attr_hardware()")

    #-----------------------------------------------------------------------------
    #    MagnetCircuit command methods
    #-----------------------------------------------------------------------------

    def On(self):
        self.debug_stream("In On()")
        self.set_state(PyTango.DevState.ON)   

    def is_On_allowed(self):
        return True

    def Off(self):
        self.debug_stream("In Off()")
        self.set_state(PyTango.DevState.OFF)   

    def is_Off_allowed(self):
        return True


class MagnetCircuitClass(PyTango.DeviceClass):


    #Class Properties
    class_property_list = {
        }


    #Device Properties
    device_property_list = {
        'PowerSupply':
            [PyTango.DevString,
            "Associated powersupply",
            [ "not set" ] ],
        'Magnets':
            [PyTango.DevVarStringArray,
            "List of magnets on this circuit",
            [ "not set" ] ],
        'Type':
            [PyTango.DevString,
            "Magnet type",
            [ "not set" ] ],
        }


    #Command definitions    #    Command definitions
    cmd_list = {
        'On':
            [[PyTango.DevVoid, ""],
            [PyTango.DevBoolean, ""]],
        'Off':
            [[PyTango.DevVoid, ""],
            [PyTango.DevBoolean, ""]],
        }


    #Attribute definitions
    attr_list = {
        'fieldA1':
            [[PyTango.DevFloat,
              PyTango.SCALAR,
              PyTango.READ_WRITE],
             {
                'description': "field A1 components",
                'label': "field A1",
                } ],
        'fieldA2':
            [[PyTango.DevFloat,
              PyTango.SCALAR,
              PyTango.READ_WRITE],
             {
                'description': "field A2 components",
                'label': "field A2",
                } ],
        'fieldA3':
            [[PyTango.DevFloat,
              PyTango.SCALAR,
              PyTango.READ_WRITE],
             {
                'description': "field A3 components",
                'label': "field A3",
                } ],
        'fieldB1':
            [[PyTango.DevFloat,
              PyTango.SCALAR,
              PyTango.READ_WRITE],
             {
                'description': "field B1 components",
                'label': "field B1",
                } ],
        'fieldB2':
            [[PyTango.DevFloat,
              PyTango.SCALAR,
              PyTango.READ_WRITE],
             {
                'description': "field B2 components",
                'label': "field B2",
                } ],
        'fieldB3':
            [[PyTango.DevFloat,
              PyTango.SCALAR,
              PyTango.READ_WRITE],
             {
                'description': "field B3 components",
                'label': "field B3",
                } ],
        'angle':
            [[PyTango.DevFloat,
              PyTango.SCALAR,
              PyTango.READ_WRITE],
             {
                'description': "bendling angle for dipoles",
                'label': "angle",
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
