#!/usr/bin/env python
# -*- coding:utf-8 -*-

###############################################################################
##    Processing of calibration properties into usably numpy arrays
##
###############################################################################

## SOME ASSUMPTIONS
#
# - If data is provided for several multipoles (not just the main component):
#       - Assume same number of current measurement points for each multipole
#       - Also assume sign of current measurement i for multipole 1 is same as sign of measurement i on multipole 2 etc
#       - Actual current values may be different (but same number, same sign)

import numpy as np

_maxdim = 10 #Maximum number of multipole components

def process_calibration_data(ExcitationCurveCurrents, ExcitationCurveFields, allowedcomp):

    hasCalibData=False

    #Check there is data:
    #May have given empty list:
    if ExcitationCurveCurrents[0]=="[]" or ExcitationCurveFields[0]=="[]":
        return hasCalibData, "Calibration data is missing.", None, None
    #May have given nothing at all:
    if ExcitationCurveCurrents[0]=="" or ExcitationCurveFields[0]=="":
        return hasCalibData, "Calibration data is missing.", None, None

    #Check dimensions of current and field calibration data
    #(Should be n arrays of field values for n arrays of current values)
    if len(ExcitationCurveCurrents) != len(ExcitationCurveFields):
        return hasCalibData, "Calibration error: different number of multipoles in field and current data", None, None

    #Check dimensions against allowed comp, e.g if sext (allowed comp=2), must have 0, 1 and 2 elements filled, so dim 3
    #so require dim>allowed comp, but can have higher dimensions filled, too!
    if len(ExcitationCurveCurrents) <= allowedcomp:
        return hasCalibData, "Calibration error: data incompatible with magnet type.", None, None

    #Make numpy arrays for field and currents for each multipole component. 
    #At this point the calibration data are strings with comma separated values. Get the length by counting commas!
    #Check length is same for all multipoles
    array_length_ref = -1
    for i in range (0,len(ExcitationCurveCurrents)):
        array_length_I = ExcitationCurveCurrents[i].count(",")
        array_length_B = ExcitationCurveFields[i].count(",")
        if  array_length_I == 0 or array_length_B == 0: #cannot be one entry and no commas
            return hasCalibData, "Calibration data is missing for multipole %i" % i, None, None
        if  array_length_I != array_length_B:
            return hasCalibData, "Calibration error: different number of measurement points in field and current data for multipole %i" % i, None, None
        if i == 0:
            array_length_ref = array_length_I
        else:
            if array_length_I != array_length_ref:
                return hasCalibData, "Calibration error: multipole %i has different length data than the first" % i, None, None

    #Assume now the circuit/magnet is calibrated
    hasCalibData=True
    array_length = array_length_ref+1

    #Arrays to hold data as provided:
    fieldsmatrix_orig   = np.zeros(shape=(_maxdim,array_length), dtype=float)
    currentsmatrix_orig = np.zeros(shape=(_maxdim,array_length), dtype=float)
    fieldsmatrix_orig[:]   = np.NAN
    currentsmatrix_orig[:] = np.NAN

    #Fill the numpy arrays. Loop over number of multipoles provided.
    for i in range (0,len(ExcitationCurveCurrents)):

        #PJB Conversion of string to floats
        #Property is a vector of strings to start with like "[1,2,3]\n[1,2,3]" No way to store a matrix of floats?
        #Have to strip off the [ and ] !
        if len(ExcitationCurveCurrents[i])>0:

            fieldsmatrix_orig[i]   =  [float(x) for x in "".join(ExcitationCurveFields[i][1:-1]).split(",")]
            currentsmatrix_orig[i] =  [float(x) for x in "".join(ExcitationCurveCurrents[i][1:-1]).split(",")] 


    #Provided calibration points may be for positive or negative currents only, in which case the final
    #array needs to be "reflected" in the origin. 
    #Or the provided calibration points (eg for Pole faced strips) may be symmetric about origin
    #i.e, may be like I2, I1, 0 or -I1, 0, I1

    #Assume same sign of current measurements for each multipole, so check allowed component to see if is passes through 0
    #(lower multipoles may be all zeroes)
    if currentsmatrix_orig[allowedcomp][0] * currentsmatrix_orig[allowedcomp][-1] < 0.0:
        #print "already reflected ", fieldsmatrix_orig, currentsmatrix_orig
        #arrange in order of increasing current
        for i in range (0,len(ExcitationCurveCurrents)):
            if currentsmatrix_orig[i][0] > 0.0:
                fieldsmatrix_orig[i]   = fieldsmatrix_orig[i][::-1]
                currentsmatrix_orig[i] = currentsmatrix_orig[i][::-1]

        #print "already reflected ", fieldsmatrix_orig, currentsmatrix_orig
        return  hasCalibData, "Calibration available", fieldsmatrix_orig, currentsmatrix_orig

    #Otherwise need to reflect and combine the data 
    else:
        #Make "reflected" arrays for negative currents and opposite sign on the fields, then merge the two later below
        fieldsmatrix_ref    = np.zeros(shape=(_maxdim,array_length-1), dtype=float)
        currentsmatrix_ref  = np.zeros(shape=(_maxdim,array_length-1), dtype=float)
        fieldsmatrix_ref[:]   = np.NAN
        currentsmatrix_ref[:] = np.NAN
        #
        #Returned array will be combination of original and reflected. 
        fieldsmatrix_comb   = np.zeros(shape=(_maxdim,(2*array_length)-1), dtype=float)
        currentsmatrix_comb = np.zeros(shape=(_maxdim,(2*array_length)-1), dtype=float)
        fieldsmatrix_comb[:]   = np.NAN
        currentsmatrix_comb[:] = np.NAN

        for i in range (0,len(ExcitationCurveCurrents)):
            
            #need to sort the currents and fields by absolute values for interpolation to work later
            currentsmatrix_orig[i] = sorted(currentsmatrix_orig[i],key=abs)
            fieldsmatrix_orig[i]   = sorted(fieldsmatrix_orig[i],key=abs)
            
            currentsmatrix_ref[i] = (-currentsmatrix_orig[i][1:])[::-1]
            fieldsmatrix_ref[i]   = (-fieldsmatrix_orig[i][1:])[::-1]
            
            currentsmatrix_comb[i] = np.concatenate((currentsmatrix_ref[i],currentsmatrix_orig[i]),axis=0)
            fieldsmatrix_comb[i]   = np.concatenate((fieldsmatrix_ref[i],fieldsmatrix_orig[i]),axis=0)

        #print "reflected ", fieldsmatrix_comb, currentsmatrix_comb
        return  hasCalibData, "Calibration available", fieldsmatrix_comb, currentsmatrix_comb
