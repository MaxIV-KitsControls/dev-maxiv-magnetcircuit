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

def calculate_fields(allowed_component, currentsmatrix, fieldsmatrix, brho,  poltimesorient, tilt, maglen, actual_current, set_current=None, is_sole=False):

    #print " +++++++++++ in CF +++++++++++++++ ", set_current, is_sole
    #Calculate all field components which will include the one we already set, using actual current in PS
    #Allowed component is zero for solenoids and dipoles, but need to distinguish between them with ugly is_sole flag

    fieldA = [np.NAN]*10
    fieldB = [np.NAN]*10
    fieldANormalised = [np.NAN]*10
    fieldBNormalised = [np.NAN]*10
    thiscomponent = 0.0

    #We set all the field components, not just the allowed one:
    for i in range (0,_maxdim):

        #NB: i=0 for dipoles, 1 for quad, 2 for sext
        #There is an extra sign, 1 for dipoles, -1 for quads and sext
        #for dipoles and solenoids do not integrate by length
        if i == 0:
            sign =  1
            length = 1.0
        if i == 1:
            sign =  -1
            length = maglen
        if i == 2:
            sign =  -1
            length = maglen

        #For a quad: Given a current we get back k1 * length * BRho
        #k1 * BRho is the element of fieldB, k1 is the element of fieldB_norm

        calcfield = sign * poltimesorient * np.interp(actual_current, currentsmatrix[i], fieldsmatrix[i]) / length 
        calcfield_norm = calcfield / brho

        if set_current is not None:
            setfield = sign * poltimesorient * np.interp(set_current, currentsmatrix[i], fieldsmatrix[i]) / length 
        else:
            setfield = np.NAN
        setfield_norm  = setfield / brho
            
        #For a sext: Given a current we get back k2 * length/2 * BRho
        #k2 * BRho is the element of fieldB, k2 is the element of fieldB_norm
        if i == 2:
            calcfield      = calcfield*2.0
            calcfield_norm = calcfield_norm*2.0
            setfield_norm  = setfield_norm*2.0

        #For a dip: Given a current we get back theta * BRho
        #NB theta (theta * BRho) is NOT the zeroth element of fieldB (fieldB normalised) but store it there anyway
        #See wiki page for details

        #For a sole, get back B_s directly, no scaling by brho

        if tilt == 0:
            fieldB[i] = calcfield
            fieldBNormalised[i] = calcfield_norm
            if i==allowed_component:
                #print "Setting this component", fieldB[i] 
                thiscomponent=calcfield_norm
                thissetcomponent=setfield_norm
                if is_sole:
                    thiscomponent = calcfield
                    thissetcomponent=setfield

        else:
            fieldA[i] = calcfield 
            fieldANormalised[i] = calcfield_norm 
            if i==allowed_component:
                #print "Setting this component", fieldA[i]
                thiscomponent=calcfield_norm
                thissetcomponent=setfield_norm
                if is_sole:
                    thiscomponent = calcfield
                    thissetcomponent=setfield

    return thiscomponent, thissetcomponent, fieldA, fieldANormalised, fieldB, fieldBNormalised

def calculate_current(allowed_component, currentsmatrix, fieldsmatrix, brho, poltimesorient, tilt, length, fieldA, fieldB, is_sole=False):
    

    #print " +++++++++++ in CF +++++++++++++++ ", fieldB, is_sole
    #For quad: given k1 * length * BRho (call it intBtimesBRho) we get a current
    #For sext: given k2 * length/2.0 * BRho (call it intBtimesBRho) we get a current
    #for dip   given theta *  BRho (call it intBtimesBRho) we get a current
    #For sole, given bs we get a current

    #For quad: k1 * BRho is the element of fieldB

    #There is an extra sign, 1 for dipoles, -1 for quads and sext
    sign = -1
    #in addition, for dipoles and solenoids do not integrate by length
    if allowed_component == 0:
        sign =  1
        length = 1.0

    if tilt == 0:
        intBtimesBRho = fieldB[allowed_component]*length * poltimesorient * sign
    else:
        intBtimesBRho = fieldA[allowed_component]*length * poltimesorient * sign
        
    if allowed_component == 2:
            intBtimesBRho  = intBtimesBRho/2.0

    #if a solenoid, no brho factor
    if is_sole:
        intBtimesBRho = intBtimesBRho / brho

    #Use numpy to interpolate. We only deal with the allowed component. Assume no need to extrapolate

    #note usage is like
    #xp = [1,2,3]
    #yp = [3,2,1]
    #interp(2.5,xp,yp) = 1.5
    #so here xp is the field and yp the current - put in a field value to get the current
    #xp must be increasing hence matrices are ordered

    #so, if fields starts with a positive sign, reverse both so that fields starts negative
    if fieldsmatrix[allowed_component][0] > 0.0:
        fields_o   = fieldsmatrix[allowed_component][::-1]
        currents_o = currentsmatrix[allowed_component][::-1]
    else:
        fields_o   = fieldsmatrix[allowed_component]
        currents_o = currentsmatrix[allowed_component]


    calc_current = np.interp(intBtimesBRho, fields_o, currents_o)

    return calc_current
