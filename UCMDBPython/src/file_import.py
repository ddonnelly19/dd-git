#coding=utf-8
from java.lang import String
from com.hp.ucmdb.discovery.library.common import CollectorsParameters

from import_utils import DataSource

import shellutils

class FileDataSource(DataSource):
    """
    This is base class for all DataSources which are based on file in the file system.
    E.g. CsvFileDataSource or PropertyFileDataSource
    """
    def __init__(self, fileName, Framework, fileEncoding=None):
        DataSource.__init__(self)
        self.fileName = fileName
        self.Framework = Framework
        self.encoding = fileEncoding and fileEncoding or CollectorsParameters.getDefaultOEMEncoding()
            
    """
    Shell client creation and file content retrieving is done here.
    Client closing is also performed here because there is no need to keep
    open connection after file content is transfered to the Probe machine
    """
    def open(self):
        client = None
        try:
            client = self.Framework.createClient()
            shell = shellutils.ShellUtils(client)
            fileContent = self.getFileContent(shell, self.fileName)
            bytes = self.getBytes(String(fileContent))
            self.data = self.parseFileContent(bytes)
        finally:
            if client:
                client.close()
            
    """
    Getting file content via remote shell
    """
    def getFileContent(self, shell, fileName):
        if shell.isWinOs() and self.encoding.lower() == 'utf-8':
            shell.setCodePage(65001)
            shell.useCharset("UTF-8")
        return shell.safecat(fileName)    
    
    """
    Most of existing file based DataSources needs file bytes to operate with
    """
    def getBytes(self, fileContent):
        return fileContent.getBytes(self.encoding)        
    
    """
    Nothing to close here, since connection is closed in "open" method
    """
    def close(self):
        pass
    
    """
    Abstract method which should be implemented by derived classes
    """
    def parseFileContent(self, bytes):
        "Each file-based DataSource should parse file content. File content if of java.lang.String type"       
        raise NotImplementedError, "parseContent"
