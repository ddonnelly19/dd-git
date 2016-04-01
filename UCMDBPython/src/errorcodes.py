#coding=utf-8
"""
Predefined error codes, that are expected to be used throughout all scripts.
"""

'''
Content codes (101-9999)
'''

# Internal Errors
INTERNAL_ERROR = 101 # Unknown exception
INTERNAL_ERROR_WITH_PROTOCOL = 102 # Unknown exception
INTERNAL_ERROR_WITH_PROTOCOL_DETAILS = 103 # Unknown exception
FAILED_ADDING_ENTITIES_TO_PROBE_DB = 104
NO_RANGES_DEFINED = 105

# Connection Errors
CONNECTION_FAILED = 200
CONNECTION_FAILED_WITH_DETAILS = 201
CONNECTION_FAILED_NO_PROTOCOL = 202
CONNECTION_FAILED_NO_PROTOCOL_WITH_DETAILS = 203
DESTINATION_IS_UNREACHABLE = 204 # Exception error code
NO_AGENT = 205 # exception for connection refused / client doesn't support ntcmd / rpc server not / specified service not exist
PROTOCOL_NOT_DEFINED = 206
NO_REPLY_FROM_HTTP_SERVER = 207
OPERATION_FAILED = 208
DDMI_AGENT_DOES_NOT_SUPPORT_SHELL = 209

# Credential-Related Errors
PERMISSION_DENIED = 300 # no permissions issues, access denied (incl. http 403, sql 1092)
PERMISSION_DENIED_NO_PROTOCOL_WITH_DETAILS = 301
INVALID_USERNAME_PASSWORD = 302
NO_CREDENTIALS_FOR_TRIGGERED_IP = 303 # Credentials error in network basic discovery (snmp / wmi)
KEY_EXCHANGE_FAILED = 304
FAILED_GETTING_OS_TYPE=305
SSL_CERTIFICATE_FAILED=306
FAILED_TESTING_SUDO_FOR_CREDENTIAL=307
FAILED_GETTING_SUDO_PASSWORD=308

# Timeout Errors
COMMAND_TIMED_OUT = 400 # Exception errcode
TIMEOUT_WITH_REMOTE_AGENT = 401 # Exceptions (general time out + InputStreamPipe closed + rpc call cancelled)
CONNECTION_TIMEOUT_NO_PROTOCOL = 402 # currently used during tcp discovery
CONNECTION_TIMED_OUT_NO_TIMEOUT_VALUE = 403 # separate connection timeout error for cases when protocol does not support setting timeout value

# Unexpected/Invalid Behaviours
UNEXPECTED_CONNECTION_INTERRUPTION = 500 # Exceptions: pipe being closed + process not launched or already terminated
FAILED_FINDING_CONFIGURATION_FILE = 501
MISSING_JARS_ERROR = 503
FAILED_FINDING_CONFIGURATION_FILE_WITH_PROTOCOL = 504

# Software Related Errors
FAILED_FINDING_PROCESS_BY_PORT = 510
FAILED_FINDING_APPSIG_BY_PROCESS = 511
PORT_NOT_IN_CONFIGFILE = 512

# Information Retrieval Errors
FAILED_GETTING_HOST_INFORMATION = 600 # errors getting information during discovery (e.g. boot date or host name)
FAILED_READING_APP_COMPONENTS = 601 # During host resources - getApplicationsTopology()
FAILED_GETTING_INFORMATION = 602
FAILED_GETTING_INFORMATION_NO_PROTOCOL = 603
FAILED_QUERYING_AGENT = 604
EMPTY_DATA_RECEIVED = 605
FAILED_LOADING_MODULE = 606
FAILED_TRANSFER_DNS_ZONE = 607

# Resources-Related Errors
OUT_OF_MEMORY = 700 # Exception for memory shortage
CLIENT_NOT_CLOSED_PROPERLY = 701 # used when failing to close client in 'finally' section
ERROR_NOT_ENOUGH_DISK_SPACE = 702 # Exception for disk space shortage

# Parsing Errors
IP_PARSING_ERROR = 800 # Parsing netstat/lsof/pfiles output
PARSING_ERROR_NO_PROTOCOL_NO_DETAILS = 801

# Encoding Errors
UNSUPPORTED_ENCODING = 900

# SQL Related Errors
STATEMENT_CANNOT_COMPLETE = 901 # Exception SQLCODE -805
VALID_ERROR_SQLSTATE = 902 # Exception SQLCODE -443
SYBASE_LOGIN_FAIL = 903 # Exception errcode
FAILED_TO_EXECUTE_SQL = 924

# HTTP Related Errors
HTTP_BAD_REQUEST = 904 # exception: http code 400
HTTP_PAGE_NOT_FOUND = 905 # exception: http code 404
HTTP_UNAUTHORIZED = 906 # exception: http code 401
HTTP_TIMEOUT = 907 # exceptions: http code 408 + connect attmped timed out
HTTP_URL_UNACCESSIBLE = 908 # exceptions: other http codes
HTTP_INTERNAL_SERVER_ERROR = 909 # Exception errcode





#######################################
# Need to be analyzed by content team #
#######################################


SSH_PROBLEM = 129 # Exceptions that didn't match any other pattern but include 'SSH' in the message
NO_RESULTS_WILL_BE_REPORTED = 136 # During snmp connection exception: BroadcastIpDiscoveryException
FAILED_DISCOVERING_RESOURCE = 142 # e.g. failed discovering cpus
FAILED_DISCOVERING_RESOURCE_WITH_CLIENT_TYPE = 143 # E.G. failed discovering users with snmp
PROCESS_STARTUP_TIME_ATTR_NOT_SET = 145 # used when discovering host resources
PROCESS_STARTUP_TIME_ATTR_NOT_SET_NO_PROTOCOL = 146
FAILED_RUNNING_DISCOVERY = 148
FAILED_RUNNING_DISCOVERY_WITH_CLIENT_TYPE = 149
FAILED_HANDLING_INCLUDE_FILE = 502
FAILED_TO_DISCOVER_ALTEON = 150
NETWORK_PATH_IS_NOT_ACCESSIBLE = 114 # Exception
SERVICE_IS_DISABLED = 116 # Exception
FAILED_QUERY = 608 # general error when query failed by some protocol
UNSUPPORTED_VERSION = 609 #unsupported version of missing discoverer
# Specific Application Errors
REG_MAM_NOT_FOUND = 910 # Exception : cannot find reg_mam.exe
PROCESS_TO_PROCESS_FAILED = 911 # Exception caught during process-to-process
LSOF_WRONG_VERSION = 912 # Used during tcp discovery
FAILED_LINKING_ELEMENTS = 913 # Alteon APP Switch by SNMP
NO_REAL_GROUP_FOUND_FOR_REAL_SERVER = 914 # Alteon APP Switch by SNMP
NO_SERVICE_FOUND_FOR_NODE = 915 # Cisco CSS by SNMP
CSS_NOT_FOUND_ON_TARGET_HOST = 916 # Cisco CSS by SNMP
UNABLE_TO_DETERMINE_MQ_VERSION = 917
NO_QUEUE_MANAGERS_FOUND = 918
MS_EXCHANGE_OBJECTS_NOT_FOUND = 919
MS_CLUSTER_INSTANCES_NOT_FOUND = 920
SERVICE_GUARD_CLUSTER_NOT_FOUND = 921
ADDITIONAL_WEBSERVER_INSTANCES_ARE_SKIPPED = 922 # TCP Webserver detection
COMMAND_OUTPUT_VERIFICATION_FAILED = 923
MSMQ_ENV_CONF_ERROR = 925
NO_SOLARIS_ZONES_DEFINED = 926
NO_XEN_FOUND = 927
MS_EXCHANGE_ERROR = 928
FAILED_GETTING_MSMQ_INFORMATION = 929
INVALID_WSDL_CONTENT = 930
SIEBEL_CLIENT_ERROR = 931
ERROR_EXECUTE_COMMAND = 932
ERROR_NNM_GET_DATA = 933
ERROR_SSL_HANDSHAKE = 934
INVALID_RESPONSE = 935
NO_HTTP_ENDPOINTS_TO_PROCESS = 936

ERROR_VIRSH_COMMAND = 937
ERROR_FAILED_TO_DISCOVER_INTERFACES = 938
FAILED_DISCOVERIING_MSDOMAIN_HOST=939
FAILED_RESOLVE_HOST_FROM_DNS=940

TIMEOUT_PING_WITH_REMOTE_AGENT = 404 
TIMEOUT_TELNET_WITH_REMOTE_AGENT = 405
