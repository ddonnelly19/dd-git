#coding=utf-8
from com.hp.ucmdb.discovery.library.common import CollectorsParameters

def getProbeResourceLocator(ucmdbVersion):
    '''double -> ProbeFileSystemLocator'''
    return ucmdbVersion >= 9 and Probe9ResourceLocator() or Probe8ResourceLocator()

class ProbeResourceLocator:
    '''Base class for probe file system locator'''
    def getContentLibPath(self):
        'Returns path with trailing slash'
        raise NotImplemented

    def contentLibPathOf(self, resource):
        'Returns full path of resource, relative to content lib folder'
        return self.getContentLibPath() + '/' + str(resource)

class Probe9ResourceLocator(ProbeResourceLocator):
    '''FS locator for Probe v.9'''

    def getContentLibPath(self):
        return CollectorsParameters.HOME_DIR + 'content/lib/'

class Probe8ResourceLocator(ProbeResourceLocator):
    '''FS locator for Probe v.8.0x'''

    def getContentLibPath(self):
        return CollectorsParameters.INSTALL_EXT_DIR
    

if __name__ == '__main__':
    assert isinstance(getProbeResourceLocator(9.0), Probe9ResourceLocator)
    assert isinstance(getProbeResourceLocator(.0), Probe8ResourceLocator)
    assert isinstance(getProbeResourceLocator(8.04), Probe8ResourceLocator)