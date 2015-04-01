#!/usr/bin/env python
# -*- coding:utf-8 -*-

###############################################################################
##    Processing of calibration properties into usably numpy arrays
##
###############################################################################

import numpy as np

_maxdim = 10 #Maximum number of multipole components

def process_calibration_data(ExcitationCurveCurrents, ExcitationCurveFields, allowedcomp):

    hasCalibData=False

    #Check dimensions of current and field calibration data
    #(Should be n arrays of field values for n arrays of current values)
    if  len(ExcitationCurveCurrents) != len(ExcitationCurveFields):
        return hasCalibData, "Calibration data have mis-matched dimensions", None, None

    if ExcitationCurveCurrents==[] or ExcitationCurveFields==[]:
        return hasCalibData, "Calibration data is missing.", None, None

    #Make numpy arrays for field and currents for each multipole component. 
    #At this point the calibration data are strings with comma separated values. Get the length by counting commas!
    array_length_1 = ExcitationCurveCurrents[0].count(",")
    array_length_2 = ExcitationCurveFields[0].count(",")
    if  array_length_1 == 0 or array_length_2 == 0:
        return hasCalibData, "Calibration data is missing.", None, None
    if  array_length_1 != array_length_2:
        return hasCalibData, "Calibration data have mis-matched dimensions", None, None
    array_length = array_length_1 + 1

    #number of multipoles must also be the same for currents and fields
    if len(ExcitationCurveCurrents) != len(ExcitationCurveFields):
        return hasCalibData, "Calibration data have mis-matched dimensions", None, None

    #check dimensions against allowed comp, e.g if sext (allowed comp=2), must have 0, 1 and 2 elements filled, so dim 3
    #allowed comp = 2 means need 3 dim, so require dim>allowed comp
    #can have higher dimensions filled, too!
    if len(ExcitationCurveCurrents) <= allowedcomp:
        return hasCalibData, "Calibration data incompatible with magnet type.", None, None

    #Assume now the circuit/magnet is calibrated
    hasCalibData=True

    #Calibration points are for positive currents only, but full calibration curve should go negative. 
    #Make "reflected" arrays for negative currents and opposite sign on the fields, then merge the two later below
    pos_fieldsmatrix   = np.zeros(shape=(_maxdim,array_length), dtype=float)
    pos_currentsmatrix = np.zeros(shape=(_maxdim,array_length), dtype=float)
    neg_fieldsmatrix   = np.zeros(shape=(_maxdim,array_length-1), dtype=float)
    neg_currentsmatrix = np.zeros(shape=(_maxdim,array_length-1), dtype=float)
    
    fieldsmatrix   = np.zeros(shape=(_maxdim,(2*array_length)-1), dtype=float)
    currentsmatrix = np.zeros(shape=(_maxdim,(2*array_length)-1), dtype=float)
    fieldsmatrix[:]   = np.NAN
    currentsmatrix[:] = np.NAN
    
    #Fill the numpy arrays, but first horrible conversion of list of chars to floats
    for i in range (0,len(ExcitationCurveCurrents)):
        #PJB hack since I use a string to start with like "[1,2,3]" No way to store a matrix of floats?
        if len(ExcitationCurveCurrents[i])>0:
            #need to sort the currents and fields by absolute values for interpolation to work later
            pos_fieldsmatrix[i]   =  sorted([float(x) for x in "".join(ExcitationCurveFields[i][1:-1]).split(",")],key=abs)
            pos_currentsmatrix[i] =  sorted([float(x) for x in "".join(ExcitationCurveCurrents[i][1:-1]).split(",")],key=abs)
                    
        #Force field and current to be zero in first entry
        #pos_currentsmatrix[i][0] = 0.0
        #pos_fieldsmatrix[i][0] = 0.0

        #Also here merge the positive and negative ranges into the final array
        neg_fieldsmatrix[i]   = (-pos_fieldsmatrix[i][1:])[::-1]
        neg_currentsmatrix[i] = (-pos_currentsmatrix[i][1:])[::-1]
        #
        currentsmatrix[i] = np.concatenate((neg_currentsmatrix[i],pos_currentsmatrix[i]),axis=0)
        fieldsmatrix[i]   = np.concatenate((neg_fieldsmatrix[i],pos_fieldsmatrix[i]),axis=0)


    return  hasCalibData, "Calibration available", fieldsmatrix, currentsmatrix
