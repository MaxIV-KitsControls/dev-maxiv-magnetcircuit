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

def calculate_fields(allowed_component, setpoints_matrix, fieldsmatrix, brho,  poltimesorient, tilt, typ, length, ps_read_value, ps_set_value=None, is_sole=False, find_limit=False):

    #print " +++++++++++ in CF +++++++++++++++ ", ps_read_value, brho
    #Calculate all field components which will include the one we already set, using actual current in PS
    #Allowed component is zero for solenoids and dipoles, but need to distinguish between them with ugly is_sole flag

    fieldA = np.asarray([np.NAN]*_maxdim)
    fieldB = np.asarray([np.NAN]*_maxdim)
    fieldANormalised = np.asarray([np.NAN]*_maxdim)
    fieldBNormalised = np.asarray([np.NAN]*_maxdim)
    thiscomponent = 0.0

    #NB: i=0 for dipoles and correctors, 1 for quad, 2 for sext
    #We set all the field components for which we have calibration data, not just the allowed ("steering") one:
    for i in range (0,_maxdim):

        #Only need to set field elements up to multipole for which we have data.
        #Calib data above are all Nan
        if np.isnan(setpoints_matrix[i]).any():
            break

        #If data is all zeroes, can also skip
        #if np.count_nonzero(currentsmatrix[i]) == 0: #not in old version of numpy!
        if np.all(setpoints_matrix[i]==0):
            continue
        
        #If we are not just finding the limit of the interpolation data, 
        #if current is beyond interpolation data return an error
        if not find_limit: 
            if ps_read_value < setpoints_matrix[i][0] or ps_read_value > setpoints_matrix[i][-1]:
                #print "read current out of bounds", actual_current,  currentsmatrix[i][0], currentsmatrix[i][-1]
                return False, None, None, None, None, None, None
            if ps_set_value is not None:
                if ps_set_value < setpoints_matrix[i][0] or ps_set_value > setpoints_matrix[i][-1]:
                    #print "set current out of bounds"
                    return False, None, None, None, None, None, None

        #For a quad: Given a current we get back k1 * length * BRho
        #For a sext: Given a current we get back k2 * length * BRho
        #For a kicker: get back theta * BRho
        #For a solenoid, get back B_s directly, no scaling by BRho
        #For a dip:  Given a current we get back Theta * BRho
        #NB Theta (Theta * BRho) is NOT the zeroth element of fieldB (fieldB normalised) but store it there anyway

        #Do the interpolation and divide by length (fix for unwanted theta length factor later)
        
        calcfield = poltimesorient * np.interp(ps_read_value, setpoints_matrix[i], fieldsmatrix[i]) / length
        if ps_set_value is not None:
            setfield = poltimesorient * np.interp(ps_set_value, setpoints_matrix[i], fieldsmatrix[i]) / length
        else:
            setfield = np.NAN

        #k1 * BRho is the element of fieldB, k1 is the element of fieldB_norm, etc
        #
        calcfield_norm = calcfield / brho
        setfield_norm  = setfield / brho

        #There is a factor 1/n! (so factor 1/2 for sextupole for which n=2)
        ##factorial_factor = factorial(i)
        ##calcfield      = calcfield*factorial_factor
        ##calcfield_norm = calcfield_norm*factorial_factor
        ##setfield_norm  = setfield_norm*factorial_factor

        #Fill A or B vector as appropriate
        #
        if tilt == 0 and typ not in ["vkick","SKEW_QUADRUPOLE","Y_CORRECTOR"]:
            fieldB[i] = calcfield
            fieldBNormalised[i] = calcfield_norm
            fieldA[i] = np.NAN
            fieldANormalised[i] = np.NAN
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
            fieldB[i] = np.NAN
            fieldBNormalised[i] = np.NAN
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

    #sign convention for ring
    sign = -1
    if  allowed_component == 0 and typ not in ["vkick","Y_CORRECTOR"]:
        sign =  1

    return True, sign*thiscomponent, sign*thissetcomponent, fieldA, fieldANormalised, fieldB, fieldBNormalised

def calculate_setpoint(allowed_component, setpoints_matrix, fieldsmatrix, brho, poltimesorient, tilt, typ, length, fieldA, fieldB, is_sole=False):
    
    #For quad: calibration data are -1.0 * k1 * length * BRho
    #For sext: calibration data are -1.0 * k2 * length * BRho
    #For dip:  calibration data are theta *  BRho
    #For sole: calibration data are Bs directly
    #For the above, steering variable are k1, k2, theta and Bs respectively

    #Take data from A or B vector as appropriate, apply extra sign factor
    #Vector elements already have the BRho factor in them
    #
    if tilt == 0 and typ not in ["vkick","SKEW_QUADRUPOLE","Y_CORRECTOR"]:
        intBtimesBRho = fieldB[allowed_component]*length * poltimesorient 
    else:
        intBtimesBRho = fieldA[allowed_component]*length * poltimesorient 

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
        currents_o = setpoints_matrix[allowed_component][::-1]
    else:
        fields_o   = fieldsmatrix[allowed_component]
        currents_o = setpoints_matrix[allowed_component]

    calc_current = np.interp(intBtimesBRho, fields_o, currents_o)
    #print "will interp ", intBtimesBRho, fields_o, currents_o, calc_current

    return calc_current
