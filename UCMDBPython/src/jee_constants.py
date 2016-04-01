import file_system


CELLCONFIGFILES = ['resources.xml', 'cell.xml', 'namebindings.xml', "security.xml"]
SERVERCONFIGFILES = ['resources.xml']
EARCONFIGFILES = ['ibm-application-bnd.xmi', 'ibm-application-ext.xmi']
WARCONFIGFILES = [
    'web.xml',
    'ibm-web-bnd.xmi',
    'ibm-web-bnd.xml',
    'ibm-web-ext.xmi',
    'ibm-web-ext.xml',
    'ibm-portlet-ext.xmi',
    'ibm-webservices-bnd.xmi',
    'ibm-webservices-ext.xmi',
    'ibm-webservicesclient-bnd.xmi',
    'ibm-webservicesclient-ext.xmi']
JARCONFIGFILES = [
    'ejb-jar.xml',
    'ibm-webservices-bnd.xmi',
    'ibm-webservices-ext.xmi',
    'ibm-webservicesclient-bnd.xmi',
    'ibm-webservicesclient-ext.xmi',
    'ibm-ejb-jar-bnd.xmi',
    'ibm-ejb-jar-ext.xmi',
    'ibm-ejb-jar-bnd.xml',
    'ibm-ejb-jar-ext.xml']

class ConfigFileFilter(file_system.FileFilter):
    def __init__(self, path, configFiles):
        self.__path = path
        self.__configFiles = configFiles

    def accept(self, file_):
        for configFile in self.__configFiles:
            if configFile[0] == '.' and file_.name.endswith(configFile):
                return True
            elif file_.name == configFile and file_.path.endswith(self.__path, 0, -len(file_.name) - 1):
                return True
        return False


class ModuleTypeDescriptor:
    def __init__(self, name, extName, isWebModule, configFiles):
        """
        @param name: the module type name
        @param extName: the extension name of the module file
        @param isWebModule: the flag indicates if the module is a web module, which determines the path to search configuration files
        @param configFiles: configuration files to collect
        @type name: str
        @type extName: str
        @type isWebModule: bool
        @type configFiles: list(str)
        """
        self.__name = name
        self.__extName = extName
        if isWebModule:
            self.__configFilePath = 'WEB-INF'
        else:
            self.__configFilePath = 'META-INF'
        self.__configFileFilter = ConfigFileFilter(self.__configFilePath, list(configFiles))

    def getName(self):
        return self.__name

    def getExt(self):
        return self.__extName

    def getConfigFilePath(self):
        return self.__configFilePath

    def getConfigFileFilter(self):
        return self.__configFileFilter

    def getSimpleName(self, moduleName):
        if moduleName and moduleName.lower().endswith(self.getExt()):
            return moduleName[:-len(self.getExt())]
        return moduleName

    def __repr__(self):
        return self.getName()


class ModuleType:
    EAR = ModuleTypeDescriptor('EAR', '.ear', False, [
        '.xml',
        # IBM WAS extension
        'ibm-application-bnd.xmi',
        'ibm-application-ext.xmi',
    ])

    WAR = ModuleTypeDescriptor('WAR', '.war', True, [
        '.xml',
        # IBM WAS extension
        'ibm-web-bnd.xmi',
        'ibm-web-bnd.xml',
        'ibm-web-ext.xmi',
        'ibm-web-ext.xml',
        'ibm-portlet-ext.xmi',
        'ibm-webservices-bnd.xmi',
        'ibm-webservices-ext.xmi',
        'ibm-webservicesclient-bnd.xmi',
        'ibm-webservicesclient-ext.xmi',
    ])

    EJB = ModuleTypeDescriptor('EJB', '.jar', False, [
        '.xml',
        # IBM WAS extension
        'ibm-webservices-bnd.xmi',
        'ibm-webservices-ext.xmi',
        'ibm-webservicesclient-bnd.xmi',
        'ibm-webservicesclient-ext.xmi',
        'ibm-ejb-jar-bnd.xmi',
        'ibm-ejb-jar-ext.xmi',
    ])


class BeanType:
    SESSION = 'session'
    ENTITY = 'entity'
    MDB = 'message-driven'


BEAN_TYPES = [BeanType.SESSION, BeanType.ENTITY, BeanType.MDB]
