#coding=utf-8
from appilog.common.system.types.vectors import ObjectStateHolderVector

def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()

    Framework.reportWarning("This job has been deprecated, IHS Plug-in discovery is incorporated into standard Apache discovery")
    
    return OSHVResult
