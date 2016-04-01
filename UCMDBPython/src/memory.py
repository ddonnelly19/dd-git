#coding=utf-8
'''
Modeling module for memory

@author: vvitvitskiy
'''

from appilog.common.system.types import ObjectStateHolder
import modeling

def _kbToMb(sizeInKb):
    'int -> int'
    return sizeInKb / 1024

def _createOsh(hostOsh, sizeInKb):
    'ObjectStateHolder, int -> ObjectStateHolder'
    osh = ObjectStateHolder('memory')
    osh.setContainer(hostOsh)
    osh.setIntegerAttribute("memory_size", sizeInKb)
    return osh

def _report80(vector, hostOsh, sizeInKb):
    'ObjectStateHolderVector, ObjectStateHolder, int'
    vector.add(_createOsh(hostOsh, sizeInKb))

def _report90(vector, hostOsh, sizeInKb):
    'ObjectStateHolderVector, ObjectStateHolder, int'
    modeling.setHostMemorySizeAttribute(hostOsh, _kbToMb(sizeInKb))

def report(vector, hostOsh, sizeInKb):
    'ObjectStateHolderVector, ObjectStateHolder, int'
    if modeling.CmdbClassModel().version() < 9:
        _report80(vector, hostOsh, sizeInKb)
    else:
        _report90(vector, hostOsh, sizeInKb)