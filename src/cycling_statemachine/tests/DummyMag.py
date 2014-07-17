#!/usr/bin/env python
# -*- coding:utf-8 -*- 

##    (Program Obviously used to Generate tango Object)
##
##        (c) - Software Engineering Group - ESRF
##############################################################################

"""
simulates the pressure behaviour according to predetermined ramp"""

__all__ = ["DummyPS", "DummyPSClass", "main"]

__docformat__ = 'restructuredtext'

import PyTango
import sys
# Add additional import
#----- PROTECTED REGION ID(DummyIonPump.additionnal_import) ENABLED START -----#
from dummypslib import DummyPSLib
#----- PROTECTED REGION END -----#	//	DummyIonPump.additionnal_import

## Device States Description
## No states for this device

class DummyPS (PyTango.Device_4Impl):

    #--------- Add you global variables here --------------------------
    #----- PROTECTED REGION ID(DummyIonPump.global_variables) ENABLED START -----#
    
    #----- PROTECTED REGION END -----#	//	DummyIonPump.global_variables

    def __init__(self,cl, name):
        PyTango.Device_4Impl.__init__(self,cl,name)
        self.debug_stream("In __init__()")
        DummyPS.init_device(self)
        #----- PROTECTED REGION ID(DummyIonPump.__init__) ENABLED START -----#
        
        #----- PROTECTED REGION END -----#	//	DummyIonPump.__init__
        self.set_state(PyTango.DevState.ON)

        
    def delete_device(self):
        self.debug_stream("In delete_device()")
        #----- PROTECTED REGION ID(DummyIonPump.delete_device) ENABLED START -----#
        
        #----- PROTECTED REGION END -----#	//	DummyIonPump.delete_device

    def init_device(self):
        self.debug_stream("In init_device()")
        self.get_device_properties(self.get_device_class())
        self.attr_Current_read = 0.0
        #----- PROTECTED REGION ID(DummyIonPump.init_device) ENABLED START -----#
        self.dummy = DummyPSLib()
        #----- PROTECTED REGION END -----#	//	DummyIonPump.init_device

    def always_executed_hook(self):
        self.debug_stream("In always_excuted_hook()")
        #----- PROTECTED REGION ID(DummyIonPump.always_executed_hook) ENABLED START -----#
        self.attr_Current_read = self.dummy.getCurrent()
        if self.dummy.getMoving() == True:
            self.set_state(PyTango.DevState.MOVING)
        else:
            self.set_state(PyTango.DevState.ON)
        #----- PROTECTED REGION END -----#	//	DummyIonPump.always_executed_hook

    #-----------------------------------------------------------------------------
    #    DummyIonPump read/write attribute methods
    #-----------------------------------------------------------------------------
    
    def read_Current(self, attr):
        self.debug_stream("In read_Current()")

        #self.attr_Current_read = self.dummy.getCurrent()
        attr.set_value(self.attr_Current_read)

    def write_Current(self, attr):
        self.debug_stream("In write_Current()")
        data = attr.get_write_value()
        self.dummy.setCurrent(data)
        
    def read_attr_hardware(self, data):
        self.debug_stream("In read_attr_hardware()")
        #----- PROTECTED REGION ID(DummyIonPump.read_attr_hardware) ENABLED START -----#
        
        #----- PROTECTED REGION END -----#	//	DummyIonPump.read_attr_hardware


    #-----------------------------------------------------------------------------
    #    DummyIonPump command methods
    #-----------------------------------------------------------------------------
    

        

class DummyPSClass(PyTango.DeviceClass):
    #--------- Add you global class variables here --------------------------
    #----- PROTECTED REGION ID(DummyIonPump.global_class_variables) ENABLED START -----#
    
    #----- PROTECTED REGION END -----#	//	DummyIonPump.global_class_variables


        #----- PROTECTED REGION ID(DummyIonPump.dyn_attr) ENABLED START -----#
        
        #----- PROTECTED REGION END -----#	//	DummyIonPump.dyn_attr

    #    Class Properties
    class_property_list = {
        }


    #    Device Properties
    device_property_list = {
        }


    #    Command definitions
    cmd_list = {
        }


    #    Attribute definitions
    attr_list = {
        'Current':
            [[PyTango.DevDouble,
            PyTango.SCALAR,
            PyTango.READ_WRITE]],
        }


def main():
    try:
        py = PyTango.Util(sys.argv)
        py.add_class(DummyPSClass,DummyPS,'DummyPS')

        U = PyTango.Util.instance()
        U.server_init()
        U.server_run()

    except PyTango.DevFailed,e:
        print '-------> Received a DevFailed exception:',e
    except Exception,e:
        print '-------> An unforeseen exception occured....',e

if __name__ == '__main__':
    main()
