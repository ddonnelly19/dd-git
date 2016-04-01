#coding=utf-8
import re
import ConfigParser
from ConfigParser import ParsingError
import logger
        
singleValRe = re.compile('^\s*([\w-]+)\s*(#.*)?$')

class StringReader: 
    """
    Used to emulate reading line by line from list of strings
    @see ConfigParser.readfp()
    """

    def __init__(self, buffer):
        """
        @param string[] buffer buffer of strings
        """
        self.lineNumber = 0
        self.buffer = buffer

    def readline(self):
        """                        
        Iterator by lines
        @return String next line 
        """
        self.lineNumber = self.lineNumber + 1  
        if self.lineNumber <= len(self.buffer):             
            return self.buffer[self.lineNumber - 1]
        else:
            return None
        
def getInivars(iniContent): 
    """               
    Creates ConfigParser object from ini file content.
    Assign empty string to vars without values. 
    @param String[] iniContent list of strings 
    @return ConfigParser config
    """
    iniContentCopy = []
    config = ConfigParser.ConfigParser()
    for line in iniContent:
        m = singleValRe.match(line)
        if m:
            key, comment = m.groups()
            iniContentCopy.append(key + "=''")
        else:
            iniContentCopy.append(line)
    iniFile = StringReader(iniContentCopy)
    try:
        config.readfp(iniFile)
    except ParsingError, pe:
        logger.warnException(str(pe))
    return config

