#coding=utf-8
import string

from java.util import Properties

from com.hp.ucmdb.discovery.library.clients.agents.sap import SAPCCMSUtil

def createCcmsUtils(client, loadType):
    return SAPCCMSUtil(client, loadType)


class SapUtils:
    ALL_TYPES_LOAD = 0
    SERVERS_LOAD = 1
    DATABASE_LOAD = 2
    SERVICES_LOAD = 3
    NO_LOAD = 4
    """
    Class for managing sap queries via SAP Client (JCO)
    """

    # constructor
    def __init__(self, client, loadOnInit=1, loadType=ALL_TYPES_LOAD):
        """
        SapUtils constructor

        @param client: Pre-connected sap client to be used for the SapUtils session
        @type client: (java) SapUtils class
        """
        self.__client = client
        if loadOnInit:
            self.__ccms_util = createCcmsUtils(client, loadType)

    def executeQuery(self, tableName, whereClause, desiredFields, inField = None, inFieldValues = None):
        r'''
        Where clause can be composed according to this guide
        http://help.sap.com/saphelp_bw30b/helpdata/en/fc/eb3983358411d1829f0000e829fbfe/content.htm
        '''
        if inField is None:
            return self.__client.executeQuery(tableName, whereClause, desiredFields)
        else:
            return self.__client.executeQuery(tableName, whereClause, inField, inFieldValues, desiredFields)

    def executeFunction(self, funcName, parameters, retParameter, desiredFields):
        return self.__client.executeFunction(funcName, parameters, retParameter, desiredFields)

    def getSites(self):
        return self.__ccms_util.getSites()

    def getServers(self, site):
        return self.__ccms_util.getServers(site)

    def getServices(self, site, server):
        return self.__ccms_util.getServices(site, server)

    def getDatabase(self, site):
        return self.__ccms_util.getDatabase(site)

    def getProfiles(self):
        return self.__client.getProfiles()

    def getJavaClient(self):
        return self.__client

    def getClients(self, siteOSH):
        clients = []
        # Query the clients table
        resultSet = self.__client.executeQuery("T000", None, "MANDT,MTEXT,ORT01,CCCATEGORY")#@@CMD_PERMISION sap protocol execution
        while resultSet.next():

            # Get the values from the table
            name = resultSet.getString("MANDT")
            description = resultSet.getString("MTEXT")
            city = resultSet.getString("ORT01")
            role = resultSet.getString("CCCATEGORY")

            prop = Properties()
            prop.setProperty('data_name', name)
            prop.setProperty('description', description)
            prop.setProperty('city', city)
            prop.setProperty('role', self.getClientRole(role))

            clients.append(prop)
        return clients

    def getClientRole(self, code):
        if code == 'P':
            return "Production"

        if code == 'T':
            return "Test"

        if code == 'C':
            return "Customizing"

        if code == 'D':
            return "Demo"

        if code == 'E':
            return "Training/Education"

        if code == 'S':
            return "SAP Reference"

        return ''

    def getComponentTypeText(self, componentType):
        if componentType is None or componentType == '' or componentType == ' ' or componentType == 'R':
            return 'Main Component'
        elif componentType == 'A':
            return 'Add-on Component'
        elif componentType == 'S':
            return 'Basis Component'
        elif componentType == 'P':
            return 'Plug-In'
        elif componentType == 'N':
            return 'Enterprise Add-On'
        elif componentType == 'I':
            return 'Industry Solution'
        elif componentType == 'C':
            return 'SDP,CDP'
        return componentType

    def formatElemString(self, data):
        strHeaderFooter = '\n'
        formattedString = ''
        it = data.keySet().iterator()
        while it.hasNext():
            name = it.next()
            value = data.get(name)
            formattedString = string.join([formattedString, name, '=', value, '\n'], ' ')
        formattedString = string.join([formattedString, strHeaderFooter])
        return formattedString

    def getComponents(self, site):

        componentsProps = []
        resultSet = self.__client.executeQuery("CVERS_REF",None,"COMPONENT,DESC_TEXT,LANGU")#@@CMD_PERMISION sap protocol execution

        # Get the components description
        mapNameToTextDic = {}
        while resultSet.next():
            lang = resultSet.getString("LANGU").lower()
            if (lang != 'e') and (lang != 'en'):
                continue
            component = resultSet.getString("COMPONENT")
            text = resultSet.getString("DESC_TEXT")
            mapNameToTextDic[component] = text

        # Get the components details
        resultSet = self.__client.executeQuery("CVERS", None, "COMPONENT,RELEASE,EXTRELEASE,COMP_TYPE");#@@CMD_PERMISION sap protocol execution
        while resultSet.next():
            component = resultSet.getString("COMPONENT")
            release = resultSet.getString("RELEASE")
            supportPackageLevel = resultSet.getString("EXTRELEASE")
            componentType = resultSet.getString("COMP_TYPE")

            text = ""
            if mapNameToTextDic.has_key(component):
                text = mapNameToTextDic[component]

            props = Properties()
            props.setProperty('Name', component)
            props.setProperty('Release', release)
            props.setProperty('Package Level', supportPackageLevel)
            props.setProperty('Type', componentType)
            props.setProperty('Description', text)

            componentsProps.append(props)

        return componentsProps

    def getSupportPackages(self, site):
        packages = []
        resultSet = self.__client.executeQuery("PAT03",None,"PATCH,SHORT_TEXT,PATCH_TYPE")#@@CMD_PERMISION sap protocol execution
        while resultSet.next():
            patch = resultSet.getString("PATCH");
            shortText = resultSet.getString("SHORT_TEXT");
            status = resultSet.getString("PATCH_TYPE");

            props = Properties()
            props.setProperty('Name', patch)
            props.setProperty('Description', shortText)
            props.setProperty('Type', status)

            packages.append(props)

        return packages

    def getIpAddress(self):
        return self.__client.getIpAddress()

    def getUserName(self):
        return self.__client.getUserName()

    def getCredentialId(self):
        return self.__client.getCredentialId()

    def getInstanceNumber(self):
        return self.__client.getInstanceNumber()

    def getConnectionClient(self):
        return self.__client.getConnectionClient()

    def getRouter(self):
        return self.__client.getRouter()


class SapSolman(SapUtils):
    def __init__(self, client):
        SapUtils.__init__(self, client, 0)
        self.__client = client

    def getBusinessProcesses(self):
        return self.__client.getBusinessProcesses()

    def getProcessSteps(self, scenario, process, processID):
        return self.__client.getProcessSteps(scenario, process, processID)

    def execute(self, table, desiredFields, inField=None, inValues=None):
        return self.executeQuery(table, None, desiredFields, inField, inValues)


def isEmptyValue(value):
    return (value is None) or (value == '') or (value == ' ')
