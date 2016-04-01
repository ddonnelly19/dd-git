#coding=utf-8
"""
Predefined unified error messages, that are expected to be used throughout all scripts.
Also includes helper error resolver that can match incoming errors and return unified
messages.
"""

import re
import logger
import errorcodes
import errorobject

from java.util import LinkedHashMap

from com.hp.ucmdb.discovery.library.clients import ClientsConsts

_PROTOCOL_PARAM = 'protocol'
_DETAILS_PARAM = 'details'

STR_ARG = lambda x: "%(" + x + ")s"

ERROR_VIRSH_COMMAND = STR_ARG(_PROTOCOL_PARAM) + ": No valid hypervisor found. Neither Xen not KVM can be reported"
WARN_NO_AGENT = STR_ARG(_PROTOCOL_PARAM) + ": No agent is on remote machine or agent is not available."
WARN_NO_XEN_FOUND = STR_ARG(_PROTOCOL_PARAM) + ': No libvirt found. Neither Xen not KVM can be reported.'
WARN_IP_ROUTE_INFORMATION = STR_ARG(_PROTOCOL_PARAM) + ": Failed to obtain ip routing information."
WARN_DNS_ZONE_TRANSFER = STR_ARG(_PROTOCOL_PARAM) + ": Failed to transfer zone records for one or more zones"
WARN_QUERY_FAILURE = STR_ARG(_PROTOCOL_PARAM) + ": Query failure"
ERROR_NO_RANGES_DEFINED = STR_ARG(_PROTOCOL_PARAM) + ": Current Probe range list is empty"
ERROR_CONNECTION_REFUSED = STR_ARG(_PROTOCOL_PARAM) + ": Connection refused."
ERROR_CONNECTION_REFUSED_DETAILS = STR_ARG(_PROTOCOL_PARAM) + ": Connection refused. Details: " + STR_ARG(_DETAILS_PARAM)
ERROR_TIMEOUT = STR_ARG(_PROTOCOL_PARAM) + ": Timeout trying to connect to remote agent, try increasing credential timeout value"
ERROR_COMMAND_TIMED_OUT = STR_ARG(_PROTOCOL_PARAM) + ": Command timed out"
ERROR_CONNECTION_TIMED_OUT = STR_ARG(_PROTOCOL_PARAM) + ": Connection timed out"
ERROR_CONNECTION_PING_TIMED_OUT = STR_ARG(_PROTOCOL_PARAM) + ": Connection timeout occurs when using IP ping."
ERROR_CONNECTION_TELNET_TIMED_OUT = STR_ARG(_PROTOCOL_PARAM) + ": The agent port cannot access the Telnet."
ERROR_NO_PERMISSIONS = STR_ARG(_PROTOCOL_PARAM) + ": Permission denied"
ERROR_INVALID_USERNAME_PASSWORD = STR_ARG(_PROTOCOL_PARAM) + ": Invalid user name or password"
ERROR_GET_SUDO_PASSWORD_FAILED="Failed to get the sudo password"
ERROR_OPERATION_FAILED = STR_ARG(_PROTOCOL_PARAM) + ": Operation failed."
ERROR_CONNECTION_FAILED = STR_ARG(_PROTOCOL_PARAM) + ": Connection failed"
ERROR_CONNECTION_FAILED_NO_PROTOCOL = "Connection failed"
ERROR_FORCE_CLOSED_CONNECTION = STR_ARG(_PROTOCOL_PARAM) + ": An existing connection was forcibly closed by the remote host"
ERROR_CONNECTION_FAILED_NO_PROTOCOL_WITH_DETAILS = "Connection failed. Details: " + STR_ARG(_DETAILS_PARAM)
ERROR_CLIENT_DISCONECT = STR_ARG(_PROTOCOL_PARAM) + ": Client Disconnect"
ERROR_MAXIMUM_CONNECTIONS_REACHED = STR_ARG(_PROTOCOL_PARAM) + ": Maximum connections reached."
ERROR_LICENCE_LIMITS_EXEDEED = STR_ARG(_PROTOCOL_PARAM) + ": Licensing limits exceeded."
ERROR_GENERIC = STR_ARG(_PROTOCOL_PARAM) + ": Internal error"
ERROR_GENERIC_WITH_DETAILS = STR_ARG(_PROTOCOL_PARAM) + ": Internal error. Details: " + STR_ARG(_DETAILS_PARAM)
ERROR_NO_CREDENTIALS = STR_ARG(_PROTOCOL_PARAM) + ": No credentials defined for the triggered ip"
ERROR_OUT_OF_MEMORY = STR_ARG(_PROTOCOL_PARAM) + ": Out of memory error occurred - operation cannot be completed"
ERROR_NOT_ENOUGH_SPACE = STR_ARG(_PROTOCOL_PARAM) + ": There is not enough space on the disk"
ERROR_SERVICE_IS_DISABLED = STR_ARG(_PROTOCOL_PARAM) + ": The service cannot be started either because it is disabled or because it has no enabled devices associated with it"
ERROR_ORACLE_HOME_NOT_FOUND = STR_ARG(_PROTOCOL_PARAM) + ": ORACLE_HOME not found. Please specify it in the job parameter."
ERROR_ORACLE_TNSNAMES_NOT_FOUND = STR_ARG(_PROTOCOL_PARAM) + ": Couldn't find tnsnames.ora configuration file. Please check OracleHomes parameter."
ERROR_REG_MAM_NOT_FOUND = STR_ARG(_PROTOCOL_PARAM) + ": File reg_mam.exe not found in 'probeManager\\discoveryResources'. In order for this discovery pattern to work, please rename an original WindowXP reg.exe  file to reg_mam.exe and copy it to 'probeManager\\discoveryResources'"
ERROR_NETWORK_PATH_IS_NOT_ACCESSIBLE = STR_ARG(_PROTOCOL_PARAM) + ": Network path is not accessible."
ERROR_NETWORK_PATH_IS_NO_LONGER_AVAILABLE = STR_ARG(_PROTOCOL_PARAM) + ": The specified network name is no longer available."
ERROR_HTTP_PAGE_NOT_FOUND = STR_ARG(_PROTOCOL_PARAM) + ": Page not found"
ERROR_HTTP_UNAUTHORIZED = STR_ARG(_PROTOCOL_PARAM) + ": Unauthorized access"
ERROR_HTTP_INTERNAL_SERVER_ERROR = STR_ARG(_PROTOCOL_PARAM) + ": WEB-Server internal error"
ERROR_FAILED_GETTING_OS_TYPE = STR_ARG(_PROTOCOL_PARAM) + ": Failed detecting OS type"
ERROR_HTTP_BAD_REQUEST =STR_ARG(_PROTOCOL_PARAM)+ ": Bad request"
ERROR_HTTP_TIMEOUT =STR_ARG(_PROTOCOL_PARAM)+ ": Timeout"
ERROR_HTTP_GENERAL =STR_ARG(_PROTOCOL_PARAM)+ ": URL is unaccessible"
ERROR_ABORTED_ESTABLEISGED_CONNECTION = STR_ARG(_PROTOCOL_PARAM) + ": An established connection was aborted by the software in your host machine."
ERROR_DESTINATION_IS_UNREACHABLE =STR_ARG(_PROTOCOL_PARAM)+ ": Destination is unreachable"
ERROR_FAILED_GETTING_MSEXCHANGE =STR_ARG(_PROTOCOL_PARAM)+ ": Failed to discover MS-Exchange"
ERROR_FAILED_GETTING_MSMQ_INFORMATION = STR_ARG(_PROTOCOL_PARAM) + ": Failed getting information about Microsoft Message Queue"
ERROR_SSH_DISABLED = STR_ARG(_PROTOCOL_PARAM) + ": Disconnecting because key exchange failed in local or remote end"
ERROR_FAILED_TO_CONNECT_TO_SERVER = STR_ARG(_PROTOCOL_PARAM) + ": Connection refused: no further information."
ERROR_UNEXPECTED_CONNECTION_INTERRUPTION = STR_ARG(_PROTOCOL_PARAM) + ": Connection was interrupted unexpectedly"
ERROR_SSL_HANDSHAKE = STR_ARG(_PROTOCOL_PARAM) + ": Failed to connect - SSL handshake error. Possible no trusted certificate found."

ERROR_VALID_ERROR_SQLSTATE = STR_ARG(_PROTOCOL_PARAM) + ": Valid error SQLSTATEs returned by an external routine or trigger."
ERROR_STATEMENT_CANNOT_COMPLETE = STR_ARG(_PROTOCOL_PARAM) + ": The statement cannot complete because the necessary package was not found in the catalog."

ERROR_SYBASE_LOGIN_FAIL = STR_ARG(_PROTOCOL_PARAM) + ": Login failed. Examine the SQLWarnings chained to this exception for the reason(s)."
ERROR_UNSUPPORTED_ENCODING = STR_ARG(_PROTOCOL_PARAM) + ": Login failed. Unsupported encoding syntax or unsupported encoding. Please check job properties."
SIEBEL_ATTRIBUTE_ERROR = STR_ARG(_PROTOCOL_PARAM) + ": Siebel Site Name is not defined for the used credentials. Please update Siebel Gateway Protocol parameters in the Setup Discovery Probe section."

ERROR_REMOTE_HOST_CLOSED_CONNECTION = STR_ARG(_PROTOCOL_PARAM) + ": Remote host closed connection during handshake"
ERROR_DISCOVERY_BY_PROTOCOL = STR_ARG(_PROTOCOL_PARAM) + ': Failed to run ' + STR_ARG(_DETAILS_PARAM) +' discovery'

ERROR_TRUST_RELATIONSHIPS_FAILED = STR_ARG(_PROTOCOL_PARAM) + ': Trust relationship between this workstation and the primary domain failed'
ERROR_OVERLAPPED_IO = STR_ARG(_PROTOCOL_PARAM) + ': Overlapped I/O operation is in progress'
ERROR_NO_LOGON_SERVER = STR_ARG(_PROTOCOL_PARAM) + ':  There are currently no logon servers available to service the logon request'
ERROR_NO_MSMQ_ROOT_QUEUE ='MSMQ root queue dir not found.'
ERROE_RESOLVING_REMOTE_QUEUE_MACHINE_NAME = "Ip address for remote queue machine is not resolved."
ERROR_NO_SOLARIS_ZONES_DEFINED = STR_ARG(_PROTOCOL_PARAM) + ': Solaris zones are not defined.'
ERROR_WMIC_QUERY_ERROR = STR_ARG(_PROTOCOL_PARAM) + ': Wmic query execution failed with error code.'

ERROR_INVALID_WSDL_CONTENT = STR_ARG(_PROTOCOL_PARAM) + ': Invalid WSDL content.'
ERROR_INVALID_RESPONSE = STR_ARG(_PROTOCOL_PARAM) + ': Invalid response.'
NO_HTTP_ENDPOINTS_TO_PROCESS_ERROR = STR_ARG(_PROTOCOL_PARAM) + ': No http endpoints to process.'

ERROR_SIEBEL_CLIENT_ERROR = STR_ARG(_PROTOCOL_PARAM) + ': Siebel client (srvrmgr) cannot be executed. Please verify specified path.'
ERROR_EXECUTE_COMMAND = STR_ARG(_PROTOCOL_PARAM) + ': Failed to execute command.'

ERROR_FAILED_TO_DISCOVER_INTERFACES = STR_ARG(_PROTOCOL_PARAM) + ': Failed to discover interfaces.'

ERROR_NNM_GET_DATA = STR_ARG(_PROTOCOL_PARAM) + ': Failed to retrieve discovery data from NNMi webservice. For details please check communication log.'

ERROR_FAILED_DISCOVERING_MSDOMAIN_HOSTS = STR_ARG(_PROTOCOL_PARAM) + ': Failed to discover hosts on MS Domain. Details: ' + STR_ARG(_DETAILS_PARAM)
ERROR_RESOLVED_HOST_FROM_DNS = STR_ARG(_PROTOCOL_PARAM) + "Cannot resolve host from DNS"

ERROR_UNSUPPORTED_VERSION = STR_ARG(_PROTOCOL_PARAM) + ': Failed to discover. Details: ' + STR_ARG(_DETAILS_PARAM)

ERROR_DDMI_AGENT_DOES_NOT_SUPPORT_SHELL = STR_ARG(_PROTOCOL_PARAM) + ': DDMI agent does not support shell commands.'

ERROR_FINDING_PROCESS_BY_PORT = 'The discovery job did not find any process listening on port: ' + STR_ARG(_DETAILS_PARAM)
ERROR_FINDING_APPSIG_BY_PROCESS = 'No application signature matches the process ' + STR_ARG(_DETAILS_PARAM)

#Mapping from ClinetConsts, that is used to resolve the protocol name
protocolNames = {
                ClientsConsts.SSH_PROTOCOL_NAME: 'SSH',
                ClientsConsts.TELNET_PROTOCOL_NAME: 'Telnet',
                ClientsConsts.NTCMD_PROTOCOL_NAME: 'NTCMD',
                ClientsConsts.OLD_NTCMD_PROTOCOL_NAME: 'NTCMD',
                ClientsConsts.WMI_PROTOCOL_NAME: 'WMI',
                ClientsConsts.SNMP_PROTOCOL_NAME: 'SNMP',
                ClientsConsts.HTTP_PROTOCOL_NAME: 'HTTP',
                ClientsConsts.SQL_PROTOCOL_NAME: 'SQL',
                ClientsConsts.WEBLOGIC_PROTOCOL_NAME: 'WEBLOGIC',
                ClientsConsts.WEBSPHERE_PROTOCOL_NAME: 'WEBSPHERE',
                ClientsConsts.JBOSS_PROTOCOL_NAME: 'JBOSS',
                ClientsConsts.DDM_AGENT_PROTOCOL_NAME: 'UDA',
                'discoveryprobegateway': 'Probe Shell',
                'as400protocol': 'AS400',
                'nnmprotocol': 'NNM',
                'sapjmxprotocol': 'SAP JMX'
                }


class ErrorMessageConfig:
    "Configuration for handling of specific error"
    SEVERITY_WARN = 'warn'
    SEVERITY_ERROR = 'error'

    def __init__(self, errorMsg, errorCode, severity=SEVERITY_ERROR, shouldStop=0):
        self.errorMsg = errorMsg
        self.errorCode = errorCode
        self.severity = severity
        self.shouldStop = shouldStop

    def isWarn(self):
        return self.severity == self.SEVERITY_WARN

    def isError(self):
        return self.severity == self.SEVERITY_ERROR


class ErrorResolver:
    "Resolves errors to error configs"
    def __init__(self, data=None):
        #list of keys is maintained in order to ensure the
        #predictable iteration order
        self.configsMap = LinkedHashMap()
        if data:
            self.configsMap.putAll(data)
        self.initDefaultConfigs()

    def addConfig(self, pattern, config):
        self.configsMap.put(pattern, config)

    def hasConfig(self, msg):
        iterator = self.configsMap.keySet().iterator()
        while iterator.hasNext():
            pattern = iterator.next()
            if re.search(pattern, msg, re.I | re.M):
                return 1

    def getConfig(self, msg):
        iterator = self.configsMap.keySet().iterator()
        while iterator.hasNext():
            pattern = iterator.next()
            if re.search(pattern, msg, re.I | re.M):
                return self.configsMap.get(pattern)

    def getDefaultConfig(self):
        return self.defaultConfig

    def copy(self):
        return ErrorResolver(self.configsMap)

    def __len__(self):
        return self.configsMap.size()

    def __getitem__(self, key):
        return self.configsMap.get(key)

    def __setitem__(self, key, item):
        self.addConfig(key, item)

    def keys(self):
        return self.configsMap.keySet()

    def initDefaultConfigs(self):
        self.defaultConfigWithDetails = ErrorMessageConfig(ERROR_GENERIC_WITH_DETAILS, errorcodes.INTERNAL_ERROR_WITH_PROTOCOL_DETAILS)
        self.defaultConfig = ErrorMessageConfig(ERROR_CONNECTION_FAILED, errorcodes.CONNECTION_FAILED)
        self.defaultConfigNoProtocol = ErrorMessageConfig(ERROR_CONNECTION_FAILED_NO_PROTOCOL, errorcodes.CONNECTION_FAILED_NO_PROTOCOL)
        self.defaultConfigNoProtocolWithDetails = ErrorMessageConfig(ERROR_CONNECTION_FAILED_NO_PROTOCOL_WITH_DETAILS, errorcodes.CONNECTION_FAILED_NO_PROTOCOL_WITH_DETAILS)


class ErrorResolverFactory:
    "Factory to produce error resolvers"
    def __init__(self):
        self.resolver = ErrorResolver()
        noAgentConfig = ErrorMessageConfig(WARN_NO_AGENT, errorcodes.NO_AGENT, severity=ErrorMessageConfig.SEVERITY_WARN, shouldStop=1)
        connectionRefusedConfig = ErrorMessageConfig(ERROR_CONNECTION_REFUSED, errorcodes.NO_AGENT, severity=ErrorMessageConfig.SEVERITY_WARN, shouldStop=1)
        # SSH may report "Key exchange failed: Failed to connect to server: Connection refused: no further information (uc)"
        self.resolver['Key exchange failed: Failed to connect to server'] = ErrorMessageConfig(ERROR_FAILED_TO_CONNECT_TO_SERVER, errorcodes.KEY_EXCHANGE_FAILED)
        self.resolver['.*[Cc]onnection refused.*'] = ErrorMessageConfig(ERROR_CONNECTION_REFUSED, errorcodes.NO_AGENT, severity=ErrorMessageConfig.SEVERITY_WARN, shouldStop=1)
        self.resolver['.*CIM_ERR_ACCESS_DENIED.*'] = ErrorMessageConfig(ERROR_CONNECTION_REFUSED, errorcodes.INVALID_USERNAME_PASSWORD, severity=ErrorMessageConfig.SEVERITY_WARN, shouldStop=1)
        self.resolver['.*NO_SUCH_PRINCIPAL.*'] = ErrorMessageConfig(ERROR_CONNECTION_REFUSED, errorcodes.INVALID_USERNAME_PASSWORD, severity=ErrorMessageConfig.SEVERITY_WARN, shouldStop=1)
        self.resolver['javax.naming.NamingException'] = ErrorMessageConfig(WARN_QUERY_FAILURE,
                                                               errorcodes.FAILED_QUERY,
                                                               severity=ErrorMessageConfig.SEVERITY_WARN)
        self.resolver['No libvirt Found.'] = ErrorMessageConfig(WARN_NO_XEN_FOUND, errorcodes.NO_XEN_FOUND, severity=ErrorMessageConfig.SEVERITY_WARN)
        self.resolver['Failed to discover MS-Exchange.*'] = ErrorMessageConfig(ERROR_FAILED_GETTING_MSEXCHANGE, errorcodes.MS_EXCHANGE_ERROR, severity=ErrorMessageConfig.SEVERITY_ERROR)
        self.resolver['Failed getting information about Microsoft Message Queue'] = ErrorMessageConfig(ERROR_FAILED_GETTING_MSMQ_INFORMATION, errorcodes.FAILED_GETTING_MSMQ_INFORMATION, severity=ErrorMessageConfig.SEVERITY_WARN)
        self.resolver['Server does not support zones'] = ErrorMessageConfig(ERROR_NO_SOLARIS_ZONES_DEFINED, errorcodes.NO_SOLARIS_ZONES_DEFINED, severity=ErrorMessageConfig.SEVERITY_WARN)
        self.resolver['ValueError: Current Probe range list is empty'] = ErrorMessageConfig(ERROR_NO_RANGES_DEFINED, errorcodes.NO_RANGES_DEFINED)
        self.resolver['java.nio.charset.UnsupportedCharsetException'] = ErrorMessageConfig(ERROR_UNSUPPORTED_ENCODING, errorcodes.UNSUPPORTED_ENCODING)
        self.resolver['java.io.UnsupportedEncodingException'] = ErrorMessageConfig(ERROR_UNSUPPORTED_ENCODING, errorcodes.UNSUPPORTED_ENCODING)
        self.resolver['java.lang.NullPointerException'] = ErrorMessageConfig(ERROR_OPERATION_FAILED, errorcodes.OPERATION_FAILED)
        self.resolver['ServiceUnavailableException'] = ErrorMessageConfig(ERROR_DESTINATION_IS_UNREACHABLE, errorcodes.DESTINATION_IS_UNREACHABLE, severity=ErrorMessageConfig.SEVERITY_WARN)
        self.resolver['[Cc]onnection reset'] = ErrorMessageConfig(ERROR_CONNECTION_REFUSED_DETAILS, errorcodes.NO_AGENT, severity=ErrorMessageConfig.SEVERITY_WARN, shouldStop=1)
        self.resolver['connection refused'] = connectionRefusedConfig
        self.resolver['connection failed'] = noAgentConfig
        self.resolver['a communication error has been detected'] = noAgentConfig
        self.resolver['[OraDriver] Connection refused from server'] = connectionRefusedConfig
        self.resolver['permission denied'] = ErrorMessageConfig(ERROR_NO_PERMISSIONS, errorcodes.PERMISSION_DENIED)
        self.resolver['unknown user.?name or bad password'] = ErrorMessageConfig(ERROR_INVALID_USERNAME_PASSWORD, errorcodes.INVALID_USERNAME_PASSWORD)
        self.resolver['Login failed'] = ErrorMessageConfig(ERROR_INVALID_USERNAME_PASSWORD, errorcodes.INVALID_USERNAME_PASSWORD)
        self.resolver['.*Failed to authenticate with provided credentials.*'] = ErrorMessageConfig(ERROR_INVALID_USERNAME_PASSWORD, errorcodes.INVALID_USERNAME_PASSWORD)
        self.resolver['.*Command timed out.*'] = ErrorMessageConfig(ERROR_TIMEOUT, errorcodes.COMMAND_TIMED_OUT)
        self.resolver['.*Read timed out'] = ErrorMessageConfig(ERROR_TIMEOUT, errorcodes.COMMAND_TIMED_OUT)
        self.resolver['connection timeout'] = ErrorMessageConfig(ERROR_CONNECTION_TIMED_OUT, errorcodes.TIMEOUT_WITH_REMOTE_AGENT, severity=ErrorMessageConfig.SEVERITY_ERROR, shouldStop=0)
        self.resolver['command timed out'] = ErrorMessageConfig(ERROR_COMMAND_TIMED_OUT, errorcodes.COMMAND_TIMED_OUT)
        self.resolver['getSudoPassword failed.*'] = ErrorMessageConfig(ERROR_GET_SUDO_PASSWORD_FAILED, errorcodes.FAILED_GETTING_SUDO_PASSWORD, severity=ErrorMessageConfig.SEVERITY_ERROR, shouldStop=1)
        self.resolver['Failed getting interfaces'] = ErrorMessageConfig(ERROR_FAILED_TO_DISCOVER_INTERFACES, errorcodes.ERROR_FAILED_TO_DISCOVER_INTERFACES, severity=ErrorMessageConfig.SEVERITY_ERROR, shouldStop=1)
        
        self.resolver['Failed.*OS type'] = ErrorMessageConfig(ERROR_FAILED_GETTING_OS_TYPE, errorcodes.FAILED_GETTING_OS_TYPE)
        self.resolver['timed? *out'] = ErrorMessageConfig(ERROR_CONNECTION_TIMED_OUT, errorcodes.TIMEOUT_WITH_REMOTE_AGENT)
        self.resolver['ping refused'] = ErrorMessageConfig(ERROR_CONNECTION_PING_TIMED_OUT, errorcodes.TIMEOUT_PING_WITH_REMOTE_AGENT)
        self.resolver['telnet refused'] = ErrorMessageConfig(ERROR_CONNECTION_TELNET_TIMED_OUT, errorcodes.TIMEOUT_TELNET_WITH_REMOTE_AGENT)
        self.resolver['not.*enough privileges'] = ErrorMessageConfig(ERROR_NO_PERMISSIONS, errorcodes.PERMISSION_DENIED)
        self.resolver['credentials id.*was not found in Protocol Dictionary Manager'] = ErrorMessageConfig(ERROR_OPERATION_FAILED, errorcodes.OPERATION_FAILED)
        #This server doesn't support ssh1, connect with ssh2 enabled
        self.resolver['server doesn\'t support ssh1'] = ErrorMessageConfig(ERROR_CONNECTION_FAILED, errorcodes.CONNECTION_FAILED)
        self.resolver['could not perform telnet connection'] = ErrorMessageConfig(ERROR_CONNECTION_FAILED, errorcodes.CONNECTION_FAILED)
        self.resolver['java.net.ConnectException'] = ErrorMessageConfig(ERROR_CONNECTION_FAILED, errorcodes.CONNECTION_FAILED, severity=ErrorMessageConfig.SEVERITY_WARN)
        self.resolver['InputStreamPipe closed'] = ErrorMessageConfig(ERROR_TIMEOUT, errorcodes.TIMEOUT_WITH_REMOTE_AGENT)
        self.resolver['client is down or does not support NTCMD'] = noAgentConfig
        self.resolver['network path is not accessible'] = ErrorMessageConfig(ERROR_NETWORK_PATH_IS_NOT_ACCESSIBLE, errorcodes.NETWORK_PATH_IS_NOT_ACCESSIBLE)
        self.resolver['network name is no longer available'] = ErrorMessageConfig(ERROR_NETWORK_PATH_IS_NO_LONGER_AVAILABLE, errorcodes.NETWORK_PATH_IS_NOT_ACCESSIBLE)
        self.resolver['No network provider accepted the given network path.'] = ErrorMessageConfig(ERROR_NETWORK_PATH_IS_NOT_ACCESSIBLE, errorcodes.NETWORK_PATH_IS_NOT_ACCESSIBLE)
        self.resolver['not enough (space on disk|disk space)'] = ErrorMessageConfig(ERROR_NOT_ENOUGH_SPACE, errorcodes.ERROR_NOT_ENOUGH_DISK_SPACE)
        self.resolver['out of memory'] = ErrorMessageConfig(ERROR_OUT_OF_MEMORY, errorcodes.OUT_OF_MEMORY)
        self.resolver['service is disabled'] = ErrorMessageConfig(ERROR_SERVICE_IS_DISABLED, errorcodes.SERVICE_IS_DISABLED)

        #WMI
        self.resolver['rpc call canceled'] = ErrorMessageConfig(ERROR_CONNECTION_TIMED_OUT, errorcodes.CONNECTION_TIMED_OUT_NO_TIMEOUT_VALUE)
        self.resolver['rpc server not'] = noAgentConfig
        self.resolver['access denied,'] = ErrorMessageConfig(ERROR_INVALID_USERNAME_PASSWORD, errorcodes.INVALID_USERNAME_PASSWORD)
        self.resolver['invalid user\\s*name'] = ErrorMessageConfig(ERROR_INVALID_USERNAME_PASSWORD, errorcodes.INVALID_USERNAME_PASSWORD)
        self.resolver['specified service does not exist'] = noAgentConfig
        #Messages when connection is closed in the middle
        self.resolver['the pipe is being closed'] = ErrorMessageConfig(ERROR_UNEXPECTED_CONNECTION_INTERRUPTION, errorcodes.UNEXPECTED_CONNECTION_INTERRUPTION)
        self.resolver['process was not launched or already terminated'] = ErrorMessageConfig(ERROR_UNEXPECTED_CONNECTION_INTERRUPTION, errorcodes.UNEXPECTED_CONNECTION_INTERRUPTION)
        self.resolver['SSLHandshakeException'] = ErrorMessageConfig(ERROR_SSL_HANDSHAKE, errorcodes.ERROR_SSL_HANDSHAKE)

        #HR_REG
        self.resolver['reg_mam.exe.*the system cannot find the file specified'] = ErrorMessageConfig(ERROR_REG_MAM_NOT_FOUND, errorcodes.REG_MAM_NOT_FOUND)

        #HTTP
        self.resolver['status code 400'] = ErrorMessageConfig(ERROR_HTTP_BAD_REQUEST, errorcodes.HTTP_BAD_REQUEST)
        self.resolver['status code 404'] = ErrorMessageConfig(ERROR_HTTP_PAGE_NOT_FOUND, errorcodes.HTTP_PAGE_NOT_FOUND)
        self.resolver['status code 403'] = ErrorMessageConfig(ERROR_NO_PERMISSIONS, errorcodes.PERMISSION_DENIED)
        self.resolver['status code 401'] = ErrorMessageConfig(ERROR_HTTP_UNAUTHORIZED, errorcodes.HTTP_UNAUTHORIZED)
        self.resolver['status code 408'] = ErrorMessageConfig(ERROR_HTTP_TIMEOUT, errorcodes.HTTP_TIMEOUT)
        self.resolver['status code 40[^01348\w\s]'] = ErrorMessageConfig(ERROR_HTTP_GENERAL, errorcodes.HTTP_URL_UNACCESSIBLE)
        self.resolver['status code 41'] = ErrorMessageConfig(ERROR_HTTP_GENERAL, errorcodes.HTTP_URL_UNACCESSIBLE)
        #SSH
        self.resolver['Key exchange failed:  SSH Disabled'] = ErrorMessageConfig(ERROR_SSH_DISABLED, errorcodes.KEY_EXCHANGE_FAILED)
        self.resolver['Key exchange failed: I/O error3: unknown error'] = ErrorMessageConfig(ERROR_CONNECTION_FAILED, errorcodes.CONNECTION_FAILED)
        self.resolver['Key exchange failed: Licensing limits exceeded'] = ErrorMessageConfig(ERROR_LICENCE_LIMITS_EXEDEED, errorcodes.KEY_EXCHANGE_FAILED)
        self.resolver['Key exchange failed: I/O error3: An established connection was aborted'] = ErrorMessageConfig(ERROR_ABORTED_ESTABLEISGED_CONNECTION, errorcodes.KEY_EXCHANGE_FAILED)
        self.resolver['Key exchange failed:  Client Disconnect'] = ErrorMessageConfig(ERROR_CLIENT_DISCONECT, errorcodes.KEY_EXCHANGE_FAILED)
        self.resolver['Key exchange failed:  Maximum connections reached'] = ErrorMessageConfig(ERROR_MAXIMUM_CONNECTIONS_REACHED, errorcodes.KEY_EXCHANGE_FAILED)
        self.resolver['Key exchange failed: I/O error3: An existing connection was forcibly closed by the remote host'] = ErrorMessageConfig(ERROR_FORCE_CLOSED_CONNECTION, errorcodes.KEY_EXCHANGE_FAILED)
        self.resolver['status code 5'] = ErrorMessageConfig(ERROR_HTTP_INTERNAL_SERVER_ERROR, errorcodes.HTTP_INTERNAL_SERVER_ERROR)
        #DB2
        self.resolver['SQLCODE: -805, SQLSTATE: 51002'] = ErrorMessageConfig(ERROR_STATEMENT_CANNOT_COMPLETE, errorcodes.STATEMENT_CANNOT_COMPLETE)
        self.resolver['SQLCODE: -443, SQLSTATE: 38553'] = ErrorMessageConfig(ERROR_VALID_ERROR_SQLSTATE, errorcodes.VALID_ERROR_SQLSTATE)
        self.resolver['SQL1092'] = ErrorMessageConfig(ERROR_NO_PERMISSIONS, errorcodes.PERMISSION_DENIED)
        self.resolver['IO Exception opening socket'] = ErrorMessageConfig(ERROR_CONNECTION_FAILED, errorcodes.CONNECTION_FAILED, shouldStop=1)
        self.resolver['password invalid'] = ErrorMessageConfig(ERROR_INVALID_USERNAME_PASSWORD, errorcodes.INVALID_USERNAME_PASSWORD, severity=ErrorMessageConfig.SEVERITY_WARN)
        self.resolver['.*Failed to execute command: virsh version'] = ErrorMessageConfig(ERROR_VIRSH_COMMAND, errorcodes.ERROR_VIRSH_COMMAND, severity=ErrorMessageConfig.SEVERITY_WARN, shouldStop=1) 

        #SNMP
        self.resolver['Could not perform snmp connection to'] = ErrorMessageConfig(ERROR_CONNECTION_FAILED, errorcodes.CONNECTION_FAILED)

        self.resolver['Connect attempt timed out'] = ErrorMessageConfig(ERROR_HTTP_TIMEOUT, errorcodes.HTTP_TIMEOUT)
        self.resolver['No route to host'] = ErrorMessageConfig(ERROR_DESTINATION_IS_UNREACHABLE, errorcodes.DESTINATION_IS_UNREACHABLE)
        #SYBASE
        self.resolver['JZ00L: Login failed'] = ErrorMessageConfig(ERROR_SYBASE_LOGIN_FAIL, errorcodes.SYBASE_LOGIN_FAIL)

        #WEB_SERVER
        self.resolver['No valid web server config file was found'] = ErrorMessageConfig(ERROR_GENERIC_WITH_DETAILS, errorcodes.FAILED_FINDING_CONFIGURATION_FILE_WITH_PROTOCOL)
        self.resolver['ORACLE_HOME not found.'] = ErrorMessageConfig(ERROR_ORACLE_HOME_NOT_FOUND, errorcodes.FAILED_GETTING_INFORMATION)
        self.resolver['Couldn\'t find tnsnames.ora configuration file.'] = ErrorMessageConfig(ERROR_ORACLE_TNSNAMES_NOT_FOUND, errorcodes.FAILED_GETTING_INFORMATION)
        self.resolver['siebelgtwyprotocol_site'] = ErrorMessageConfig(SIEBEL_ATTRIBUTE_ERROR, errorcodes.FAILED_GETTING_INFORMATION)
        self.resolver['trust relationship between this workstation and the primary domain failed'] = ErrorMessageConfig(ERROR_TRUST_RELATIONSHIPS_FAILED, errorcodes.CONNECTION_FAILED_WITH_DETAILS)
        self.resolver['overlapped I/O operation is in progress'] = ErrorMessageConfig(ERROR_OVERLAPPED_IO, errorcodes.CONNECTION_FAILED_WITH_DETAILS)
        self.resolver['no logon servers available'] = ErrorMessageConfig(ERROR_NO_LOGON_SERVER, errorcodes.CONNECTION_FAILED_WITH_DETAILS)
        self.resolver['Root queue dir not found'] = ErrorMessageConfig(ERROR_NO_MSMQ_ROOT_QUEUE, errorcodes.MSMQ_ENV_CONF_ERROR)
        self.resolver['Ip address for machine name.*could not be retrieved'] = ErrorMessageConfig(ERROE_RESOLVING_REMOTE_QUEUE_MACHINE_NAME, errorcodes.MSMQ_ENV_CONF_ERROR, severity=ErrorMessageConfig.SEVERITY_WARN)
        self.resolver['Failed to obtain ip routing information'] = ErrorMessageConfig(WARN_IP_ROUTE_INFORMATION, errorcodes.FAILED_GETTING_INFORMATION, severity=ErrorMessageConfig.SEVERITY_WARN)
        self.resolver['Wmic query execution failed with error code'] = ErrorMessageConfig(ERROR_WMIC_QUERY_ERROR, errorcodes.FAILED_GETTING_INFORMATION, severity=ErrorMessageConfig.SEVERITY_WARN)
        # LDAP
        self.resolver['In order to perform this operation a successful bind must be completed on the connection'] = ErrorMessageConfig(ERROR_CONNECTION_FAILED, errorcodes.CONNECTION_FAILED, severity=ErrorMessageConfig.SEVERITY_WARN)

        # AS400
        self.resolver['User ID is not known'] = ErrorMessageConfig(ERROR_INVALID_USERNAME_PASSWORD, errorcodes.INVALID_USERNAME_PASSWORD, severity=ErrorMessageConfig.SEVERITY_WARN)
        self.resolver['Password is incorrect'] = ErrorMessageConfig(ERROR_INVALID_USERNAME_PASSWORD, errorcodes.INVALID_USERNAME_PASSWORD, severity=ErrorMessageConfig.SEVERITY_WARN)

        # Webservice discovery
        self.resolver['WSDLException: faultCode=PARSER_ERROR'] = ErrorMessageConfig(ERROR_INVALID_WSDL_CONTENT, errorcodes.INVALID_WSDL_CONTENT, severity=ErrorMessageConfig.SEVERITY_WARN)

        # Siebel Windows Shell
        self.resolver['CreateProcess.*?srvrmgr\.exe'] = ErrorMessageConfig(ERROR_SIEBEL_CLIENT_ERROR, errorcodes.SIEBEL_CLIENT_ERROR, severity=ErrorMessageConfig.SEVERITY_WARN, shouldStop=1)
        self.resolver['Cannot run program.*?srvrmgr\.exe'] = ErrorMessageConfig(ERROR_SIEBEL_CLIENT_ERROR, errorcodes.SIEBEL_CLIENT_ERROR, severity=ErrorMessageConfig.SEVERITY_WARN, shouldStop=1)
        self.resolver['.*Failed to execute command:.*ifconfig'] = ErrorMessageConfig(ERROR_EXECUTE_COMMAND, errorcodes.ERROR_EXECUTE_COMMAND, severity=ErrorMessageConfig.SEVERITY_WARN, shouldStop=1)
        self.resolver['.*\(404\)\/NmsSdkService.*'] = ErrorMessageConfig(ERROR_NNM_GET_DATA, errorcodes.ERROR_NNM_GET_DATA, severity=ErrorMessageConfig.SEVERITY_WARN, shouldStop=1)

        #MS Domain
        self.resolver['Failed to discover hosts on MS Domain'] = ErrorMessageConfig(ERROR_FAILED_DISCOVERING_MSDOMAIN_HOSTS, errorcodes.FAILED_DISCOVERIING_MSDOMAIN_HOST, severity=ErrorMessageConfig.SEVERITY_WARN, shouldStop=0)

        # DNS Discovery
        self.resolver['Cannot resolve host from DNS'] = ErrorMessageConfig(ERROR_RESOLVED_HOST_FROM_DNS, errorcodes.FAILED_RESOLVE_HOST_FROM_DNS, severity=ErrorMessageConfig.SEVERITY_ERROR, shouldStop=0)
        #HRA
        self.resolver['.*Not supported '] = ErrorMessageConfig(ERROR_UNSUPPORTED_VERSION, errorcodes.UNSUPPORTED_VERSION, severity=ErrorMessageConfig.SEVERITY_ERROR, shouldStop=0)
        
        # DDMI agent
        self.resolver["Agent Version v9.* doesn't support shell commands"] = ErrorMessageConfig(ERROR_DDMI_AGENT_DOES_NOT_SUPPORT_SHELL, errorcodes.DDMI_AGENT_DOES_NOT_SUPPORT_SHELL, severity=ErrorMessageConfig.SEVERITY_ERROR, shouldStop=0)
        
    def getResolver(self):
        """
        Warning: same instance is returned every time. It's possible for this instance to be shared
        among multiple threads, in order to avoid concurrency problems, do not change its state
        (e.g. do not add new resolvers if you are not sure).
        """
        return self.resolver

    def getEmptyResolver(self):
        return ErrorResolver()


class Reporter:
    "Helper class to resolve errors and report them to either Framework directly or in provided collections indirectly"
    def __init__(self, resolver):
        self.resolver = resolver

    def resolve(self, error, protocolConst):
        config = None
        logException =1
        protocol = self.getProtocolName(protocolConst)

        if protocol:
            if error:
                config = self.resolver.getConfig(error)
                if config is None:
                    config = self.resolver.defaultConfigWithDetails
                logException =0
            else:
                config = self.resolver.defaultConfig
        else:
            if error:
                config = self.resolver.defaultConfigNoProtocolWithDetails
            else:
                config = self.resolver.defaultConfigNoProtocol

        self.errConfig = config
        self.makeMessage(error, protocol, logException)

    def getProtocolName(self, protocolConst):
        protocol = None
        if protocolConst is not None:
            if protocolConst in protocolNames:
                protocol = protocolNames[protocolConst]
            else:
                protocol = protocolConst
        return protocol

    def makeMessage(self, error, protocol, logException):
        params = {}
        params[_PROTOCOL_PARAM] = protocol
        params[_DETAILS_PARAM] = error

        self.msg = self.errConfig.errorMsg % params
        self.params = [protocol, error]

        if logException:
            logger.debugException(self.msg +'\n')
        else:
            logger.debug(self.msg)

    def getErrorObject(self):
        cfg = self.errConfig
        errobj = errorobject.createError(cfg.errorCode, self.params, self.msg)
        return errobj

    def addToErrorCollections(self, warningsList, errorsList):
        if (warningsList is not None and self.errConfig.isWarn()):
            warningsList.append(self.msg)
        elif (errorsList is not None and self.errConfig.isError()):
            errorsList.append(self.msg)

    def addToErrorObjectsCollections(self, warningsList, errorsList):
        cfg = self.errConfig
        if (warningsList is not None and self.errConfig.isWarn()):
            errobj = errorobject.createError(cfg.errorCode, self.params, self.msg)
            warningsList.append(errobj)
        elif (errorsList is not None and self.errConfig.isError()):
            errobj = errorobject.createError(cfg.errorCode, self.params, self.msg)
            errorsList.append(errobj)

    def reportToFramework(self, framework):
        cfg = self.errConfig
        errobj = errorobject.createError(cfg.errorCode, self.params, self.msg)
        if cfg.isWarn():
            logger.reportWarningObject(errobj)
        elif cfg.isError():
            logger.reportErrorObject(errobj)

    def shouldStop(self):
        return self.errConfig.shouldStop


# Warning: this resolver is shared among multiple threads, so in order to avoid
# concurrency issues, do not modify the state of this resolver
# (e.g. do not add new resolvers after creation).
resolver = ErrorResolverFactory().getResolver()


def resolveAndAddToCollections(error, protocol, warningsList, errorsList):
    "Resolve message, log it, add to collections, return whether we should stop after that"
    reporter = Reporter(resolver)
    reporter.resolve(error, protocol)
    reporter.addToErrorCollections(warningsList, errorsList)
    return reporter.shouldStop()

def resolveAndAddToObjectsCollections(error, protocol, warningsList, errorsList):
    "Resolve message, log it, add to collections, return whether we should stop after that"
    reporter = Reporter(resolver)
    reporter.resolve(error, protocol)
    reporter.addToErrorObjectsCollections(warningsList, errorsList)
    return reporter.shouldStop()

def resolveAndReport(error, protocol, framework):
    "Resolve message, log it, report it, return whether we should stop after that"
    reporter = Reporter(resolver)
    reporter.resolve(error, protocol)
    reporter.reportToFramework(framework)
    return reporter.shouldStop()

def resolveError(error, protocol):
    "Resolve message, create a new ErrorObject from it and return it"
    reporter = Reporter(resolver)
    reporter.resolve(error, protocol)
    return reporter.getErrorObject()

def makeErrorMessage(protocol, message=None, pattern=ERROR_GENERIC_WITH_DETAILS):
    params = {}
    params[_PROTOCOL_PARAM] =protocol
    params[_DETAILS_PARAM] =message
    return pattern % params


if __name__ == "__main__":

    resolver = ErrorResolverFactory().getResolver()
    protocolName = "SSH"
    #add custom config if required
    resolver['SSH'] = ErrorMessageConfig("%(protocol)s: Problem with SSH", errorcodes.SSH_PROBLEM, ErrorMessageConfig.SEVERITY_WARN, 1)
    #override the default message if required
    resolver['connection refused'] = ErrorMessageConfig("%(protocol)s: Connection refused", errorcodes.NO_AGENT, ErrorMessageConfig.SEVERITY_WARN, 1)

    #test messages
    errors = ["Error: connection refused: connect",
            "SSH1 is not supported",
            "Failed to connect: Error connecting: Connection time out: connect",
            "Something bad happened",
            "RPC server not available.",
            "The specified service does not exist as an installed service."]

    for error in errors:
        config = resolver.getConfig(error)
        params = {}
        params[_PROTOCOL_PARAM] =protocolName
        if (config is None):
            config = resolver.defaultConfigWithDetails
            params[_DETAILS_PARAM] =error
        print config.errorMsg % params
