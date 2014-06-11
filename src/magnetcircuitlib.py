#!/usr/bin/env python
# -*- coding:utf-8 -*-

###############################################################################
##     This contains the functions for calculating all field components given
##     a current, or a current given the requested value of the field 
##     component of interest
##
##     This is kept separate from the Tango device and could be tested standalone
##
###############################################################################


import numpy as np
from math import sqrt

_maxdim = 10 #Maximum number of multipole components

def calculate_fields(allowed_component, currentsmatrix, fieldsmatrix, brho, tilt, length, energy, actual_current):

    fieldA = [0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0]
    fieldB = [0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0]
    fieldANormalised = [0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0]
    fieldBNormalised = [0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0]
    thiscomponent = 0.0

    #We calculate all field components which will include the one we already set
    #This uses the actual current in the PS, not the set current

    #We set all the field components, not just the allowed one:
    for i in range (0,_maxdim):

        calcfield = np.interp(actual_current, currentsmatrix[i], fieldsmatrix[i]) / (brho*length) 
        calcfield_norm = calcfield/energy

        if tilt == 0:
            fieldB[i] = calcfield
            fieldBNormalised[i] = calcfield_norm
            if i==allowed_component:
                #print "Setting this component", fieldB[i] 
                thiscomponent=fieldB[allowed_component]
        else:
            fieldA[i] = calcfield 
            fieldANormalised[i] = calcfield_norm 
            if i==allowed_component:
                #print "Setting this component", fieldA[i]
                thiscomponent=fieldA[allowed_component]

    return thiscomponent, fieldA, fieldANormalised, fieldB, fieldBNormalised

def calculate_current(allowed_component, currentsmatrix, fieldsmatrix, brho, tilt, length, energy, fieldA, fieldB):
    
    #print "In calculate_current, showing conversion data for multipole component ", allowed_component,
    #"\n",fieldsmatrix[allowed_component],
    #"\n",currentsmatrix[allowed_component]

    if tilt == 0:
        requested_field = fieldB[allowed_component]
    else:
        requested_field = fieldA[allowed_component]
        
    #Use numpy to interpolate. We only deal with the allowed component. Assume no need to extrapolate
    intB = requested_field*brho*length
    calc_current = np.interp(intB, fieldsmatrix[allowed_component], currentsmatrix[allowed_component])

    return calc_current
