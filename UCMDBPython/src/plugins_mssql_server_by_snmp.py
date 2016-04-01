#coding=utf-8
import sys
import logger

from plugins import Plugin

class MSSQLServerInstancesBySNMPPlugin(Plugin):
    """
        Plugin discovers mssql software element.
    """
    
    def __init__(self):
        Plugin.__init__(self)
        self.__client = None
        self.__path = None
         
    def isApplicable(self, context):
        self.__client = context.client
        try:
            return context.application.getProcess('sqlservr.exe') is not None
        except:
            logger.errorException(sys.exc_info()[1])

    def process(self, context):
        context.application.getOsh().setObjectClass('application')
