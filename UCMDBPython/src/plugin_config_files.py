#coding=utf-8
from itertools import imap, ifilter
from plugins import Plugin
import logger
import file_system
import file_topology
import fptools

from applications import Expression

class ConfigurationFilesPlugin(Plugin):
    
    PLUGIN_ID = "plugin_config_files"
    
    ELEMENT_CONFIG_FILE = "config-file"
    
    def __init__(self):
        Plugin.__init__(self)

    def isApplicable(self, context):
        descriptor = context.application.getApplicationComponent().getExplicitPluginById(ConfigurationFilesPlugin.PLUGIN_ID)
        if descriptor and context.client:
            return True        
        return False
    
    def _getLocationFromElement(self, element):
        if element:
            location = element.getText()
            location = location and location.strip()
            return location
    
    def _parseLocation(self, location, parseRuleContexts):
        if location:
            expression = Expression(location)
            expression.parse(parseRuleContexts)
            try:
                parsedLocation = expression.evaluate()
                return parsedLocation
            except:
                logger.warnException(" ... Failed to parse location of config file: %s" % location)
    
    def _retrieveConfigFile(self, path, fileSystem):
        try:
            fileObject = fileSystem.getFileContent(path)
            if fileObject and fileObject.content:
                return fileObject
        except:
            logger.warnException(" ... Failed to retrieve content of file by path: %s" % path)

    def _reportConfigFile(self, fileObject, reporter, context):
        if fileObject and fileObject.content:
            configOsh = reporter.report(fileObject, context.application.getOsh())
            return configOsh
                
    def process(self, context):
        descriptor = context.application.getApplicationComponent().getExplicitPluginById(ConfigurationFilesPlugin.PLUGIN_ID)
        if not descriptor:
            return
        
        element = descriptor.getRootElement()
        configElements = element.getChildren(ConfigurationFilesPlugin.ELEMENT_CONFIG_FILE)
        
        # parse DOM
        paths = ifilter(None, imap(self._getLocationFromElement, configElements))
        
        # evaluate expressions
        parseRuleContexts = context.application.getParseRuleContexts()
        parseFn = fptools.partiallyApply(self._parseLocation, fptools._, parseRuleContexts)
        parsedPaths = ifilter(None, imap(parseFn, paths))
        
        # retrieve content
        fileSystem = file_system.createFileSystem(context.client)
        retrieveFn = fptools.partiallyApply(self._retrieveConfigFile, fptools._, fileSystem)
        configFiles = ifilter(None, imap(retrieveFn, parsedPaths))
        
        # report
        builder = file_topology.Builder()
        reporter = file_topology.Reporter(builder)
        reportFn = fptools.partiallyApply(self._reportConfigFile, fptools._, reporter, context)
        oshs = ifilter(None, imap(reportFn, configFiles))
        
        for osh in oshs:
            context.resultsVector.add(osh)
