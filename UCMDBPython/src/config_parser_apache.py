# __author__ = 'gengt'
import logger
import apache_config_parser
from apache_plugin import apache_plugins


def parseConfigFile(shell, configfilePath, configFileName, fileContent, variableResolver):
    """parse apache config file httpd.conf"""
    configItems, parserdFileContent = parserApacheConf(shell, fileContent, configfilePath, configFileName)
    for plugin in apache_plugins.values():
        if plugin.suitable(configItems, parserdFileContent):
            logger.debug('Match apache configuration plugin: %s' % plugin.__class__.__name__)
            for k, vs in plugin.findVariables(shell, configItems, parserdFileContent, variableResolver).items():
                for v in vs:
                    variableResolver.add(k, v)
    return variableResolver


def parserApacheConf(shell, fileContent, filePath, fileName):
    """Call ApacheConfParser function, return all parsed config items and reconstructed config content"""
    parser = apache_config_parser.ApacheConfParser(shell)
    parser.parseApacheConf(fileContent, filePath, fileName)
    return parser.items, repr(parser.rootBlock)
