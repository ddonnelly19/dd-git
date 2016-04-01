#coding=utf-8
import fptools

import cim 
import cim_discover

from check_credential import connect, Result


def cimConnectionCheck(credentialId, ipAddress, framework):
    
    credentialsCategory = framework.getProtocolProperty(credentialId, cim.ProtocolProperty.CATEGORY)
    categories = cim_discover.getCimCategories(framework)
    
    if credentialsCategory and credentialsCategory != cim.CimCategory.NO_CATEGORY:
        categories = [category for category in categories if category.getName() == credentialsCategory]
    
    namespaces = [ns for category in categories for ns in category.getNamespaces()]

    testFunction = fptools.partiallyApply(cim_discover.safeTestConnectionWithNamespace, framework, ipAddress, credentialId, fptools._)
    try:
        testedNamespaces = map(testFunction, namespaces)
        testedNamespaces = filter(None, testedNamespaces)
        if len(testedNamespaces) == 0:
            raise ValueError("Failed to establish connection to any namespace")
        return Result(True)
    except ValueError, ex:
        return Result(False, str(ex)) 
    
def DiscoveryMain(framework):
    return connect(framework, cimConnectionCheck)
