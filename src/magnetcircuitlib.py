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

## NOTE PJB THIS VERSION ONLY FOR THE RING SINCE NO FACTORIAL FACTOR!

import numpy as np
from math import sqrt, factorial

_maxdim = 10 #Maximum number of multipole components

def calculate_fields(allowed_component, currentsmatrix, fieldsmatrix, brho,  poltimesorient, tilt, typ, length, actual_current, set_current=None, is_sole=False, find_limit=False):

    #print " +++++++++++ in CF +++++++++++++++ ", actual_current, set_current, is_sole
    #Calculate all field components which will include the one we already set, using actual current in PS
    #Allowed component is zero for solenoids and dipoles, but need to distinguish between them with ugly is_sole flag

    fieldA = [np.NAN]*_maxdim
    fieldB = [np.NAN]*_maxdim
    fieldANormalised = [np.NAN]*_maxdim
    fieldBNormalised = [np.NAN]*_maxdim
    thiscomponent = 0.0

    #We set all the field components, not just the allowed one:
    for i in range (0,_maxdim):

        #Only need to set field elements up to multipole for which we have data.
        #Calib data above are all Nan
        if np.isnan(currentsmatrix[i]).any():
            break

        #If data is all zeroes, can also skip
        #if np.count_nonzero(currentsmatrix[i]) == 0: #not in old version of numpy!
        if np.all(currentsmatrix[i]==0):
            #print "found zeroes"
            continue
        
        #NB: i=0 for dipoles and correctors, 1 for quad, 2 for sext
        #There is an extra sign -1 for quads and sext (i.e. when i is not 0)
        #Vertical correctors (i=0) also get sign -1
        sign = -1
        if i == 0 and typ not in ["vkick","Y_CORRECTOR"]:
            sign =  1

        #For a quad: Given a current we get back k1 * length * BRho
        #k1 * BRho is the element of fieldB, k1 is the element of fieldB_norm

        #If we are finding limit of field, report the limit of the interpolation data
        #If not, and current is beyond interpolation data, return an error
        if not find_limit: 
            if actual_current < currentsmatrix[i][0] or actual_current > currentsmatrix[i][-1]:
                #print "read current out of bounds", actual_current,  currentsmatrix[i][0], currentsmatrix[i][-1]
                return False, None, None, None, None, None, None
            if set_current is not None:
                if set_current < currentsmatrix[i][0] or set_current > currentsmatrix[i][-1]:
                    print "set current out of bounds"
                    return False, None, None, None, None, None, None

        calcfield = sign * poltimesorient * np.interp(actual_current, currentsmatrix[i], fieldsmatrix[i]) / length

        if set_current is not None:
            setfield = sign * poltimesorient * np.interp(set_current, currentsmatrix[i], fieldsmatrix[i]) / length 
        else:
            setfield = np.NAN

        calcfield_norm = calcfield / brho
        setfield_norm  = setfield / brho

        #There is a factor 1/n! (so factor 1/2 for sextupole for which n=2)
        #For a sext: Given a current we get back k2 * length/2 * BRho
        #k2 * BRho is the element of fieldB, k2 is the element of fieldB_norm
        ##factorial_factor = factorial(i)
        ##calcfield      = calcfield*factorial_factor
        ##calcfield_norm = calcfield_norm*factorial_factor
        ##setfield_norm  = setfield_norm*factorial_factor

        #For a dip: Given a current we get back Theta * BRho
        #NB Theta (Theta * BRho) is NOT the zeroth element of fieldB (fieldB normalised) but store it there anyway
        #See wiki page for details
        #For a solenoid, get back B_s directly, no scaling by BRho

        if tilt == 0 and typ not in ["vkick","SKEW_QUADRUPOLE","Y_CORRECTOR"]:
            fieldB[i] = calcfield
            fieldBNormalised[i] = calcfield_norm
            fieldA[i] = 0.0
            fieldANormalised[i] = 0.0
            if i==allowed_component:
                #print "Setting this component", fieldB[i] 
                thiscomponent=calcfield_norm
                thissetcomponent=setfield_norm
                if is_sole:
                    thiscomponent = calcfield
                    thissetcomponent=setfield
                #hack for theta (zeroth component) should not be divided by length
                if  i==0:
                    thiscomponent = calcfield_norm * length
                    thissetcomponent = setfield_norm * length
        else:
            fieldA[i] = calcfield 
            fieldANormalised[i] = calcfield_norm 
            fieldB[i] = 0.0
            fieldBNormalised[i] = 0.0
            if i==allowed_component:
                #print "Setting this component", fieldA[i]
                thiscomponent=calcfield_norm
                thissetcomponent=setfield_norm
                if is_sole:
                    thiscomponent = calcfield
                    thissetcomponent=setfield
                #hack for theta (zeroth component) should not be divided by length
                if  i==0:
                    thiscomponent = calcfield_norm * length
                    thissetcomponent = setfield_norm * length

    return True, thiscomponent, thissetcomponent, fieldA, fieldANormalised, fieldB, fieldBNormalised

def calculate_current(allowed_component, currentsmatrix, fieldsmatrix, brho, poltimesorient, tilt, typ, length, fieldA, fieldB, is_sole=False):
    
    #For quad: given k1 * length * BRho (call it intBtimesBRho) we get a current
    #For sext: given k2 * length/2.0 * BRho (call it intBtimesBRho) we get a current
    #For dip:  given theta *  BRho (call it intBtimesBRho) we get a current
    #For sole: given bs we get a current

    #There is an extra sign -1 for quads and sext (i.e. when i is not 0)
    #Vertical correctors (i=0) also get sign -1
    sign = -1
    if allowed_component == 0 and typ not in ["vkick","Y_CORRECTOR"]:
        sign =  1

    if tilt == 0 and typ not in ["vkick","SKEW_QUADRUPOLE","Y_CORRECTOR"]:
        intBtimesBRho = fieldB[allowed_component]*length * poltimesorient * sign
    else:
        intBtimesBRho = fieldA[allowed_component]*length * poltimesorient * sign

    #hack since for theta should not multiply by length
    if allowed_component == 0:
        intBtimesBRho = intBtimesBRho / length

    #if a solenoid, no brho factor
    if is_sole:
        intBtimesBRho = intBtimesBRho / brho

    #n! factor for linac only!?
    ##factorial_factor = factorial(allowed_component)
    ##intBtimesBRho  = intBtimesBRho/factorial_factor

    #Use numpy to interpolate. We only deal with the allowed component. Assume no need to extrapolate
    #note usage is like: xp = [1,2,3], yp = [3,2,1], interp(2.5,xp,yp) = 1.5
    #so here xp is the field and yp the current. xp must be increasing
    #if fields starts with a positive sign, reverse both so that fields starts negative

    if fieldsmatrix[allowed_component][0] > 0.0:
        fields_o   = fieldsmatrix[allowed_component][::-1]
        currents_o = currentsmatrix[allowed_component][::-1]
    else:
        fields_o   = fieldsmatrix[allowed_component]
        currents_o = currentsmatrix[allowed_component]

    calc_current = np.interp(intBtimesBRho, fields_o, currents_o)
    #print "will interp ", intBtimesBRho, fields_o, currents_o, calc_current

    return calc_current
