import logger
from appilog.common.system.types.vectors import ObjectStateHolderVector


class FrameworkDelegator(object):
    def __init__(self):
        self.resultMap = {}
        self.portMap = {}
        self.currentApplication = None
        self.currentVector = None

    def sendObjects(self, resultVector):
        if self.currentApplication and self.currentVector:
            #logger.debug("result vector for application:", self.currentApplication)
            #logger.debug(resultVector.toXmlString())
            self.currentVector.addAll(resultVector)
            for osh in resultVector:
                if osh.getObjectClass() == 'ip_service_endpoint':
                    port = osh.getAttributeValue('network_port_number')
                    logger.debug("found port:", port)
                    self.portMap[self.currentApplication].append(str(port))
                    logger.debug("port for application: %s : %s" % (self.currentApplication, self.portMap[self.currentApplication]))
        else:
            logger.debug("you should set current application before send objects")

    def setCurrentApplication(self, applicationName):
        self.currentApplication = applicationName
        if self.resultMap.has_key(applicationName):
            self.currentVector = self.resultMap[applicationName]
        else:
            resutVector = ObjectStateHolderVector()
            self.resultMap[applicationName] = resutVector
            self.portMap[applicationName] = []
            self.currentVector = resutVector

    def getResultVectorsByPort(self, port):
        resultVectors = []
        for appliationName in self.portMap.keys():
            if str(port) in self.portMap[appliationName]:
                resultVectors.append(self.getResultVectorByApplicationName(appliationName))

        return resultVectors

    def getApplicationNamesByPort(self, port):
        appliationNames = []
        for appliationName in self.portMap.keys():
            #logger.debug("appliationName", appliationName)
            #logger.debug("self.portMap[appliationName]", self.portMap[appliationName])
            #logger.debug("port", port)
            if str(port) in self.portMap[appliationName]:
                appliationNames.append(appliationName)

        return appliationNames

    def getResultVectorByApplicationName(self, applicationName):
        result = self.resultMap.get(applicationName)
        if not result:
            logger.debug("result vector not found for appliation: ", applicationName)
        return result

    def addNetstatPortResult(self, applicationName, port):
        if not self.portMap.has_key(applicationName):
            logger.debug("application not discovered:", applicationName)
            return

        self.portMap[applicationName].append(str(port))



