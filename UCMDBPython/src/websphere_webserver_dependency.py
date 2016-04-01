#coding=utf-8
import logger
import modeling

from appilog.common.system.types.vectors import ObjectStateHolderVector

class JobException(Exception): pass

class WebModule:
    def __init__(self, contextRoot, rootId):
        self.contextRoot = contextRoot
        self.rootId = rootId
        self.containerId = None
        self.osh = None
        
    def __repr__(self):
        return "WebModule(context = %s)" % self.contextRoot


class HttpContext:
    def __init__(self, contextRoot, rootId):
        self.contextRoot = contextRoot
        self.rootId = rootId
        self.containerId = None
        self.serverName = None
        self.osh = None

    def __repr__(self):
        return "HttpContext(context = %s)" % self.contextRoot


def restoreWebModuleOshById(moduleId):
    return modeling.createOshByCmdbIdString('webmodule', moduleId)


def restoreHttpContextOshById(httpContextId):
    return modeling.createOshByCmdbIdString('httpcontext', httpContextId)


def restoreJ2eeApplicationOshById(j2eeApplicationId):
    return modeling.createOshByCmdbIdString('j2eeapplication', j2eeApplicationId)


def restoreWebServerOshById(webServerId):
    return modeling.createOshByCmdbIdString('web_server', webServerId)

            
def filterHttpContextsByServerNames(httpContextById, webSphereNamesSet):
    filteredHttpContextById = {}
    for httpContextId, httpContext in httpContextById.items():
        if webSphereNamesSet.has_key(httpContext.serverName):
            filteredHttpContextById[httpContextId] = httpContext
    return filteredHttpContextById


def filterHttpContextsByWebModuleContext(httpContextById, contextRoot):
    filteredHttpContextById = {}
    for httpContextId, httpContext in httpContextById.items():
        if httpContext.contextRoot == contextRoot:
            filteredHttpContextById[httpContextId] = httpContext
    return filteredHttpContextById


def reportTopology(httpContextById, webModule, resultVector):
        
    webServerOshById = {}    
        
    for httpContext in httpContextById.values():
            
        webServerOsh = webServerOshById.get(httpContext.containerId)
        if webServerOsh is None:
            webServerOsh = restoreWebServerOshById(httpContext.containerId)
            webServerOshById[httpContext.containerId] = webServerOsh
            resultVector.add(webServerOsh)
        
        useLink = modeling.createLinkOSH('use', webServerOsh, webModule.osh)
        resultVector.add(useLink)

def DiscoveryMain(Framework):
    resultVector = ObjectStateHolderVector()
    
    webModuleId = Framework.getDestinationAttribute('web_module_id')
    webModuleContextRoot = Framework.getDestinationAttribute('web_module_context_root')
    
    httpContextIds = Framework.getTriggerCIDataAsList('http_context_id')
    httpContextContextRoots = Framework.getTriggerCIDataAsList('http_context_context_root')
    httpContextContainerIds = Framework.getTriggerCIDataAsList('http_context_root_container')
    httpContextServers = Framework.getTriggerCIDataAsList('http_context_server')

    webSphereNames = Framework.getTriggerCIDataAsList('websphere_full_name')
    
    try:             
        
        if not webModuleId or not webModuleContextRoot:
            raise JobException, "Web module ID or context root is empty"
        
        if not httpContextIds or not httpContextContextRoots or not httpContextContainerIds or not httpContextServers:
            raise JobException, "HTTP Context details are empty"
        
        webModule = WebModule(webModuleContextRoot, webModuleId)
        webModule.osh = restoreWebModuleOshById(webModuleId)
            
        httpContextIdsCount = len(httpContextIds)
        httpContextContextRootCount = len(httpContextContextRoots)
        httpContextContainerIdsCount = len(httpContextContainerIds)
        httpContextServersCount = len(httpContextServers)
        if httpContextIdsCount != httpContextContextRootCount or httpContextIdsCount != httpContextContainerIdsCount or httpContextIdsCount != httpContextServersCount: 
            raise JobException, "Mismatch in HTTP Context attribute collections"
            
        httpContextById = {}
        for i in range(httpContextIdsCount):
            httpContext = HttpContext(httpContextContextRoots[i], httpContextIds[i])
            httpContext.containerId = httpContextContainerIds[i]
            httpContext.serverName = httpContextServers[i]
            httpContext.osh = restoreHttpContextOshById(httpContext.rootId)
            httpContextById[httpContext.rootId] = httpContext

        webSphereNamesSet = {}
        if webSphereNames:
            for name in webSphereNames:
                webSphereNamesSet[name] = None
        
        filteredHttpContextById = filterHttpContextsByServerNames(httpContextById, webSphereNamesSet)
        
        filteredHttpContextById = filterHttpContextsByWebModuleContext(filteredHttpContextById, webModule.contextRoot)
        
        reportTopology(filteredHttpContextById, webModule, resultVector)
        
    
    except JobException, ex:
        logger.warn(ex)
    except:
        logger.debugException('')
        Framework.reportError("Error during discovery. See logs for details.")

    return resultVector
