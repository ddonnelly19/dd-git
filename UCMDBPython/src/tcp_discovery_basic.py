#coding=utf-8
import time
import logger
import errormessages
import errorcodes

class UnknownOSTypeException(Exception):
    def __str__(self):
        return "Unknown OS type"

class TcpDiscoverer:
    def __init__(self, framework):
        self.framework = framework
        self.client = self._createClient()

    def _createClient(self):
        return self.framework.createClient()

    def _getClient(self):
        return self.client
        
    def discover(self):
        protocol = self.framework.getDestinationAttribute('Protocol')    
        try:
            captureProcessInformation = self.framework.getParameter('CaptureProcessInformation')
            numberOfTCPSnapshots = int(self.framework.getParameter('NumberOfTCPSnapshots'))
            delayBetweenTCPSnapshots = float(self.framework.getParameter('DelayBetweenTCPSnapshots'))
        except:
            logger.error(logger.prepareFullStackTrace(''))
            raise ValueError("Job parameters are invalid")
        else:
            if numberOfTCPSnapshots < 1 or delayBetweenTCPSnapshots <= 0:
                raise ValueError("Job parameters are invalid")

            try:
                if captureProcessInformation.lower() == 'true':
                    self._discoverProcesses()

            except UnknownOSTypeException, ex:
                msg = str(ex)
                errormessages.resolveAndReport(msg, self.client.getClientType(), self.framework)
            except:
                exInfo = logger.prepareJythonStackTrace('Failed to discover processes')
                errormessages.resolveAndReport(exInfo, self.client.getClientType(), self.framework)

            try:
                for i in range(numberOfTCPSnapshots):
                    self._discoverTcp()
                    time.sleep(delayBetweenTCPSnapshots)
            except:
                logger.debugException('Failed to discover TCP information')
                import sys
                msg = str(sys.exc_info()[1])
                errormessages.resolveAndReport(msg, self.client.getClientType(), self.framework)

    def _discoverProcesses(self):
        raise NotImplementedError()
        
    def _discoverTcp(self):
        raise NotImplementedError()