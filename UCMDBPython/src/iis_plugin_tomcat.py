import re
import logger


def parseConfigFile(shell, filePath, fileName, fileContent, variableResolver):
    for context in variableResolver.get('scp.context'):
        lines = fileContent.split('\n')
        for line in lines:
            pattern, workerName = line.strip().split('=')
            pattern = pattern.replace('*', '.*')
            if re.match(pattern, context, re.I):
                logger.debug('Narrow IIS plugins for Tomcat discovery to worker name \'%s\'.' % workerName)
                variableResolver.add('worker_name', workerName)
