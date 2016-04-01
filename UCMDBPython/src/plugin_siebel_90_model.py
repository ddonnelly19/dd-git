#coding=utf-8
import logger
from plugins import Plugin
import modeling

class BaseSiebel90ModelPlugin(Plugin):

    def __init__(self):
        Plugin.__init__(self)
        self.__framework = None

    def isApplicable(self, context):
        self.__framework = context.framework
        versionAsDouble = logger.Version().getVersion(self.__framework)
        if versionAsDouble >= 9:
            return 1
        else:
            return 0

class SiebelAppServer90ModelPlugin(BaseSiebel90ModelPlugin):

    def __init__(self):
        BaseSiebel90ModelPlugin.__init__(self)

    def process(self, context):
        application = context.application
        applicationOsh = application.getOsh()
        #we should not set the name for Server
        applicationOsh.removeAttribute('data_name')
        modeling.setApplicationDiscoveredProductName(applicationOsh, 'Siebel Server')

class SiebelGateway90ModelPlugin(BaseSiebel90ModelPlugin):

    def __init__(self):
        BaseSiebel90ModelPlugin.__init__(self)

    def process(self, context):
        application = context.application
        applicationOsh = application.getOsh()
        #we should not set the name for Server
        applicationOsh.removeAttribute('data_name')
        modeling.setApplicationDiscoveredProductName(applicationOsh, 'Siebel Gateway Name Server')