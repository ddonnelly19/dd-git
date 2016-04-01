#coding=utf-8
import sys
import logger

from plugins import Plugin

class SAPASInstanceName(Plugin):
    """
        Until version UCMDB 9.0 SAP AS instance name was reported in data_name while in other Applications it was reported in special attribute
        To allisgn SAP AS with other Applications (and support transformations in bdm_changes.xml) we have to set 'data_name' from 'name' attribute.
    """

    def __init__(self):
        Plugin.__init__(self)
        self.__client = None
        self.__path = None

    def isApplicable(self, context):
        self.__client = context.client
        try:
            return context.application.getOsh().getAttribute('name') is not None
        except:
            logger.errorException(sys.exc_info()[1])

    def process(self, context):
        applicationOsh = context.application.getOsh()
        nameAttribute = applicationOsh.getAttribute('name')
        if nameAttribute is not None:
            applicationOsh.setStringAttribute('data_name', nameAttribute.getStringValue())
        return
