#coding=utf-8
"""
This library helps in creating common classes and links
"""

import logger
import netutils
import re
import string
import ip_addr


from appilog.common.system.defines import AppilogTypes
from appilog.common.system.types import AttributeStateHolder, ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector, StringVector
from appilog.common.utils.zip import ChecksumZipper
from appilog.common.utils import IPv4
from appilog.common.utils import RangeType

from com.hp.ucmdb.discovery.common import CollectorsConstants
from com.hp.ucmdb.discovery.library.communication.downloader import ConfigFilesManagerImpl
from com.hp.ucmdb.discovery.library.communication.downloader.cfgfiles import GeneralSettingsConfigFile
from com.hp.ucmdb.discovery.library.communication.downloader.cfgfiles import PortInfo
from com.hp.ucmdb.discovery.library.scope import DomainScopeManager
from com.hp.ucmdb.discovery.library.clients import ClientsConsts
from com.hp.ucmdb.discovery.library.clients import ScriptsExecutionManager
from com.mercury.topaz.cmdb.shared.model.object.id import CmdbObjectID

from java.lang import String
from java.text import ParseException, SimpleDateFormat
from java.util import Date, Locale, SimpleTimeZone
from java.util.regex import Pattern
############ MODELING CONSTANTS #######

SERVICEADDRESS_TYPE_TCP = 1
SERVICEADDRESS_TYPE_UDP = 2
SERVICEADDRESS_TYPE_URL = 3

############ STORAGE TYPES ############
FIXED_DISK_STORAGE_TYPE = 'FixedDisk'
NETWORK_DISK_STORAGE_TYPE = 'NetworkDisk'
COMPACT_DISK_STORAGE_TYPE = 'CompactDisk'
REMOVABLE_DISK_STORAGE_TYPE = 'RemovableDisk'
FLOPPY_DISK_STORAGE_TYPE = 'FloppyDisk'
VIRTUAL_MEMORY_STORAGE_TYPE = 'VirtualMemory'
FLASH_MEMORY_STORAGE_TYPE = 'FlashMemory'
RAM_DISK_STORAGE_TYPE = 'RamDisk'
RAM_STORAGE_TYPE = 'Ram'
NO_ROOT_DIRECTORY_STORAGE_TYPE = 'No Root Directory'
OTHER_STORAGE_TYPE = 'Other'
UNKNOWN_STORAGE_TYPE = "UNKNOWN"
IGNORE_INTERFACE_PATTERN_FILTER = ['LoopBack', 'Wireless', 'Virtual', 'WAN',
                                   'RAS Async', 'Bluetooth', 'FireWire', 'VPN',
                                   'Tunnel adapter', 'Tunneling Pseudo',
                                   'Hamachi', '1394', 'Miniport', 'TAP\-Win32',
                                   'Teefer2', 'PPP\/SLIP']
IP_ADDRESS_PROPERTY_LOOPBACK = 'loopback'
IP_ADDRESS_PROPERTY_DHCP = 'dhcp'
IP_ADDRESS_PROPERTY_BROADCAST = 'broadcast'
IP_ADDRESS_PROPERTY_ANYCAST = 'anycast'

MIME_TEXT_PLAIN = "text/plain"
MIME_TEXT_XML = "text/xml"

OS_TYPE_AND_CLASS_TO_OS_FAMILY_MAP = {
                                  'linux': 'unix',
                                  'sunos': 'unix',
                                  'freebsd': 'unix',
                                  'aix': 'unix',
                                  'unix': 'unix',
                                  'nt': 'windows',
                                  'windows': 'windows',
                                  'vax': 'vax',
                                  'hp-ux': 'unix',
                                  'vmware_esx_server': 'baremetal_hypervisor',
                                  'vmkernel': 'baremetal_hypervisor',
                                  'ipar': 'mainframe',
                                  'lpar': 'mainframe',
                                  'mainframe': 'mainframe',
                                  'Darwin': 'unix',
                                  'Mac OS X': 'unix',
                                  'OS X': 'unix',
                            }

databaseDataNames = {
                'oracle': 'Oracle DB',
                'sqlserver': 'MSSQL DB',
                'db2_database': 'IBM DB2',
                'db2_instance': 'IBM DB2 Instance',
                'sybase': 'Sybase DB',
                'maxdb': 'SAP MaxDB',
                'hana_database': 'SAP HanaDB',
                'mysql': 'MySQL DB',
                'postgresql': 'PostgreSQL'
                }

STORAGE_ID_TO_STORAGE_TYPE = {
                            0: OTHER_STORAGE_TYPE,
                            1: NO_ROOT_DIRECTORY_STORAGE_TYPE,
                            2: REMOVABLE_DISK_STORAGE_TYPE,
                            3: FIXED_DISK_STORAGE_TYPE,
                            4: NETWORK_DISK_STORAGE_TYPE,
                            5: COMPACT_DISK_STORAGE_TYPE,
                            6: RAM_STORAGE_TYPE}

applicationNameToProductNameMap = {
        #DB servers
    'Oracle DB': 'oracle_database',
    'SAP MaxDB': 'maxdb',
    'SAP HanaDB': 'hana_database',
    'MSSQL DB': 'sql_server_database',
    'IBM DB2 Instance': 'db2_instance',
    'IBM DB2': 'db2_database',
    'Sybase DB': 'sybase_database',
    'MySQL DB': 'mysql_database',
    'PostgreSQL': 'postgresql_database',
        #App servers
    'JBoss AS': 'jboss_application_server',
    'Oracle iAS': 'oraclei_application_server',
    'WebLogic AS': 'weblogic_application_server',
    'WebSphere AS': 'websphere_application_server',
    'Glassfish AS': 'glassfish_application_server',
    'Jetty WebServer': 'jetty_application_server',
        #Web servers
    'Microsoft IIS WebServer': 'iis_web_server',
    'Apache WebServer': 'apache_web_server',
    'Apache Tomcat': 'tomcat_web_server',
        #clusters
    'Microsoft Cluster SW': 'microsoft_cluster',
    'HP Service Guard Cluster SW': 'service_guard_cluster',
    'Veritas Cluster SW': 'veritas_cluster',
    'Red Hat Cluster Suite': 'redhat_cluster',
        #SAP
    'SAP ABAP Central Services': 'abap_sap_central_services',
    'SAP ABAP Application Server': 'sap_abap_application_server',
    'SAP J2EE Central Services': 'j2ee_sap_central_services',
    'SAP J2EE Application Server': 'sap_j2ee_application_server',
    'SAP ITS Manager': 'sap_its_agate',
    'SAP Message Server': 'sap_message_server',
    'SAP Enqueue Server': 'sap_enqueue_server',
        #Siebel
    'Siebel Server': 'siebel_application_server',
    'Siebel Gateway Name Server': 'siebel_gateway',
        #Virtualization
    'Virtualization Layer Software': 'vmware_hypervisor',
    'VMware VirtualCenter': 'vmware_virtual_center',
    'Microsoft Hyper-V Hypervisor': 'microsoft_hypervisor',
    'IBM HMC': 'ibm_hardware_management_console',
        # Virtualization - Oracle
    'Oracle VM Manager': 'oracle_vm_manager',
    'Oracle VM Agent': 'oracle_vm_agent',
        #Other
    'Microsoft Exchange Server': 'microsoft_exchange_server',
    'IBM WebSphere MQ': 'ibm_websphere_mq',
    'Active Directory Application Mode': 'active_directory_application_mode',
    'Citrix': 'citrix_xenapp_server',
    'DomainController': 'domain_controller'}

applicationTypeToDiscoveredProductNameMap = {
                # SAP
                'abap_sap_central_services': 'SAP ABAP Central Services',
                'j2ee_sap_central_services': 'SAP J2EE Central Services',
                'sap_r3_server': 'SAP ABAP Application Server',
                'sap_j2ee_app_server': 'SAP J2EE Application Server',
                'sap_message_server': 'SAP Message Server',
                'sap_enqueue_server': 'SAP Enqueue Server',

                    #Siebel
                'siebel_app_server': 'Siebel Server',
                'siebel_gateway': 'Siebel Gateway Name Server'
                }

CLASSES_80_TO_BDM = {'host': 'node',
                'clusteredservice': 'cluster_resource_group',
                'clustergroup': 'cluster_resource_group_config',
                'clusterresource': 'cluster_resource_config',
                'hostresource': 'node_element',
                'service': 'windows_service',
                'logicalvolume': 'logical_volume',
                'disk': 'file_system',
                'software': 'installed_software',
                'ipserver': 'ip_service_endpoint',
                'url': 'uri_endpoint',
                'application': 'running_software',
                'failoverclustersoftware': 'cluster_software',
                'dnsserver': 'dns_server',
                'webserver': 'web_server',
                'networkresource': 'network_entity',
                'network': 'ip_subnet',
                'ip': 'ip_address',
                'applicationsystem': 'application_system',
                'document': 'configuration_document',
                'configfile': 'configuration_document',
                'failovercluster': 'failover_cluster',
                'port': 'physical_port',
                'networkshare': 'file_system_export',
                'business': 'business_element',
                'logical_service': 'service',
                'business_service_for_catalog': 'business_service',
                'logical_application': 'business_application',
                'business_unit': 'organization',
                'line_of_business': 'business_function',
                'member': 'membership',
                'depend': 'dependency',
                'clientserver': 'client_server',
                'depends_on': 'usage',
                'use': 'usage',
                'run': 'execution_environment',
                'owner': 'ownership',
                'potentially_run': 'ownership'}

MIME_TYPES = {'3dm': 'x-world/x-3dmf',
                '3dmf': 'x-world/x-3dmf',
                'a': 'application/octet-stream',
                'aab': 'application/x-authorware-bin',
                'aam': 'application/x-authorware-map',
                'aas': 'application/x-authorware-seg',
                'abc': 'text/vnd.abc',
                'acgi': 'text/html',
                'afl': 'video/animaflex',
                'ai': 'application/postscript',
                'aif': 'audio/x-aiff',
                'aifc': 'audio/x-aiff',
                'aiff': 'audio/x-aiff',
                'aim': 'application/x-aim',
                'aip': 'text/x-audiosoft-intra',
                'ani': 'application/x-navi-animation',
                'aps': 'application/mime',
                'arc': 'application/octet-stream',
                'arj': 'application/octet-stream',
                'art': 'image/x-jg',
                'asf': 'video/x-ms-asf',
                'asm': 'text/x-asm',
                'asp': 'text/asp',
                'asx': 'video/x-ms-asf',
                'au': 'audio/x-au',
                'avi': 'video/avi',
                'avs': 'video/avs-video',
                'bcpio': 'application/x-bcpio',
                'bin': 'application/octet-stream',
                'bm': 'image/bmp',
                'bmp': 'image/bmp',
                'boo': 'application/book',
                'book': 'application/book',
                'boz': 'application/x-bzip2',
                'bsh': 'application/x-bsh',
                'bz': 'application/x-bzip',
                'bz2': 'application/x-bzip2',
                'c': 'text/plain',
                'c++': 'text/plain',
                'cat': 'application/vnd.ms-pki.seccat',
                'cc': 'text/plain',
                'ccad': 'application/clariscad',
                'cco': 'application/x-cocoa',
                'cdf': 'application/cdf',
                'cer': 'application/x-x509-ca-cert',
                'cha': 'application/x-chat',
                'chat': 'application/x-chat',
                'class': 'application/java',
                'com': 'application/octet-stream',
                'conf': 'text/plain',
                'cpio': 'application/x-cpio',
                'cpp': 'text/x-c',
                'cpt': 'application/x-compactpro',
                'crl': 'application/pkcs-crl',
                'crt': 'application/x-x509-ca-cert',
                'csh': 'text/x-script.csh',
                'css': 'text/css',
                'cxx': 'text/plain',
                'dcr': 'application/x-director',
                'deepv': 'application/x-deepv',
                'def': 'text/plain',
                'der': 'application/x-x509-ca-cert',
                'dif': 'video/x-dv',
                'dir': 'application/x-director',
                'dl': 'video/x-dl',
                'doc': 'application/msword',
                'dot': 'application/msword',
                'dp': 'application/commonground',
                'drw': 'application/drafting',
                'dump': 'application/octet-stream',
                'dv': 'video/x-dv',
                'dvi': 'application/x-dvi',
                'dwf': 'model/vnd.dwf',
                'dwg': 'image/x-dwg',
                'dxf': 'image/x-dwg',
                'dxr': 'application/x-director',
                'el': 'text/x-script.elisp',
                'elc': 'application/x-elc',
                'env': 'application/x-envoy',
                'eps': 'application/postscript',
                'es': 'application/x-esrehber',
                'etx': 'text/x-setext',
                'evy': 'application/x-envoy',
                'exe': 'application/octet-stream',
                'f': 'text/plain',
                'f77': 'text/x-fortran',
                'f90': 'text/plain',
                'fdf': 'application/vnd.fdf',
                'fif': 'image/fif',
                'fli': 'video/x-fli',
                'flo': 'image/florian',
                'flx': 'text/vnd.fmi.flexstor',
                'fmf': 'video/x-atomic3d-feature',
                'for': 'text/plain',
                'fpx': 'image/vnd.net-fpx',
                'frl': 'application/freeloader',
                'funk': 'audio/make',
                'g': 'text/plain',
                'g3': 'image/g3fax',
                'gif': 'image/gif',
                'gl': 'video/x-gl',
                'gsd': 'audio/x-gsm',
                'gsm': 'audio/x-gsm',
                'gsp': 'application/x-gsp',
                'gss': 'application/x-gss',
                'gtar': 'application/x-gtar',
                'gz': 'application/x-compressed',
                'gzip': 'application/x-gzip',
                'h': 'text/plain',
                'hdf': 'application/x-hdf',
                'help': 'application/x-helpfile',
                'hgl': 'application/vnd.hp-hpgl',
                'hh': 'text/plain',
                'hlb': 'text/x-script',
                'hlp': 'application/x-helpfile',
                'hpg': 'application/vnd.hp-hpgl',
                'hpgl': 'application/vnd.hp-hpgl',
                'hqx': 'application/binhex',
                'hta': 'application/hta',
                'htc': 'text/x-component',
                'htm': 'text/html',
                'html': 'text/html',
                'htmls': 'text/html',
                'htt': 'text/webviewhtml',
                'htx': 'text/html',
                'ice': 'x-conference/x-cooltalk',
                'ico': 'image/x-icon',
                'idc': 'text/plain',
                'ief': 'image/ief',
                'iefs': 'image/ief',
                'iges': 'application/iges',
                'igs': 'application/iges',
                'ima': 'application/x-ima',
                'imap': 'application/x-httpd-imap',
                'inf': 'text/plain',
                'inf': 'application/inf',
                'ins': 'application/x-internett-signup',
                'ip': 'application/x-ip2',
                'isu': 'video/x-isvideo',
                'it': 'audio/it',
                'iv': 'application/x-inventor',
                'ivr': 'i-world/i-vrml',
                'ivy': 'application/x-livescreen',
                'jam': 'audio/x-jam',
                'jav': 'text/plain',
                'java': 'text/plain',
                'jcm': 'application/x-java-commerce',
                'jfif': 'image/jpeg',
                'jfif-tbnl': 'image/jpeg',
                'jpe': 'image/jpeg',
                'jpeg': 'image/jpeg',
                'jpg': 'image/jpeg',
                'jps': 'image/x-jps',
                'js': 'application/x-javascript',
                'jut': 'image/jutvision',
                'kar': 'audio/midi',
                'ksh': 'text/x-script.ksh',
                'la': 'audio/x-nspaudio',
                'lam': 'audio/x-liveaudio',
                'latex': 'application/x-latex',
                'lha': 'application/octet-stream',
                'lhx': 'application/octet-stream',
                'list': 'text/plain',
                'lma': 'audio/x-nspaudio',
                'log': 'text/plain',
                'lsp': 'text/x-script.lisp',
                'lst': 'text/plain',
                'lsx': 'text/x-la-asf',
                'ltx': 'application/x-latex',
                'lzh': 'application/octet-stream',
                'lzx': 'application/octet-stream',
                'm': 'text/plain',
                'm1v': 'video/mpeg',
                'm2a': 'audio/mpeg',
                'm2v': 'video/mpeg',
                'm3u': 'audio/x-mpequrl',
                'man': 'application/x-troff-man',
                'map': 'application/x-navimap',
                'mar': 'text/plain',
                'mbd': 'application/mbedlet',
                'mc$': 'application/x-magic-cap-package-1.0',
                'mcd': 'application/x-mathcad',
                'mcf': 'text/mcf',
                'mcp': 'application/netmc',
                'me': 'application/x-troff-me',
                'mht': 'message/rfc822',
                'mhtml': 'message/rfc822',
                'mid': 'audio/midi',
                'midi': 'audio/midi',
                'mif': 'application/x-frame',
                'mime': 'www/mime',
                'mjf': 'audio/x-vnd.audioexplosion.mjuicemediafile',
                'mjpg': 'video/x-motion-jpeg',
                'mm': 'application/base64',
                'mme': 'application/base64',
                'mod': 'audio/x-mod',
                'moov': 'video/quicktime',
                'mov': 'video/quicktime',
                'movie': 'video/x-sgi-movie',
                'mp2': 'video/mpeg',
                'mp3': 'audio/mpeg3',
                'mpa': 'audio/mpeg',
                'mpc': 'application/x-project',
                'mpe': 'video/mpeg',
                'mpeg': 'video/mpeg',
                'mpg': 'video/mpeg',
                'mpga': 'audio/mpeg',
                'mpp': 'application/vnd.ms-project',
                'mpt': 'application/x-project',
                'mpv': 'application/x-project',
                'mpx': 'application/x-project',
                'mrc': 'application/marc',
                'ms': 'application/x-troff-ms',
                'mv': 'video/x-sgi-movie',
                'my': 'audio/make',
                'mzz': 'application/x-vnd.audioexplosion.mzz',
                'nap': 'image/naplps',
                'naplps': 'image/naplps',
                'nc': 'application/x-netcdf',
                'ncm': 'application/vnd.nokia.configuration-message',
                'nif': 'image/x-niff',
                'niff': 'image/x-niff',
                'nix': 'application/x-mix-transfer',
                'nsc': 'application/x-conference',
                'nvd': 'application/x-navidoc',
                'o': 'application/octet-stream',
                'oda': 'application/oda',
                'omc': 'application/x-omc',
                'omcd': 'application/x-omcdatamaker',
                'omcr': 'application/x-omcregerator',
                'p': 'text/x-pascal',
                'p10': 'application/x-pkcs10',
                'p12': 'application/x-pkcs12',
                'p7a': 'application/x-pkcs7-signature',
                'p7c': 'application/x-pkcs7-mime',
                'p7m': 'application/x-pkcs7-mime',
                'p7r': 'application/x-pkcs7-certreqresp',
                'p7s': 'application/pkcs7-signature',
                'part': 'application/pro_eng',
                'pas': 'text/pascal',
                'pbm': 'image/x-portable-bitmap',
                'pcl': 'application/vnd.hp-pcl',
                'pct': 'image/x-pict',
                'pcx': 'image/x-pcx',
                'pdb': 'chemical/x-pdb',
                'pdf': 'application/pdf',
                'pfunk': 'audio/make',
                'pgm': 'image/x-portable-graymap',
                'pic': 'image/pict',
                'pict': 'image/pict',
                'pkg': 'application/x-newton-compatible-pkg',
                'pko': 'application/vnd.ms-pki.pko',
                'pl': 'text/plain',
                'plx': 'application/x-pixclscript',
                'pm': 'image/x-xpixmap',
                'pm4': 'application/x-pagemaker',
                'pm5': 'application/x-pagemaker',
                'png': 'image/png',
                'pnm': 'image/x-portable-anymap',
                'pot': 'application/vnd.ms-powerpoint',
                'pov': 'model/x-pov',
                'ppa': 'application/vnd.ms-powerpoint',
                'ppm': 'image/x-portable-pixmap',
                'pps': 'application/vnd.ms-powerpoint',
                'ppt': 'application/vnd.ms-powerpoint',
                'ppz': 'application/mspowerpoint',
                'pre': 'application/x-freelance',
                'prt': 'application/pro_eng',
                'ps': 'application/postscript',
                'psd': 'application/octet-stream',
                'pvu': 'paleovu/x-pv',
                'pwz': 'application/vnd.ms-powerpoint',
                'py': 'text/x-script.phyton',
                'pyc': 'applicaiton/x-bytecode.python',
                'qcp': 'audio/vnd.qcelp',
                'qd3': 'x-world/x-3dmf',
                'qd3d': 'x-world/x-3dmf',
                'qif': 'image/x-quicktime',
                'qt': 'video/quicktime',
                'qtc': 'video/x-qtc',
                'qti': 'image/x-quicktime',
                'qtif': 'image/x-quicktime',
                'ra': 'audio/x-realaudio',
                'ram': 'audio/x-pn-realaudio',
                'ras': 'image/x-cmu-raster',
                'rast': 'image/cmu-raster',
                'rexx': 'text/x-script.rexx',
                'rf': 'image/vnd.rn-realflash',
                'rgb': 'image/x-rgb',
                'rm': 'audio/x-pn-realaudio',
                'rmi': 'audio/mid',
                'rmm': 'audio/x-pn-realaudio',
                'rmp': 'audio/x-pn-realaudio',
                'rng': 'application/ringing-tones',
                'rnx': 'application/vnd.rn-realplayer',
                'roff': 'application/x-troff',
                'rp': 'image/vnd.rn-realpix',
                'rpm': 'audio/x-pn-realaudio-plugin',
                'rt': 'text/richtext',
                'rtf': 'text/richtext',
                'rtx': 'text/richtext',
                'rv': 'video/vnd.rn-realvideo',
                's': 'text/x-asm',
                's3m': 'audio/s3m',
                'saveme': 'application/octet-stream',
                'sbk': 'application/x-tbook',
                'scm': 'video/x-scm',
                'sdml': 'text/plain',
                'sdp': 'application/x-sdp',
                'sdr': 'application/sounder',
                'sea': 'application/x-sea',
                'set': 'application/set',
                'sgm': 'text/sgml',
                'sgml': 'text/sgml',
                'sh': 'text/x-script.sh',
                'shar': 'application/x-bsh',
                'shtml': 'text/html',
                'sid': 'audio/x-psid',
                'sit': 'application/x-stuffit',
                'skd': 'application/x-koan',
                'skm': 'application/x-koan',
                'skp': 'application/x-koan',
                'skt': 'application/x-koan',
                'sl': 'application/x-seelogo',
                'smi': 'application/smil',
                'smil': 'application/smil',
                'snd': 'audio/x-adpcm',
                'sol': 'application/solids',
                'spc': 'text/x-speech',
                'spl': 'application/futuresplash',
                'spr': 'application/x-sprite',
                'sprite': 'application/x-sprite',
                'src': 'application/x-wais-source',
                'ssi': 'text/x-server-parsed-html',
                'ssm': 'application/streamingmedia',
                'sst': 'application/vnd.ms-pki.certstore',
                'step': 'application/step',
                'stl': 'application/x-navistyle',
                'stp': 'application/step',
                'sv4cpio': 'application/x-sv4cpio',
                'sv4crc': 'application/x-sv4crc',
                'svf': 'image/x-dwg',
                'svr': 'application/x-world',
                'swf': 'application/x-shockwave-flash',
                't': 'application/x-troff',
                'talk': 'text/x-speech',
                'tar': 'application/x-tar',
                'tbk': 'application/x-tbook',
                'tcl': 'text/x-script.tcl',
                'tcsh': 'text/x-script.tcsh',
                'tex': 'application/x-tex',
                'texi': 'application/x-texinfo',
                'texinfo': 'application/x-texinfo',
                'text': 'text/plain',
                'tgz': 'application/x-compressed',
                'tif': 'image/x-tiff',
                'tiff': 'image/x-tiff',
                'tr': 'application/x-troff',
                'tsi': 'audio/tsp-audio',
                'tsp': 'application/dsptype',
                'tsv': 'text/tab-separated-values',
                'turbot': 'image/florian',
                'txt': 'text/plain',
                'uil': 'text/x-uil',
                'uni': 'text/uri-list',
                'unis': 'text/uri-list',
                'unv': 'application/i-deas',
                'uri': 'text/uri-list',
                'uris': 'text/uri-list',
                'ustar': 'application/x-ustar',
                'uu': 'text/x-uuencode',
                'uue': 'text/x-uuencode',
                'vbs': 'text/vbs',
                'vcd': 'application/x-cdlink',
                'vcs': 'text/x-vcalendar',
                'vda': 'application/vda',
                'vdo': 'video/vdo',
                'vew': 'application/groupwise',
                'viv': 'video/vivo',
                'vivo': 'video/vivo',
                'vmd': 'application/vocaltec-media-desc',
                'vmf': 'application/vocaltec-media-file',
                'voc': 'audio/x-voc',
                'vos': 'video/vosaic',
                'vox': 'audio/voxware',
                'vqe': 'audio/x-twinvq-plugin',
                'vqf': 'audio/x-twinvq',
                'vql': 'audio/x-twinvq-plugin',
                'vrml': 'application/x-vrml',
                'vrt': 'x-world/x-vrt',
                'vsd': 'application/x-visio',
                'vst': 'application/x-visio',
                'vsw': 'application/x-visio',
                'w60': 'application/wordperfect6.0',
                'w61': 'application/wordperfect6.1',
                'w6w': 'application/msword',
                'wav': 'audio/x-wav',
                'wb1': 'application/x-qpro',
                'wbmp': 'image/vnd.wap.wbmp',
                'web': 'application/vnd.xara',
                'wiz': 'application/msword',
                'wk1': 'application/x-123',
                'wmf': 'windows/metafile',
                'wml': 'text/vnd.wap.wml',
                'wmlc': 'application/vnd.wap.wmlc',
                'wmls': 'text/vnd.wap.wmlscript',
                'wmlsc': 'application/vnd.wap.wmlscriptc',
                'word': 'application/msword',
                'wp': 'application/wordperfect',
                'wp5': 'application/wordperfect',
                'wp6': 'application/wordperfect',
                'wpd': 'application/wordperfect',
                'wq1': 'application/x-lotus',
                'wri': 'application/x-wri',
                'wrl': 'application/x-world',
                'wrz': 'model/vrml',
                'wsc': 'text/scriplet',
                'wsrc': 'application/x-wais-source',
                'wtk': 'application/x-wintalk',
                'xbm': 'image/x-xbitmap',
                'xdr': 'video/x-amt-demorun',
                'xgz': 'xgl/drawing',
                'xif': 'image/vnd.xiff',
                'xl': 'application/excel',
                'xla': 'application/x-msexcel',
                'xlb': 'application/x-excel',
                'xlc': 'application/x-excel',
                'xld': 'application/x-excel',
                'xlk': 'application/x-excel',
                'xll': 'application/x-excel',
                'xlm': 'application/x-excel',
                'xls': 'application/x-msexcel',
                'xlt': 'application/x-excel',
                'xlv': 'application/x-excel',
                'xlw': 'application/x-msexcel',
                'xm': 'audio/xm',
                'xml': 'text/xml',
                'xmz': 'xgl/movie',
                'xpix': 'application/x-vnd.ls-xpix',
                'xpm': 'image/x-xpixmap',
                'x-png': 'image/png',
                'xsr': 'video/x-amt-showrun',
                'xwd': 'image/x-xwindowdump',
                'xyz': 'chemical/x-pdb',
                'z': 'application/x-compressed',
                'zip': 'application/x-compressed',
                'zoo': 'application/octet-stream',
                'zsh': 'text/x-script.zsh'
                }

TCP_PROTOCOL = PortInfo.TCP_PROTOCOL
UDP_PROTOCOL = PortInfo.UDP_PROTOCOL


class NetworkInterface:
    """
    This class represents Network interface
    @deprecated: use networking.Interface instead
    """
    def __init__(self, description, physicalAddress, ips=None,
                 subnetMasks=None, interfaceIndex=None, dhcpEnabled=0,
                 interfaceClass="interface"):
        self.macAddress = physicalAddress
        self.description = description
        self.interfaceIndex = interfaceIndex
        self.ips = ips
        self.masks = subnetMasks
        self.dhcpEnabled = dhcpEnabled
        self.type = None
        self.adminStatus = None
        self.operStatus = None
        self.speed = None
        self.name = None
        self.alias = None
        self.className = interfaceClass
        self.osh = None
        self.role = None

    def getOsh(self):
        '-> osh or None'
        return self.osh

    def __repr__(self):
        return "[MAC address: %s. Description: %s]" % (self.macAddress,
                                                       self.description)


def _toFloatOrNone(floatString):
    if floatString is not None:
        try:
            return float(floatString)
        except ValueError:
            logger.debug('Can not parse %s to float' % floatString)


def createDiskOSH(containerHost, dataName, type,  # @ReservedAssignment
                    size=None, failures=None, name=None, usedSize=None,
                    mountPoint=None, fileSystemType=None, ciType="disk"):
    """
        Creates an C{ObjectStateHolder} class that represents a disk.
        This method uses may return None in case type is not an allowed storage type.
        @see: isAllowedStorageType
        @param containerHost: the container node ObjectStateHolder
        @type containerHost: ObjectStateHolder
        @param dataName: name of a disk
        @type dataName: string
        @param type: storage type (such as FixedDisk, NetworkDisk, CompactDisk, FloppyDisk, etc)
        @type type: string
        @param size: size of a disk in Megabytes
        @param usedSpace: used disk space in Megabytes
        @type size: double
        @param failures: The number of requests for storage represented by this entry that
                         could not be honored due to not enough storage.
        @type failures: integer
        @param name: name
        @type name: string
        @param mountPoint: A file system path or drive letter where a file system may be mounted.
        @param fileSystemType: The type of a File system (such as FAT, NTFS,NFS etc..)
        @deprecated: use createFileSystemOSH instead
    """
    if type == UNKNOWN_STORAGE_TYPE:
        type = None   # @ReservedAssignment
    elif not isAllowedStorageType(type):
        return None

    diskOSH = ObjectStateHolder(ciType)
    diskOSH.setContainer(containerHost)
    diskOSH.setAttribute('data_name', dataName)
    if type:
        diskOSH.setAttribute('disk_type', type)

    if size and size != '-':
        size = _toFloatOrNone(size)
        if size:  # can't be 0
            diskOSH.setDoubleAttribute('disk_size', size)
            usedSize = _toFloatOrNone(usedSize)
            if usedSize is not None:  # can be 0
                freeDiskPercentage = (size - usedSize) / size * 100
                freeDiskPercentage = round(freeDiskPercentage, 2)
                diskOSH.setDoubleAttribute('free_space', freeDiskPercentage)

    if (failures):
        diskOSH.setAttribute('disk_failures', failures)
    if name and name.strip():
        diskOSH.setStringAttribute('name', name)
    if mountPoint:
        diskOSH.setStringAttribute("mount_point", mountPoint)  # id attribute
    if fileSystemType:
        diskOSH.setStringAttribute("filesystem_type", fileSystemType)
    return diskOSH



def createFileSystemOSH(containerHostOSH, mountPoint, diskType,
                        labelName=None, mountDevice=None, fileSystemType=None,
                        size=None, usedSize=None, failures=None):
    """
        This method uses may return None in case type is not an allowed storage type.
        @see: isAllowedStorageType
        @param containerHostOSH: the container node ObjectStateHolder
        @type containerHostOSH: ObjectStateHolder
        @param mountPoint: A file system path or drive letter where a file system may be mounted.
        @type mountPoint: string
        @param mountDevice: A file system device path where a file system mounted from
        @type mountDevice: string
        @param labelName: label name of a fileSystem
        @type labelName: string
        @param diskType: storage type (such as FixedDisk, NetworkDisk, CompactDisk, FloppyDisk, etc)
        @type diskType: string
        @param size: size of a disk in Megabytes
        @param usedSpace: used disk space in Megabytes
        @type size: double
        @param failures: The number of requests for storage represented by this entry that
                         could not be honored due to not enough storage.
        @param fileSystemType: The type of a File system (such as FAT, NTFS,NFS etc..)
    """
    if diskType == UNKNOWN_STORAGE_TYPE:
        diskType = None
    elif not isAllowedStorageType(diskType):
        return None

    fileSystemOSH = ObjectStateHolder('file_system')
    fileSystemOSH.setContainer(containerHostOSH)
    fileSystemOSH.setStringAttribute('mount_point', mountPoint)   # id attribute

    if diskType:
        fileSystemOSH.setAttribute('disk_type', diskType)

    if labelName and labelName.strip():
        fileSystemOSH.setStringAttribute('name', labelName)

    if mountDevice:
        fileSystemOSH.setStringAttribute("mount_device", mountDevice)

    if fileSystemType:
        fileSystemOSH.setStringAttribute("filesystem_type", fileSystemType)

    if size and size != '-':
        size = _toFloatOrNone(size)
        if size:  # can't be 0
            fileSystemOSH.setDoubleAttribute('disk_size', size)
            usedSize = _toFloatOrNone(usedSize)
            if usedSize is not None:  # can be 0
                freeDiskPercentage = (size - usedSize) / size * 100
                freeDiskPercentage = round(freeDiskPercentage, 2)
                fileSystemOSH.setDoubleAttribute('free_space', freeDiskPercentage)

    if failures:
        fileSystemOSH.setAttribute('disk_failures', failures)

    return fileSystemOSH


def isAllowedStorageType(storageType):
    """
    This method returns true if storageType is included to the list of allowed storage types.
    Allowed storage types are taken from discoveredStorageTypes property which resides inside globalSettings.xml configuration file.
    """
    globalSettings = GeneralSettingsConfigFile.getInstance()

    discoveredStorageTypesString = globalSettings.getPropertyStringValue('discoveredStorageTypes', '')
#    discoveredStorageTypesString = globalSettings.getPropertyStringValue(CollectorsConstants.TAG_DISCOVERED_STORAGE_TYPES, '')
    return isIncludedToList(discoveredStorageTypesString, storageType)


def createInterfacesOSHV(networkInterfaces, containerHostOSH=None):
    """
     Creates a vector of ObjectStateHolder of type C{interface}
     @param networkInterfaces:  - a list of interfaces from which we create the OSHV (Object State Holder Vector).
     @type networkInterfaces: a list NetworkInterface
     @param containerHostOSH:  - the container node of the interfaces
     @type containerHostOSH: ObjectStateHolder
     @return: a vector that contains ObjectStateHolder classes that were created from the input
     @rtype: ObjectStateHolderVector
    """
    oshv = ObjectStateHolderVector()
    for interface in networkInterfaces:
        osh = createInterfaceOSH(interface.macAddress, containerHostOSH, interface.description, interface.interfaceIndex, interface.type, interface.adminStatus, interface.adminStatus, interface.speed, interface.name, interface.alias, interface.className)
        if osh is not None:
            interface.osh = osh
            oshv.add(osh)
        else:
            logger.debug('Mac is invalid and will be skipped: %s' % interface)
    return oshv


def isValidInterface(mac, description=None, name=None):
    """ Check whether interface is valid. Support for NNM pseudo interfaces that are prefixed with constant value.
    str[, str, str] -> bool
    For CMDB 8 check only mac (physical address or interface index)
    For CMDB 9 if mac is not valid - name and description can be checked for existence too
    @deprecated: Logic is not obvious
    """
    NNM_PSEUDO_INTERFACE_PREFIX = 'ZZZZ'
    isValid = mac is not None and (netutils.isValidMac(mac) or str(mac).isdigit() or mac.startswith(NNM_PSEUDO_INTERFACE_PREFIX))
    if not isValid:
        if _CMDB_CLASS_MODEL.version() >= 9:
            isValid = name or description
    return isValid


def createInterfaceOSH(mac, hostOSH=None, description=None, index=None,
                         type=None, adminStatus=None,  # @ReservedAssignment
                         operStatus=None, speed=None, name=None, alias=None,
                         reportInterfaceName = True, interfaceClass="interface"):
    """
     Creates an C{ObjectStateHolder} based on the interface at the specified address. Throws
     @param mac: the MAC address of the interface, or the interface index or the interface description
     @type mac: string - either a MAC address or a MAC index
     @param hostOSH: the container node ObjectStateHolder
     @type hostOSH: ObjectStateHolder
     @return: new interface or None
     @rtype: ObjectStateHolder
    """
    interface = ObjectStateHolder(interfaceClass)

    if not isValidInterface(mac, name, description):
        return None
    try:
        mac = netutils.parseMac(mac)
    except:
        #logger.debug('Failed parsing incorrect mac %s' % mac)
        mac = None
    # mac can also be an interface#
    if netutils.isValidMac(mac):
        interface.setStringAttribute('mac_address', mac)
        interface.setStringAttribute('interface_macaddr', mac)
    elif mac in netutils._IGNORED_INTERFACE_MACS:
        return None
    #interface has a virtual mac so it's a virtual one
    elif netutils.isVirtualMac(mac):
        interface.setStringAttribute('mac_address', mac)
        interface.setBoolAttribute('isvirtual', 1)
        list_ = StringVector(('virtual_interface',))
        roleAttribute = AttributeStateHolder('interface_role', list_)
        interface.addAttributeToList(roleAttribute)
        name = name or description
    elif not name:
        #we have to have or mac_address or interface_name since they define reconciliation rules
        #logger.warn("Reported network interface with invalid macaddress and with no name")
        if description is None:
            #logger.warn("Reported network interface with invalid macaddress and with no name or description. Interface not created")
            return None
        else:
            name = description
    elif not name:
        return None

    if hostOSH:
        interface.setContainer(hostOSH)

    if description:
        interface.setAttribute('interface_description', description)

    if index is not None:
        try:
            interface.setIntegerAttribute('interface_index', index)
        except:
            logger.warn("interface_index is not accepted, value:%s" % index)

    if type:
        intValue = None
        try:
            intValue = int(type)
        except:
            logger.warn("Failed to convert the interface type '%s'" % type)
        else:
            if intValue > 0:
                interface.setEnumAttribute("interface_type", intValue)

    if adminStatus:
        intValue = None
        try:
            intValue = int(adminStatus)
        except:
            logger.warn("Failed to convert the interface admin status '%s'" % adminStatus)
        else:
            if intValue > 0 and intValue < 8:
                interface.setEnumAttribute("interface_admin_status", intValue)

    if operStatus:
        intValue = None
        try:
            intValue = int(operStatus)
        except:
            logger.warn("Failed to convert the interface admin status '%s'" % operStatus)
        else:
            if intValue > 0 and intValue < 8:
                interface.setEnumAttribute("interface_operational_status", intValue)

    if speed is not None:
        longValue = None
        try:
            longValue = long(speed)
        except:
            logger.warn("Failed to convert the interface interface speed '%s'" % speed)
        else:
            if longValue > 0:
                interface.setLongAttribute("interface_speed", longValue)

    if name:
        interface.setAttribute('interface_name', name)

    if alias:
        interface.setAttribute('interface_alias', alias)
    if not reportInterfaceName:
        interface.removeAttribute('interface_name')
    if interfaceClass == 'interface_aggregation':
        interface.setBoolAttribute('isvirtual', 1)
        list_ = StringVector(('aggregate_interface',))
        roleAttribute = AttributeStateHolder('interface_role', list_)
        interface.addAttributeToList(roleAttribute)

    return interface


def createLinkOSH(className, end1, end2):
#~~~ What does className refer to, the type of link, or of the endpoints?
#~~~ Why: @param className: the name of the link to create  Is it the link name or the className
    """
    Creates an C{ObjectStateHolder} class that represents a link.
    The link must be a valid link according to the class model.
      @param className: the name of the link to create
      @type className: string
      @param end1: the I{from} of the link
      @type end1: CmdbObjectID
      @param end2: the I{to} of the link
      @type end2: CmdbObjectID

      @return: a link from end1 to end2 of type className
      @rtype: ObjectStateHolder
    """
    link = ObjectStateHolder(className)
    if (end1.__class__ is ObjectStateHolder):
        link.setAttribute("link_end1", end1)
    else:
        link.setObjectIDAttribute("link_end1", end1)

    if (end2.__class__ is ObjectStateHolder):
        link.setAttribute("link_end2", end2)
    else:
        link.setObjectIDAttribute("link_end2", end2)

    return link


def getIpAddressPropertyValue(ipAddress, netmask, dhcpEnabled=None, interfaceName=None):
    'str, str[, bool or str, str] -> str'
    ipProp = None
    if netutils.isValidIp(ipAddress):
        if netutils.isLocalIp(ipAddress):
            ipProp = IP_ADDRESS_PROPERTY_LOOPBACK
        elif dhcpEnabled and (str(dhcpEnabled).lower() != 'false'):
            ipProp = IP_ADDRESS_PROPERTY_DHCP
        elif netutils.isIpAnycast(ipAddress, interfaceName):
            ipProp = IP_ADDRESS_PROPERTY_ANYCAST
        elif netutils.isIpBroadcast(ipAddress, netmask):
            ipProp = IP_ADDRESS_PROPERTY_BROADCAST
    return ipProp


def _getDomainScopeManager():
    r'@types: -> com.hp.ucmdb.discovery.library.scope.DomainScopeManager'
    return DomainScopeManager


def createIpOSH(ipAddress, netmask=None, dnsname=None, ipProps=None):
    """
    Creates an C{ObjectStateHolder} that represents an IP.
    @param ipAddress: a well formatted IP address
    @type ipAddress: string or ip_addr.IPAddress object
    @param netmask: a well formatted net mask
    @type netmask: string
    @param dnsname: the given IP-related DNS name
    @type dnsname: string

    @return: an IP address OSH
    @rtype: ObjectStateHolder
    """

    if not ipAddress:
        raise ValueError("Receive IP Address that is invalid: %s" % ipAddress)

    ipVersion = 4
    ipAddressString = str(ipAddress)

    if not isinstance(ipAddress, basestring):
        try:
            ipVersion = ipAddress.version
        except:
            logger.debugException('')
    else:
        if not ip_addr.isValidIpAddress(ipAddressString):
            raise ValueError("Receive IP Address that is invalid: %s" % ipAddress)
    
    try:
        domainName = _getDomainScopeManager().getDomainByIp(ipAddressString)
        probeName = None
        if not domainName:
            domainName = '${DefaultDomain}'
        else:
            probeName = _getDomainScopeManager().getProbeName(ipAddressString, domainName)
    except:
        domainName = "DefaultDomain"
        probeName = None

    ipOsh = ObjectStateHolder("ip")
    ipOsh.setStringAttribute("ip_address", ipAddressString)
    ipOsh.setStringAttribute("name", ipAddressString)
    ipOsh.setStringAttribute("ip_domain", domainName)
    if probeName:
        ipOsh.setStringAttribute("ip_probename", probeName)

    if dnsname:
        ipOsh.setStringAttribute("ip_dnsname", dnsname)

    if netmask and ip_addr.isValidNetmaskNotZero(netmask) and ipVersion != 6:
        parsedIp = IPv4(ipAddressString, netmask)
        networkAddress = parsedIp.getNetAddress().toString()
        ipOsh.setAttribute("ip_netaddr", networkAddress)
        ipOsh.setAttribute("ip_netmask", netmask)

        netclass = netutils.getNetworkClassByNetworkMask(netmask)
        if netclass:
            ipOsh.setAttribute("ip_netclass", netclass)

        if not netmask in ('255.255.255.255', '255.255.255.254'):
            broadcastIp = parsedIp.getLastIp()
            if parsedIp.equals(broadcastIp):
                ipOsh.setBoolAttribute("ip_isbroadcast", 1)

    if ipProps:
        ipOsh.setStringAttribute('ip_address_property', ipProps)
        if ipProps == IP_ADDRESS_PROPERTY_DHCP:
            ipOsh.setBoolAttribute('ip_isdhcp', 1)

    return ipOsh


def setHostOsName(hostOsh, osName):
    '@deprecated: Use setOsName of HostBuilder instead'
    if hostOsh:
        hostOsh = HostBuilder(hostOsh).setOsName(osName).build()


COMMA = ', '


def isMatchedByRegexpList(regexpListString, value, delimiter=COMMA):
    """
    Checks if some value part of value can be matched by at least one regexp.
    @param regexpListString: String represented by sequence of regexps separated by some delimiter
    @param value: Actual value which is checked by regexps
    @param delimiter: Delimiter used in regexpListString. By default is ', ' without quotes
    @deprecated: Please do not use this method. It won't be accessible in the public scope
    """
    regexps = regexpListString.split(delimiter)
    for regexp in regexps:
        if re.findall(regexp, value):
            return 1
    return 0


def isIncludedToList(listOfElementsString, value, delimiter=COMMA):
    """ Check value for existance in the string of elements delimited by <delimiter>
    str, str, str -> bool
    @deprecated: Please do not use this method. It won't be accessible in the public scope"""
    elements = listOfElementsString.split(delimiter)
    return elements.count(value) > 0


def addHostAttributes(uh_obj, osName=None, machineName=None, machineBootDate=None):
    """
    Sets the machine name and operation system attributes of a node.
    @param uh_obj: the node to update
    @type uh_obj: OSH
    @param osName: the operation system name, can be None
    @type osName: string
    @param machineName: the machine name, can be None
    @type machineName: string
    """
    setHostOsName(uh_obj, osName)

    if machineName:
        if isValidFQDN(machineName):
            uh_obj.setAttribute("primary_dns_name", machineName)
            names= machineName.split('.', 1)
            uh_obj.setAttribute("host_hostname", names[0])
            if len(names)>1:
                uh_obj.setAttribute("domain_name", names[1])
        else:
            uh_obj.setAttribute('host_hostname', machineName)

    if machineBootDate:
        uh_obj.setDateAttribute('host_last_boot_time', machineBootDate)
        
def isValidFQDN(hostname):
    try:        
        if not hostname:
            return False
        if ip_addr.isValidIpAddress(hostname):
            return False
        if hostname.find(".") <= -1:
            return False
        else:
            return True
        #if re.match(ur'(?=^.{1,254}$)(^(?:(?!\d+\.|-)[a-zA-Z0-9_\-]{1,63}(?<!-)\.?)+(?:[a-zA-Z]{2,})$)', hostname, re.IGNORECASE | re.MULTILINE):
            #return True
        #return False
    except:
        return False


def createHostOSH(ipAddress, hostClassName="node", osName=None,
                  machineName=None, machineBootDate=None, filter_client_ip=None):
#~~~ In what ways is the node not complete? Just missing node key?
    """
    Creates a node OSH with its associated IP Address, operation system name. and machine name.
    The created node is not complete>
    @param ipAddress: a well formated IP address
    @type ipAddress: string
    @param hostClassName: the default is I{node}
    @type hostClassName: string
    @param osName: the operation system name, can be None
    @type osName: string
    @param machineName: the MAC address, can be None
    @type machineName: string
    """
    if filter_client_ip:
        ipType = _getDomainScopeManager().getRangeTypeByIp(ipAddress)
        if ipType and ipType.equals(RangeType.CLIENT):
            return None
    
    try:
        domainName = _getDomainScopeManager().getDomainByIp(ipAddress.strip())
    except:
        domainName = "DefaultDomain"

    host = ObjectStateHolder(hostClassName)
    host.setAttribute("host_key", '%s %s' % (ipAddress, domainName))
    host.setBoolAttribute('host_iscomplete', 0)
    addHostAttributes(host, osName, machineName, machineBootDate)
    return host


def createNetworkOSH(ipAddress, netmask):
    """
    create a new OSH that represent a network
    @param ipAddress: a well formed IP address
    @type ipAddress: string
    @param netmask: a well formed new mask
    @type netmask: string
    @return: a new network OSH
    @rtype: ObjectStateHolder
    """

    parsedIp = IPv4(ipAddress, netmask)
    netAddressStr = parsedIp.getNetAddress().toString()

    domainName = _getDomainScopeManager().getDomainByNetwork(netAddressStr, netmask)
    probeName = _getDomainScopeManager().getProbeNameByNetwork(netAddressStr, netmask, domainName)

    networkOsh = ObjectStateHolder("network")
    networkOsh.setStringAttribute("network_netaddr", netAddressStr)
    networkOsh.setStringAttribute("network_domain", domainName)
    networkOsh.setStringAttribute("network_probename", probeName)
    networkOsh.setStringAttribute("network_netmask", netmask)

    if not netmask in ('255.255.255.255', '255.255.255.254'):
        broadcastAddress = parsedIp.getLastIp().toString()
        networkOsh.setStringAttribute("network_broadcastaddress", broadcastAddress)

        netclass = netutils.getNetworkClassByNetworkMask(netmask)
        if netclass:
            networkOsh.setStringAttribute("network_netclass", netclass)

    if netmask:
        networkOsh.setIntegerAttribute('ip_prefix_length', netutils.getShortMask(netmask))

    return networkOsh


def __isVMWareInterface(interfaceDescription):
    return re.search('VMware', interfaceDescription, re.I)


def __isAllowedInterface(interfaceDescription):
    # ignore Loopback interfaces
    # ignore VMware interfaces
    # ignore Wireless interfaces
    # ignore Bluetooth interfaces
    # ignore Firewire interfaces
    # ignore VPN interfaces
    if interfaceDescription is None:
        return 0

    ignoreLocalizedIinterfacePatternFilter = []
    ignoreLocalizedString = GeneralSettingsConfigFile.getInstance().getPropertyStringValue('ignoreLocalizedVirtualInterfacesPatternList', '')
    ignoreLocalizedIinterfacePatternFilter.extend(IGNORE_INTERFACE_PATTERN_FILTER)
    if ignoreLocalizedString:
        ignoreLocalizedIinterfacePatternFilter.extend(ignoreLocalizedString.split(','))
    for pattern in ignoreLocalizedIinterfacePatternFilter:
        if re.search(pattern, interfaceDescription, re.I):
            return 0

    if __isVMWareInterface(interfaceDescription):
        ignoreVmwareInterfaces = GeneralSettingsConfigFile.getInstance().getPropertyIntegerValue('ignoreVmwareInterfaces', 1)
        if ignoreVmwareInterfaces == 2:
            logger.debug('VMWare interface are configured to be ignored, based on ignoreVmwareInterfaces global parameter:', ignoreVmwareInterfaces)
            return 0
    return 1


def __isKnownHost(hostKey, existingMacs, discoveredMacs):
    #check whether the Host Key is in the retrieved interfaces list:
    if hostKey in discoveredMacs:
        return 1

    #check whether at least one physical MAC was already discovered
    if existingMacs and existingMacs != "NA":
        for existingMac in existingMacs:
            if existingMac in discoveredMacs:
                return 1


def createCompleteHostOSHByInterfaceList(hostClass, interfaceList,
                                              osName=None, machineName=None,
                                              machineBootDate=None,
                                              host_cmdbid=None, host_key=None,
                                              host_macs=None,
                                              ucmdb_version=None):
    """
    Returns the minimal valid mac address to be used as key for the node.
    A valid mac is one that passed isValidMac() method.
    For some interfaces (like Wireless, VMware, Bluetooth etc), the
    MAC address cannot be used as the key.
    @param hostClass: the node type, for example I{nt}
    @type hostClass: string
    @param interfaceList: a list of C{NetworkInterface}
    @type interfaceList: list
    @param osName: operation system name, can be None
    @type osName: string
    @param machineName: can be None
    @type machineName: string
    """

    macList = []
    allMacs = []
    listVMmacList = []
    for interface in interfaceList:
        macAddress = interface.macAddress
        description = interface.description
        isValid = netutils.isValidMac(macAddress)
        if isValid:
            macAddress = netutils.parseMac(macAddress)
            allMacs.append(macAddress)

        if isValid and __isAllowedInterface(description):
            logger.debug('Appending MAC address: %s' % macAddress)
            if __isVMWareInterface(description):
                listVMmacList.append(macAddress)
            else:
                macList.append(macAddress)
        else:
            logger.debug('Ignoring interface: %s' % description)

    if len(macList) > 0:
        if ucmdb_version < 9 and host_cmdbid and host_cmdbid != 'NA' and __isKnownHost(host_key, host_macs, allMacs):
            #node Key is in the interfaces Mac list, restore from the UCMDB-ID
            hostOsh = createOshByCmdbIdString(hostClass, host_cmdbid)
            hostOsh.setBoolAttribute('host_iscomplete', 1)
            addHostAttributes(hostOsh, osName, machineName, machineBootDate)
            return hostOsh

        #Choosing node key as minimal physical MAC address
        hostKey = min(macList)
        return createCompleteHostOSH(hostClass, hostKey, osName, machineName, machineBootDate)
    elif len(listVMmacList) > 0:
        #Choosing node key as minimal virtual MAC address
        hostKey = min(listVMmacList)
        return createCompleteHostOSH(hostClass, hostKey, osName, machineName)
    elif len(allMacs) > 0:
        hostKey = min(allMacs)
        return createCompleteHostOSH(hostClass, hostKey, osName, machineName)
    else:
        logger.debug('Could not find valid host key. Interfaces list: %s' % interfaceList)
        raise Exception('Could not find valid host key')


def createCompleteHostOSH(hostClass, hostKey, osName=None, machineName=None, machineBootDate=None):
    """
    Creates a OSH that represents a complete node.
    @param hostClass: the node type, for example I{nt}
    @type hostClass: string
    @param hostKey: the smallest MAC address of the machine
    @type hostKey: string
    @param osName: operation system name, can be None
    @type osName: string
    @param machineName: can be None
    @type machineName: string
    @rtype: ObjectStateHolder
    """
    uh_obj = ObjectStateHolder(hostClass)
    uh_obj.setAttribute('host_key', hostKey)
    uh_obj.setBoolAttribute('host_iscomplete', 1)
    addHostAttributes(uh_obj, osName, machineName, machineBootDate)
    return uh_obj


def createHostAndIPOSHV(ip):
    """
    Creates an incomplete node and an IP connected with a C{contained} link.
    @param ip: a well formed IP address
    @type ip: string
    @return: return a OSHV that contains three OSH object, IP, node, and a link between them
    @rtype: ObjectStateHolderVector that contains three ObjectStateHolder classes
    """
    vec = ObjectStateHolderVector()
    hostOSH = createHostOSH(ip)
    ipOSH = createIpOSH(ip)
    link = createLinkOSH('contained', hostOSH, ipOSH)

    vec.add(hostOSH)
    vec.add(ipOSH)
    vec.add(link)

    return vec


def processBytesAttribute(stringValue):
    """
    Return data for bytes attribute - zips the data bytes encoded as UTF-8 and
    returns the following information set:
    (Zipped Bytes, CheckSum Value, String Length)
    """
    bytesValue = String(stringValue).getBytes('UTF-8')
    zipper = ChecksumZipper()
    zippedBytes = zipper.zip(bytesValue)
    checksumValue = zipper.getChecksumValue()
    return (zippedBytes, checksumValue, len(stringValue))


def createCFOSH(filename, extension, path, filecontent, containerOSH=None, description=None, charsetName=None):
    """
    Creates a ObjectStateHolder that contains a zipped configuration file.
    This method is deprecated
    """
    if extension:
        filename = filename + '.' + extension
    return createConfigurationDocumentOSH(filename, path, filecontent, containerOSH, None, None, description, None, charsetName)


def createConfigurationDocumentOshByFile(configFile, containerOsh,
                                              contentType=None,
                                              description=None,
                                              charsetName=None):
        configFileOsh = createConfigurationDocumentOSH(
                           configFile.getName(), configFile.path,
                           configFile.content,
                           containerOsh, contentType,
                           configFile.lastModificationTime(),
                           description,
                           configFile.version, charsetName
                        )
        if configFile.owner:
            configFileOsh.setAttribute('document_osowner', configFile.owner)
        if configFile.permissions():
            configFileOsh.setAttribute('document_permissions', configFile.permissions())
        return configFileOsh


def createConfigurationDocumentOSH(name, path, content, containerOSH=None, contentType=None,
                                   contentLastUpdate=None, description=None, version=None, charsetName=None):
    """
    Creates ObjectStateHolder that represents a configuration document.
    @param name: the name of the configuration document
    @type name: string
    @param path: full path to configuration file
    @type path: string
    @param content: contents of configuration file
    @type content: string
    @param containerOSH: the container of the configuration document
    @type containerOSH: ObjectStateHolder
    @param contentType: content type
    @type contentType: string
    @param contentLastUpdate: last time the content was updated
    @type contentLastUpdate: java.util.Date
    @param description: description of the document
    @type description: string
    @param version: version of configuration document
    @type version: string
    @param charsetName: charset name of the content
    @type charsetName: string
    @return: ObjectStateHolder for configuration document
    """

    documentOsh = ObjectStateHolder("configfile")
    documentOsh.setAttribute('data_name', name)
    resolvedContentType = contentType
    if resolvedContentType == None:
        extensionRegex = ".+\.(\w+)$"
        extension = re.match(extensionRegex, name)
        if extension:
            extension = extension.group(1)
            if extension in MIME_TYPES:
                resolvedContentType = MIME_TYPES[extension]
            else:
                resolvedContentType = None
                logger.warn("Content type for file %s was not resolved" % name)
        else:
            logger.warn("Content type for file %s was not resolved" % name)

    if content:
        bytesValue = None
        if charsetName:
            bytesValue = String(content).getBytes(charsetName)
        else:
            bytesValue = String(content).getBytes()
        zipper = ChecksumZipper()
        zippedBytes = zipper.zip(bytesValue)
        checksumValue = zipper.getChecksumValue()
        if len(zippedBytes) <= 512000:
            documentOsh.setBytesAttribute('document_data', zippedBytes)
        else:
            logger.debug('Configuration file %s size is too big' % name)
        documentOsh.setLongAttribute('document_checksum', checksumValue)
        documentOsh.setLongAttribute('document_size', len(bytesValue))
    if path:
        documentOsh.setAttribute('document_path', path)
    if resolvedContentType:
        documentOsh.setAttribute('document_content_type', resolvedContentType)
    if contentLastUpdate:
        documentOsh.setAttribute('document_lastmodified', contentLastUpdate)
    if description:
        documentOsh.setAttribute('data_description', description)
    if version:
        documentOsh.setAttribute('version', version)
    if containerOSH is not None:
        documentOsh.setContainer(containerOSH)

    return documentOsh


class _ProcessDo:
    """Class represents Process Data Object - process with all its attributes"""

    def __init__(self, name, commandline, pid=None, path=None, parameters=None, user=None, startuptime=None, description=None):
        self.name = name
        self.commandline = commandline
        self.pid = pid
        self.path = path
        self.parameters = parameters
        self.user = user
        self.startuptime = startuptime
        self.description = description


class _ProcessMatcher:
    """Class represents process matcher, which decides whether particual process satisfies defined conditions"""

    class Rule:
        """Base class for process matching rule"""
        def __init__(self):
            pass

        def matches(self, processDo):
            pass

    class PropertyMatchRule(Rule):
        """
        Rule which verifies that perticular property of process matches the regex.
        Currently works for String properties or properties that can be converted to String.
        Will raise exception if defined property is not found.
        """
        def __init__(self, targetProperty, pattern, flags=0):
            _ProcessMatcher.Rule.__init__(self)
            self.targetProperty = targetProperty
            self.pattern = pattern
            self.flags = flags

        def matches(self, processDo):
            if processDo:
                value = self._getProperty(processDo)
                if value and re.match(self.pattern, str(value), self.flags):
                    return 1

        def _getProperty(self, processDo):
            return getattr(processDo, self.targetProperty)

    def __init__(self):
        self._rules = []

    def matches(self, processDo):
        if self._rules:
            for rule in self._rules:
                if not rule.matches(processDo):
                    return 0
            return 1

    def byName(self, pattern):
        if pattern:
            self._rules.append(_ProcessMatcher.PropertyMatchRule("name", pattern, re.I))
        return self


class _ProcessModifier:
    """Class represents a modifier of a process. Performs modification of process' properties by defined rules."""

    class Rule:
        """Base class for process modification rule."""
        def __init__(self):
            pass

        def apply(self, processDo):
            pass

    class ReplaceInPropertyRule(Rule):
        """
        Modifier that performs string substitution in process string proeprty.
        Will raise exception if target property is not found.
        """
        def __init__(self, targetProperty, pattern, replacement):
            _ProcessModifier.Rule.__init__(self)
            self.targetProperty = targetProperty
            self.pattern = pattern
            self.replacement = replacement

        def apply(self, processDo):
            if processDo:
                value = self._getProperty(processDo)
                if value:
                    value = re.sub(self.pattern, self.replacement, value)
                    self._setProperty(processDo, value)

        def _getProperty(self, processDo):
            return getattr(processDo, self.targetProperty)

        def _setProperty(self, processDo, value):
            setattr(processDo, self.targetProperty, value)

    def __init__(self):
        self._rules = []

    def apply(self, processDo):
        if processDo:
            for rule in self._rules:
                rule.apply(processDo)

    def replaceInCommandline(self, pattern, replacement):
        self._rules.append(_ProcessModifier.ReplaceInPropertyRule("commandline", pattern, replacement))
        return self


class _ProcessSanitizer:
    """Class sanitizes processes by defined rules - adjusts the data or prevents illegal values to enter CMDB"""

    _EXCHANGE_MODIFIER = _ProcessModifier()
    _EXCHANGE_MODIFIER.replaceInCommandline(r"\s+-pipe:\d+", "")
    _EXCHANGE_MODIFIER.replaceInCommandline(r"\s+-stopkey:[\w\\-]+", "")
    _EXCHANGE_MODIFIER.replaceInCommandline(r"\s+-resetkey:[\w\\-]+", "")
    _EXCHANGE_MODIFIER.replaceInCommandline(r"\s+-readykey:[\w\\-]+", "")
    _EXCHANGE_MODIFIER.replaceInCommandline(r"\s+-hangkey:[\w\\-]+", "")

    MATCHER_TO_MODIFIER_MAP = {
        _ProcessMatcher().byName(r"smcgui\.exe"): _ProcessModifier().replaceInCommandline(r"\s*\\\\\.\\pipe\\\w+", ""),
        _ProcessMatcher().byName(r"w3wp\.exe"): _ProcessModifier().replaceInCommandline(r"\s+-a\s+\\\\\.\\pipe\\[\w-]+", ""),
        _ProcessMatcher().byName(r"vmware-vmx(\.exe)?"): _ProcessModifier().replaceInCommandline(r"\s+-@\s+\"pipe=\\\\\.\\pipe\\.+?\"", ""),
        _ProcessMatcher().byName(r"AppleMobileDeviceHelper\.exe"): _ProcessModifier().replaceInCommandline(r"\s+--pipe\s+\\\\\.\\pipe\\[\w-]+", ""),
        _ProcessMatcher().byName(r"EdgeTransport\.exe"): _EXCHANGE_MODIFIER,
        #pop3, imap4 processes
        _ProcessMatcher().byName(r"Microsoft.Exchange\.\w+\.exe"): _EXCHANGE_MODIFIER,
        _ProcessMatcher().byName(r"CITRIX\.exe"): _ProcessModifier().replaceInCommandline(r"\s+--lmgrd_start\s+\w+", "")
    }

    def sanitize(self, processDo):
        for matcher, modifier in _ProcessSanitizer.MATCHER_TO_MODIFIER_MAP.items():
            if matcher.matches(processDo):
                modifier.apply(processDo)


def createProcessOSH(name, hostOSH, process_cmdline=None, process_pid=None,
                     process_path=None, process_parameters=None, process_user=None, process_startuptime=None,
                     procDescription=None):
    """
    Creates a new OSH that represent a process.
    @param name: the name of the process
    @type name: string
    @param hostOSH: the container node of the proccess
    @type hostOSH: ObjectStateHolderVector
    @param process_cmdline:
    @type process_cmdline: string
    @param process_path: the path of the process installation
    @type process_path: string
    @param process_parameters: process parameters
    @type process_parameters: string
    @param process_startuptime: time when process has been started in milliseconds
    @procDescription: short description of current process
    @type process_startuptime: long
    @return: a new ObjectStateHolder that represents a process
    @rtype: ObjectStateHolder
    """
    if process_cmdline or process_parameters:
        globalSettings = GeneralSettingsConfigFile.getInstance()
        clearCommandLineForProcesses = globalSettings.getPropertyStringValue('clearCommandLineForProcesses', '')
        for proc in clearCommandLineForProcesses.split(','):
            if name.lower() == proc.strip().lower():
                process_cmdline = None
                process_parameters = None

    processDo = _ProcessDo(name, process_cmdline, process_pid, process_path, process_parameters, process_user, process_startuptime, procDescription)

    _ProcessSanitizer().sanitize(processDo)

    processOSH = ObjectStateHolder('process')
    processOSH.setStringAttribute('data_name', processDo.name)
    if processDo.commandline == '':
        processDo.commandline = None
    if processDo.commandline:
        processOSH.setStringAttribute('process_cmdline', processDo.commandline.strip())
    processOSH.setContainer(hostOSH)

    if processDo.pid != None:
        processOSH.setIntegerAttribute('process_pid', int(processDo.pid))
    if processDo.path != None:
        processOSH.setStringAttribute('process_path', processDo.path)
    if processDo.parameters != None:
        processOSH.setStringAttribute('process_parameters', processDo.parameters)
    if processDo.user != None:
        processOSH.setStringAttribute('process_user', processDo.user)
    if processDo.startuptime != None and processDo.startuptime != 0:
        startupDate = Date(processDo.startuptime)
        processOSH.setDateAttribute('process_startuptime', startupDate)
    if processDo.description != None:
        processOSH.setStringAttribute('data_description', processDo.description)
    return processOSH


def createServiceURLAddressOsh(hostOSH, url):
    """
    @deprecated: use modeling.createUrlOsh method instead

    Creates a new OSH that repesents an ipserver.
    @param hostOSH: the container node of the process
    @type hostOSH: ObjectStateHolderVector
    @return: a new ObjectStateHolder that represents an ipserver
    @rtype: ObjectStateHolder
    """
    return createUrlOsh(hostOSH, url)


def createUrlOsh(hostOsh, url, type=None):  # @ReservedAssignment
    """
    Creates a new OSH that represents an url
    @param hostOsh: the container node of the url
    @type hostOsh: ObjectStateHolder
    @param url: url connect string
    @type url: string
    @return: a new ObjectStateHolder instance
    @rtype: ObjectStateHolder
    """
#    if not url:
#        raise ValueError, "Key attribute Url is missing."
#    if not hostOsh:
#        raise ValueError, "Key attribute Host is missing."

    urlOsh = ObjectStateHolder('url')
    urlOsh.setAttribute('data_name', url)
    setAdditionalKeyAttribute(urlOsh, 'url_connectstring', url)
    urlOsh.setContainer(hostOsh)
    return urlOsh


def createServiceAddressOsh(hostOSH, ip, portNumber, portType,
                               portName=None):
    """
    @deprecated:
    Use a combination of the following classes instead:

      netutils.Endpoint
      netutils.ServiceEndpointBuilder
      netutils.ServiceEndpointReporter
      netutils._PortType
      netutils.ProtocolType

    Creates a new OSH that repesents an ipserver.

    @param hostOSH: the container node of the process
    @type hostOSH: ObjectStateHolderVector
    @param portNumber: port number
    @type ip: string
    @type portNumber: int
    @param portType: port type
    @type portType: enum
    @param portName: name of the port
    @type portName: string
    @return: a new ObjectStateHolder that represents an ipserver
    @rtype: ObjectStateHolder
    """
    protocolType = None
    if portType == SERVICEADDRESS_TYPE_TCP:
        protocolType = netutils.ProtocolType.TCP_PROTOCOL
    elif portType == SERVICEADDRESS_TYPE_UDP:
        protocolType = netutils.ProtocolType.UDP_PROTOCOL
    else:
        protocolType = netutils.ProtocolType.TCP_PROTOCOL
    serviceName = None
    if portName:
        serviceName = netutils._PortType(portName)
    endpoint = netutils.Endpoint(portNumber, protocolType,
                                 ip, portType=serviceName)
    builder = netutils.ServiceEndpointBuilder()
    reporter = netutils.EndpointReporter(builder)
    ipServerOSH = reporter.reportEndpoint(endpoint, hostOSH)
    
    if portName:
        ipServerOSH.setStringAttribute('ip_service_name', portName)
        ipServerOSH.addAttributeToList('service_names', portName)
    
    return ipServerOSH


def getDatabaseDataName(dbType):
    if dbType in databaseDataNames:
        data_name = databaseDataNames[dbType]
        return data_name
    else:
        raise Exception('Unsupported DB Type: ' + dbType)


def getSupportedDbTypes():
    supportedDbType = []
    for dbType in databaseDataNames.keys():
        supportedDbType.append(dbType)
    return supportedDbType


# Mandatory parameters: dbType, dbName(SID), hostOSH
def createDatabaseOSH(dbType, dbName, dbPort, ip, hostOSH, credentialsID=None,
                      userName=None, timeout=None, dbVersion=None,
                      appVersion=None, applicationVersionNumber=None, buildNumber=None, edition=None):
    '''
    @param dbType: this is a key attribute that defines db type
    @param dbName: this is a key attribute that represented in OSH as SID
    @raise Exception: if db type is not supported
    @raise ValueError: if key attribute is missing
    '''
    if dbName is None:
        raise ValueError("Key attribute SID is missing")

    data_name = getDatabaseDataName(dbType)
    databaseCategory = 'Database'
    databaseDbType = dbType
    databaseVendor = None
    databaseName = dbName
    if dbType in ('oracle', 'mysql'):
        databaseVendor = 'oracle_corp'
    elif dbType == 'sqlserver':
        databaseDbType = "MicrosoftSQLServer"
        databaseVendor = 'microsoft_corp'
    elif dbType == 'db2_instance':
        databaseVendor = 'ibm_corp'
    elif dbType == 'sybase':
        databaseDbType = 'Sybase'
        databaseVendor = 'sybase_inc'
    elif dbType in ('maxdb', 'MAXDB'):
        databaseDbType = 'maxdb'
        databaseVendor = 'sap_ag'
    elif dbType == 'HDB':
        databaseDbType = 'sap_hdb'
        databaseVendor = 'sap_ag'

    databaseOSH = createApplicationOSH(dbType, data_name, hostOSH, databaseCategory, databaseVendor)

    if dbPort:
        try:
            databaseOSH.setAttribute('application_port', int(dbPort))
            if _CMDB_CLASS_MODEL.version() < 9:
                databaseOSH.setAttribute('database_dbport', str(dbPort))
        except:
            logger.debugException('Port is not a valid integer -', dbPort)

    databaseOSH.setAttribute('application_ip', ip)

    # Key Attribute: database_dbsid (the database instance name)
    # ----------------------------------------------------------
    setAdditionalKeyAttribute(databaseOSH, 'database_dbsid', databaseName.strip())

    databaseOSH.setAttribute('database_dbtype', databaseDbType)
    if credentialsID != None:
        databaseOSH.setAttribute('credentials_id', credentialsID)
    if userName != None:
        databaseOSH.setAttribute('application_username', userName)
    if timeout != None:
        databaseOSH.setAttribute('application_timeout', timeout)
    if dbVersion and dbVersion != 'NA':
        setDatabaseVersion(databaseOSH, dbVersion)

    if appVersion != None and appVersion != 'NA':
        databaseOSH.setAttribute('application_version', appVersion)
    if applicationVersionNumber != None:
        databaseOSH.setAttribute('application_version_number', applicationVersionNumber)
    if buildNumber != None:
        databaseOSH.setAttribute('build_number', buildNumber)
    if edition != None:
        databaseOSH.setAttribute('software_edition', edition)
    return databaseOSH


def setDatabaseVersion(dbOsh, version):
    '''ObjectStateHolder, str -> void
    @deprecated: use createDatabaseOSH instead
    '''
    if dbOsh and version:
        dbOsh.setAttribute('application_version_number', version)
        if _CMDB_CLASS_MODEL.version() < 9:
            dbOsh.setAttribute('database_dbversion', version)


def createWebServerOSH(serverType, port, configfile, hostOSH, isIHS, serverVersion=None):
    serverClass = 'application'
    data_name = serverType
    vendor = None
    webServerConfigFile = None
    if(string.find(serverType, 'IBM_HTTP') >= 0 or
       string.find(serverType, 'IBM HTTP') >= 0 or isIHS):
        if configfile != None and configfile != '' and configfile != 'N/A':
            serverClass = 'ibmhttpserver'
            webServerConfigFile = configfile
        data_name = 'IBM HTTP WebServer'
        vendor = 'ibm_corp'
    elif string.find(serverType, 'Apache') >= 0:
        if configfile != None and configfile != '' and configfile != 'N/A':
            serverClass = 'apache'
            webServerConfigFile = configfile
        data_name = 'Apache WebServer'
        vendor = 'the_apache_software_foundation'
    elif string.find(serverType, 'Netscape-Enterprise') >= 0 or string.find(serverType, "Sun-ONE-Web-Server") >= 0:
        serverClass = 'sunoneserver'
        data_name = 'Sun One WebServer'
        vendor = 'oracle_corp'
    elif string.find(serverType, 'Microsoft-IIS') >= 0:
        serverClass = 'iis'
        data_name = 'Microsoft IIS WebServer'
        vendor = 'microsoft_corp'
    elif string.find(serverType, 'Jetty') >= 0:
        data_name = 'Jetty WebServer'
    else:
        logger.debug('server type [', serverType, '] is not supported')

    webServerOSH = createApplicationOSH(serverClass, data_name, hostOSH, 'Web Server', vendor)

    setWebServerVersion(webServerOSH, serverVersion)

    if serverClass == 'application':
        if (port != None) and (_CMDB_CLASS_MODEL.version() >= 9):
            webServerOSH.setIntegerAttribute('application_port', port)
        return webServerOSH

    logger.debug('Creating WebServer OSH', serverClass, ' isIHS:', isIHS)

    if webServerConfigFile != None:
        webServerOSH.setAttribute('webserver_configfile', webServerConfigFile.lower())
        webServerOSH.setAttribute('webserver_configfile_case_sensitive', webServerConfigFile)

    if port != None:
        webServerOSH.setIntegerAttribute('application_port', port)

    return webServerOSH


def setWebServerVersion(webServerOsh, version):
    '''ObjectStateHolder, str -> void
    @deprecated: use createWebServerOSH instead
    '''
    if webServerOsh and version:
        if _CMDB_CLASS_MODEL.version() < 9:
            webServerOsh.setAttribute('webserver_version', version)
        webServerOsh.setAttribute('application_version', version)
        webServerOsh.setAttribute('application_version_number', version)


def createExchangeServer(host, applicationIp=None, credentialsId=None, exchangeVersion=None):
    exchangeServer = createApplicationOSH('ms_exchange_server', 'Microsoft Exchange Server', host, 'Mail', 'Microsoft')

    if credentialsId:
        exchangeServer.setAttribute('credentials_id', credentialsId)
    if applicationIp:
        exchangeServer.setAttribute('application_ip', applicationIp)
    if exchangeVersion:
        exchangeServer.setAttribute('application_version', exchangeVersion)

    return exchangeServer


def getProductNameByApplicationName(applicationName):
    if applicationName in applicationNameToProductNameMap:
        return applicationNameToProductNameMap[applicationName]
    else:
        raise Exception('Unknown Application: %s' % applicationName)


def setApplicationProductName(applicationOsh, applicationName=None):
    if applicationOsh:
        attributeName = 'product_name'
        applicationClass = applicationOsh.getObjectClass()
        if applicationName is None:
            applicationName = (applicationOsh.getAttributeValue('data_name')
                               or applicationOsh.getAttributeValue('discovered_product_name'))
        if applicationClass and applicationName:
            try:
                productName = getProductNameByApplicationName(applicationName)
                applicationOsh.setStringAttribute(attributeName, productName)
            except:
                # it is normal when product name is not found, thus do nothing
                pass


def getDiscoveredProductNameByType(applicationClass):
    if applicationClass in applicationTypeToDiscoveredProductNameMap:
        return applicationTypeToDiscoveredProductNameMap[applicationClass]
    return None


def setApplicationDiscoveredProductName(applicationOsh, productName=None):
    'ObjectStateHolder, str -> None'
    if applicationOsh:
        applicationType = applicationOsh.getObjectClass()
        discoveredProductName = getDiscoveredProductNameByType(applicationType) or productName
        if discoveredProductName:
            applicationOsh.setStringAttribute('discovered_product_name', discoveredProductName)


def createApplicationOSH(citName, name, hostOsh, category=None, vendor=None):
    osh = ObjectStateHolder(citName)
    if name:
        osh.setAttribute('data_name', name)
    osh.setContainer(hostOsh)

    if vendor:
        osh.setAttribute('vendor', vendor)
    if category:
        osh.setAttribute('application_category', category)

    setApplicationProductName(osh)
    setApplicationDiscoveredProductName(osh)

    return osh


def createSapInstanceOSH(servertype, serverName, address, hostOsh):
    serverOSH = createApplicationOSH(servertype, serverName, hostOsh, 'Enterprise App', 'sap_ag')
    if address is not None:
        serverOSH.setAttribute("application_ip", address)
    discoveredProductName = getDiscoveredProductNameByType(servertype)
    setApplicationProductName(serverOSH, discoveredProductName)
    setAppServerType(serverOSH)
    return serverOSH


class __J2eeServerDefinition:
    def __init__(self, className, name, vendor):
        self.className = className
        self.name = name
        self.vendor = vendor

__J2EE_SERVERS = {
    'glassfish': __J2eeServerDefinition('glassfishas', 'Glassfish AS', 'oracle_corp'),
    'jboss': __J2eeServerDefinition('jbossas', 'JBoss AS', 'jboss_group_llc'),
    'weblogic': __J2eeServerDefinition('weblogicas', 'WebLogic AS', 'bea_systems_ltd'),
    'websphere': __J2eeServerDefinition('websphereas', 'WebSphere AS', 'ibm_corp'),
    'oracleias': __J2eeServerDefinition('oracleias', 'Oracle iAS', 'oracle_corp')
}


class __AppServerTypeDefinition:
    def __init__(self, type_list):
        self.app_server_type = StringVector()
        for app_server_type in type_list:
            self.app_server_type.add(app_server_type)

__J2EE_APP_SERVER = __AppServerTypeDefinition(['j2ee'])
__SAP_ABAP_APP_SERVER = __AppServerTypeDefinition(['sap'])
__SAP_J2EE_APP_SERVER = __AppServerTypeDefinition(['j2ee, sap'])
__SIEBEL_APP_SERVER = __AppServerTypeDefinition(['siebel'])

__APP_SERVER_TYPES = {
    'j2eeserver': __AppServerTypeDefinition(['j2ee']),
    'jbossas': __AppServerTypeDefinition(['j2ee']),
    'weblogicas': __AppServerTypeDefinition(['j2ee']),
    'websphereas': __AppServerTypeDefinition(['j2ee']),
    'siebel_app_server': __AppServerTypeDefinition(['siebel']),
    'sap_r3_server': __AppServerTypeDefinition(['sap']),
    'abap_sap_central_services': __AppServerTypeDefinition(['sap']),
    'sap_j2ee_app_server': __AppServerTypeDefinition(['j2ee', 'sap']),
    'j2ee_sap_central_services': __AppServerTypeDefinition(['j2ee', 'sap'])
}


def setAppServerType(appServerOsh):
    appServerClassName = appServerOsh.getObjectClass()
    if appServerClassName in __APP_SERVER_TYPES:
        appServerType = __APP_SERVER_TYPES[appServerClassName].app_server_type
        appServerOsh.setAttribute('application_server_type', appServerType)


__APP_SYSTEM_VENDORS = {
    'exchangesystem': 'microsoft_corp',
    'tomcatcluster': 'the_apache_software_foundation',
    'vmware_cluster': 'v_mware_inc',
    'siebel_site': 'oracle_corp',
    'veritascluster': 'symantec_corp',
    'serviceguardcluster': 'hewlett_packard_co',
    'mscluster': 'microsoft_corp',
    'rac': 'oracle_corp',
    'oraclesystem': 'oracle_corp',
    'sap_system': 'sap_ag',
    'hana': 'sap_ag',
    'bobj_system': 'sap_ag'}


def createJ2eeDomain(domainName, Framework=None, vendor=None, adminServerInfo=None):
    r'''
    @types: str, Framework, str, str -> ObjectStateHolder
    @deprecated: use jee.Domain and jee.ServerTopologyBuilder.buildDomainOsh
                 method instead
    '''
    domainOSH = ObjectStateHolder('j2eedomain')
    domainOSH.setAttribute('data_name', domainName)
    setAppSystemVendor(domainOSH, vendor)
    return domainOSH


def setAppSystemVendor(appSystemOsh, vendor=None):
    if vendor is None:
        appSystemClassName = appSystemOsh.getObjectClass()
        if appSystemClassName in __APP_SYSTEM_VENDORS:
            vendor = __APP_SYSTEM_VENDORS[appSystemClassName]
    if vendor is not None:
        appSystemOsh.setStringAttribute('vendor', vendor)


def createJ2EEServer(serverType, ipddress, port=None, hostOSH=None, serverName=None, domainName=None):
    """
    VERY IMPORTANT: despite serverName has default value(None) it is very important to set its name
            since this is key attribute for j2eeserver. In case it is None we set it to 'Default Server'
    """
    if not serverType in __J2EE_SERVERS:
        errorMsg = 'Invalid j2eeserver type %s' % serverType
        raise Exception(errorMsg)

    if hostOSH == None:
        hostOSH = createHostOSH(ipddress)

    j2eeServer = __J2EE_SERVERS[serverType]
    serverCategory = 'J2EE Server'

    serverOSH = createApplicationOSH(j2eeServer.className, j2eeServer.name, hostOSH, serverCategory, j2eeServer.vendor)

    serverOSH.setAttribute('application_ip', ipddress)
    if port != None:
        serverOSH.setIntegerAttribute('application_port', int(port))
        serverOSH.setAttribute('j2eeserver_listenadress', ipddress)

    if serverName == None:
        serverName = 'Default Server'
    setAdditionalKeyAttribute(serverOSH, 'j2eeserver_servername', serverName)

    serverOSH.setAttribute('application_server_type', __J2EE_APP_SERVER.app_server_type)
    if domainName is not None:
        setJ2eeServerAdminDomain(serverOSH, domainName)
    return serverOSH


def setJ2eeServerAdminDomain(serverOSH, adminDomainName):
    serverOSH.setStringAttribute('administration_domain', adminDomainName)


def createNtcmdOSH(ip_address, credentialsId, language, codePage):
    'str, str, str, str -> ObjectStateHolder'
    ntcmdOSH = ObjectStateHolder('ntcmd')
    ntcmdOSH.setAttribute('data_name', 'ntcmd')
    ntcmdOSH.setAttribute('application_ip', ip_address)
    ntcmdOSH.setAttribute('credentials_id', credentialsId)
    ntcmdOSH.setAttribute('language', language)
    ntcmdOSH.setAttribute('codepage', codePage)
    return ntcmdOSH


def createSSHOSH(ip_address, port):
    'str, str -> ObjectStateHolder'
    return createTTYOSH('ssh', ip_address, port)


def createTelnetOSH(ip_address, port):
    'str, str -> ObjectStateHolder'
    return createTTYOSH('telnet', ip_address, port)


def createSnmpOSH(ip_address, port):
    'str, str -> ObjectStateHolder'
    return createTTYOSH('snmp', ip_address, port)


def createTTYOSH(clientType, ip_address, port):
    'str, str, str(port) -> ObjectStateHolder'
    tty_obj = ObjectStateHolder(clientType)
    tty_obj.setAttribute('application_ip', ip_address)
    tty_obj.setAttribute('data_name', clientType)
    if port:
        tty_obj.setAttribute('application_port', port)
    return tty_obj


def createWmiOSH(ip_address):
    'str -> ObjectStateHolder'
    wmiOsh = ObjectStateHolder('wmi')
    wmiOsh.setAttribute('application_ip', ip_address)
    wmiOsh.setAttribute('data_name', ClientsConsts.WMI_PROTOCOL_NAME)
    return wmiOsh


def createClusterSoftwareOSH(hostOSH, clustName, version=None, vendor=None):
    category = 'Cluster'
    if clustName == 'Microsoft Cluster SW' and not vendor:
        vendor = 'microsoft_corp'
    elif clustName == 'HP Service Guard Cluster SW' and not vendor:
        vendor = 'hewlett_packard_co'

    clusterSoftware = createApplicationOSH('failoverclustersoftware',
                                       clustName, hostOSH, category, vendor)
    if version:
        clusterSoftware.setAttribute('application_version', version)
    return clusterSoftware


def createCpuOsh(cid, hostOsh, speed=None, coreNumber=None, vendor=None, descr=None, data_name=None, logicalProcessorCount=None):
    '''Creates CPU OSH by specified cid and node container
    str, ObjectStateHolder[, long(speed MHz), int(coreNumber), str, str, str] -> ObjectStateHolder
    @param cid: cid - key attribute
    @param hostOsh: OSH instance of the container node - key attribute
    @raise ValueError: if key attribute CID is missing
    '''
    cpuOsh = ObjectStateHolder('cpu')
    if not cid:
        raise ValueError("Key attribute CID is missing")
    cpuOsh.setContainer(hostOsh)
    cpuOsh.setAttribute('cpu_cid', cid)

    if vendor:
        cpuOsh.setAttribute('cpu_vendor', vendor)
    try:
        speed = long(speed)
    except:
        logger.warn("Invalid CPU speed value: %s" % speed)
    else:
        cpuOsh.setLongAttribute("cpu_clock_speed", speed)
    if data_name:
        cpuOsh.setAttribute('data_name', ' '.join(data_name.split()))
    if coreNumber is not None:
        if str(coreNumber).isdigit() and int(coreNumber) > 0:
            cpuOsh.setIntegerAttribute('core_number', coreNumber)
        else:
            logger.warn("Invalid CPU core number value: %s" % coreNumber)
    if descr:
        cpuOsh.setAttribute('data_description', descr)
    if logicalProcessorCount:
        cpuOsh.setIntegerAttribute('logical_cpu_count', logicalProcessorCount)
    return cpuOsh

ACTIVE_DIRECTORY_DOMAIN_CIT = 'activedirectorydomain'
DOMAIN_CONTROLLER_CIT = 'domaincontroller'


def createActiveDirectoryOsh(className, dataName):
    'str, str -> ObjectStateHolder'
    adOsh = ObjectStateHolder(className)
    adOsh.setAttribute("data_name", dataName)
    return adOsh


def createOshByCmdbId(className, cmdbId):
    '''
    Creates a new OSH that represent a configuration item of type 'className'
    @param className: type of CI
    @type className: string
    @param cmdbId: CI ID in UCMDB
    @type cmdbId: CmdbObjectId
    @return: new OSH instance
    @rtype: ObjectStateHolder
    '''
    return __createOshByCmdbId(className, cmdbId)


def createOshByCmdbIdString(className, cmdbId):
    '''
    Creates a new OSH that represent a configuration item of type 'className'
    @param className: type of CI
    @type className: string
    @param ucmdbId: CI ID in UCMDB
    @type ucmdbId: string
    @return: new OSH instance
    @rtype: ObjectStateHolder
    '''
    CmdbOIDFactory = CmdbObjectID.Factory
    cmdbId = CmdbOIDFactory.restoreObjectID(cmdbId)
    return __createOshByCmdbId(className, cmdbId)


def __createOshByCmdbId(className, cmdbId):
    return ObjectStateHolder(className, cmdbId)


def getDateFromUtcString(utcDateString):
    """
    Helper function that parses a string representing a date in UTC format
    and returns date as java.util.Date object
    UTC date example: 20080517201331.843750+180
    """
    matcher = re.match('(\d{14}\.\d{3})\d{3}([+-]\d{3})$', utcDateString)
    if matcher:
        dateString = matcher.group(1)
        timezoneOffsetString = matcher.group(2)
        timezoneMillis = int(timezoneOffsetString) * 60 * 1000
        timezone = SimpleTimeZone(timezoneMillis, '')
        utcDateFormatString = 'yyyyMMddHHmmss.SSS'
        return getDateFromString(dateString, utcDateFormatString, timezone)
    else:
        raise ValueError("Value '%s' is not a valid UTC date" % utcDateString)


def getDateFromString(dateString, dateFormatString, timeZone=None, locale=Locale.ENGLISH):
    """
    Helper function that parses a date from string using specified date format, timezone and locale
    Timezone is java.util.TimeZone instance
    Locale is java.util.Locale instance, defaults to English
    Returns date as java.util.Date object
    """
    dateFormat = SimpleDateFormat(dateFormatString, locale)
    dateFormat.setLenient(0)
    if timeZone is not None:
        dateFormat.setTimeZone(timeZone)
    try:
        date = dateFormat.parse(dateString)
        return date
    except ParseException:
        raise ValueError("Error while parsing date string '%s'" % dateString)


class CmdbClassModel:
    ''' CMDB class model wrapper

    Used to request information stored in CMDB class model.
    Model information obtained in two ways:
        1. Using class model file, stored on probe (till UCMDB 9)
        2. Class model with changes (for UCMDB 9) obtained from service in Framework
    '''
    def __init__(self, framework=None):
        '''
        If framework instance is not specified - used one registered for
        current thread.
        '''
        self.__framework = framework
        self.__version = None

    def __getFramework(self):
        if not self.__framework:
            self.__framework = ScriptsExecutionManager.getFramework()
        return self.__framework

    def isKeyAttribute(self, citName, attributeName):
        '''
        Check whether specified attribute is a key attribut for specified CIT
        @return: Truth or False values
        '''
        cmdbAttr = self.getAttributeDefinition(citName, attributeName)
        return (cmdbAttr
                and cmdbAttr.getQualifierByName('ID_ATTRIBUTE') is not None)

    def getConfigFileManager(self):
        try:
            return ConfigFilesManagerImpl.getInstance()
        except:
            ConfigFilesManagerImpl.init("config", None, None)
            return ConfigFilesManagerImpl.getInstance()

    def getAttributeDefinition(self, citName, attributeName):
        '''
        Get attribute definition if such exists in CMDB model
        @rtype: com.mercury.topaz.cmdb.shared.classmodel.cmdbclass.attribute.CmdbAttribute
        @return: Definition or None
        '''
        if citName and attributeName:
            try:
                cmdbModel = self.getConfigFileManager().getCmdbClassModel()
                cmdbClass = cmdbModel.getClass(citName)
                return (cmdbClass
                        and cmdbClass.getAttributeByName(attributeName))
            except:
                pass

    def getTypeDefinition(self, name):
        r'''Get type definition by name. Type definition is domain specific
        type of attribute used in particular CIT
        @types: str -> com.mercury.topaz.cmdb.shared.classmodel.type.typedef.CmdbTypeDef'''
        cmdbModel = self.getConfigFileManager().getCmdbClassModel()
        return cmdbModel.getAllTypeDefs().getCmdbTypeDefByName(name)

    def isExistingAttribute(self, citName, attributeName):
        '''
        Check whether attribute exists in the specified CIT.

        First method checks in CMDB model using interface to probe class model file.
        Otherwise using Framework service (available since 8.04)
        @return: Truth or False value
        '''
        #check CMDB 8.* - get class model definition, located at the Probe
        if self.getAttributeDefinition(citName, attributeName):
            return 1
        #try to check CMDB v9 (according to BDM changes)
        try:
            if self.__getFramework().getClassModelServices().IsAttributeExist(citName, attributeName):
                return 1
        except:
            pass
#            logger.debugException("Failed to check attribute '%s' for class '%s'" % (attributeName, citName))

    def setAttributeIfExists(self, osh, attributeName, attributeValue,
                                attributeTypeStr=AppilogTypes.STRING_DEF):
        'osh, str, object, attribute type -> bool'
        if self.isExistingAttribute(osh.getObjectClass(), attributeName):
            if attributeTypeStr is not None:
                attrOsh = AttributeStateHolder(attributeName, attributeValue, attributeTypeStr)
            else:
                attrOsh = AttributeStateHolder(attributeName, attributeValue)
            osh.setAttribute(attrOsh)
            return 1

    def version(self):
        '-> double'
        if not self.__version:
            self.__version = logger.Version().getVersion(self.__getFramework())
        return self.__version

_CMDB_CLASS_MODEL = CmdbClassModel()
'''@deprecated methods'''
checkAttributeExists = _CMDB_CLASS_MODEL.isExistingAttribute
checkIsKeyAttribute = _CMDB_CLASS_MODEL.isKeyAttribute
__setAttributeIfExists = _CMDB_CLASS_MODEL.setAttributeIfExists
''' end '''


def setAdditionalKeyAttribute(osh, attributeName, attributeValue, attributeTypeStr=AppilogTypes.STRING_DEF):
    osh.setAttribute(attributeName, attributeValue)
    osh.setStringAttribute('name', attributeValue)


def setHostSerialNumberAttribute(hostOsh, serialNumber):
    SERIAL_EXCLUDE_PATTERN = 'Not Specified|System Serial Number|To Be Filled By O\.E\.M\.|CHASSIS SERIAL NUMBER'
    if serialNumber:
        serialNumber = serialNumber.strip()
        if (re.match(SERIAL_EXCLUDE_PATTERN, serialNumber,
                     re.IGNORECASE) or (serialNumber.lower() == 'none')):
            logger.warn('Serial number %s was ignored as invalid and set to empty value' % serialNumber)
            serialNumber = ''
        hostOsh.setAttribute('host_serialnumber', serialNumber)


def setHostManufacturerAttribute(hostOsh, manufacturer):
    hostBuilder = HostBuilder(hostOsh)
    MANUFACTURER_EXCLUDE_PATTERN = 'System manufacturer|To Be Filled By O\.E\.M\.'
    if manufacturer:
        manufacturer = manufacturer.replace('_', ' ').strip()
        if re.search(MANUFACTURER_EXCLUDE_PATTERN, manufacturer, re.IGNORECASE):
            logger.warn('Manufacturer %s was ignored as invalid and set to empty value' % manufacturer)
            manufacturer = ''
        else:
            if manufacturer == 'VMware, Inc.':
                logger.warn('Manufacturer is VMware, assuming node is virtual machine')
                hostBuilder.setAsVirtual(1)
    hostBuilder.setAttribute('host_manufacturer', manufacturer)
    hostBuilder.build()


def setHostModelAttribute(hostOsh, model):
    MODEL_EXCLUDE_PATTERN = 'None|System Name|System Product Name|To Be Filled By O\.E\.M\.'
    if model:
        model = model.replace('_', ' ').strip()
    if re.search(MODEL_EXCLUDE_PATTERN, model, re.IGNORECASE):
        logger.warn('Node model %s was ignored as invalid and set to empty value' % model)
        model = ''
    hostOsh.setAttribute('host_model', model)


def setSNMPSysObjectId(hostOsh, objectId):
    hostOsh.setAttribute('sys_object_id', objectId)


def setHostMemorySizeAttribute(hostOsh, memorySizeInMegabytes):
    hostOsh.setIntegerAttribute('memory_size', int(memorySizeInMegabytes))


def setHostSwapMemorySizeAttribute(hostOsh, swapMemorySizeInMegabytes):
    hostOsh.setIntegerAttribute('swap_memory_size', int(swapMemorySizeInMegabytes))


def setVlanIdAttribute(vlanOsh, vlanId):
    vlanOsh.setIntegerAttribute('vlan_id', int(vlanId))


def setPhysicalPortNumber(portOsh, portNumber):
    portOsh.setIntegerAttribute('port_index', int(portNumber))


def setHostDefaultGateway(hostOsh, defaultGateway):
    hostOsh.setStringAttribute('default_gateway_ip_address', defaultGateway)


def setHostBiosUuid(hostOsh, biosUuid):
    if biosUuid:
        hostOsh.setStringAttribute('host_biosuuid', biosUuid.upper())


def setHostOsFamily(hostOsh, osFamily=None, osTypeOrClassName=None):
    family = osFamily
    if family is None and osTypeOrClassName:
        family = OS_TYPE_AND_CLASS_TO_OS_FAMILY_MAP.get(osTypeOrClassName.lower())
    hostOsh.setStringAttribute('os_family', family)


def setPortRemoteNumber(portOsh, remoteNumber):
    if remoteNumber:
        remoteIndex = None
        try:
            remoteIndex = int(remoteNumber)
        except:
            pass
        else:
            portOsh.setIntegerAttribute('port_remote_index', remoteIndex)


def createDnsOsh(dnsServerIp, dnsHostOsh):
    dnsAppOsh = createApplicationOSH('dnsserver', 'DNS server', dnsHostOsh)
    dnsAppOsh.setAttribute('application_ip', dnsServerIp)
    return dnsAppOsh


def createWinsOsh(winsServerIp, winsHostOsh):
    winsAppOsh = createApplicationOSH('application', 'WINS server', winsHostOsh)
    winsAppOsh.setAttribute('application_ip', winsServerIp)
    return winsAppOsh


def createDhcpOsh(dhcpServerIp, dhcpHostOsh):
    dhcpAppOsh = createApplicationOSH('application', 'DHCP server', dhcpHostOsh)
    dhcpAppOsh.setAttribute('application_ip', dhcpServerIp)
    return dhcpAppOsh


class StaticMethod:
    'Class that represents static method'
    def __init__(self, callable_):
        self.__call__ = self.callable = callable_


class _HostBuilderStaticMethod(StaticMethod):
    def __init__(self, oshProvider):
        self.oshProvider = oshProvider

    def __call__(self, *args):
        osh = self.oshProvider(*args)
        return HostBuilder(osh)


class OshBuilder:
    def __init__(self, osh):
        self.osh = osh

    def __getattr__(self, name):
        return getattr(self.osh, name)

    def build(self):
        return self.osh


def finalizeHostOsh(hostOsh):
    '''
    @return: hostOsh or None
    @deprecated
    '''
    if hostOsh:
        return HostBuilder(hostOsh).build()


class RoleDefinition:
    class Filter:
        def isAccepted(self, osh):
            '''Defines whether OSH owns defined role
            ObjectStateHolder -> bool
            '''
            pass

    DEFAULT_FILTER = Filter()

    def __init__(self, name, alternativeBoolAttribute=None, filter=None):  # @ReservedAssignment
        '(str, str, RoleDefinition.Filter) -> RoleDefinition'
        self.name = name
        self.alternativeAttribute = alternativeBoolAttribute
        self.filter = filter or RoleDefinition.DEFAULT_FILTER

    def __repr__(self):
        return self.name


class OshClassEntryFilter(RoleDefinition.Filter):
    'Defines whether OSH class is among owners'
    def __init__(self, *appropriateClasses):
        self.appropriateClasses = appropriateClasses

    def isAccepted(self, osh):
        return osh.getObjectClass() in self.appropriateClasses


class HostRoleEnum:
    'Predefined role definitions that node may own'

    VIRTUAL = RoleDefinition("virtualized_system", 'host_isvirtual')
    ROUTER = RoleDefinition("router", 'host_isroute', OshClassEntryFilter("router", "switchrouter"))
    FIREWALL = RoleDefinition("firewall", filter=OshClassEntryFilter("firewall"))
    ATM = RoleDefinition("atm_switch", filter=OshClassEntryFilter("atmswitch"))
    LAN = RoleDefinition("lan_switch", filter=OshClassEntryFilter("switch", "fcswitch"))
    DESKTOP = RoleDefinition("desktop", 'host_isdesktop')
    SERVER = RoleDefinition("server")
    LOAD_BALANCER = RoleDefinition("load_balancer", filter=OshClassEntryFilter('lb'))
    NET_PRINTER = RoleDefinition("printer", filter=OshClassEntryFilter('netprinter'))

    def values(self):
        return (self.VIRTUAL, self.ROUTER, self.FIREWALL, self.ATM, self.LAN,
                self.DESKTOP, self.SERVER, self.LOAD_BALANCER, self.NET_PRINTER)


class HostBuilder(OshBuilder):
    ATTR_NODE_ROLE = "node_role"
    CLASS_NAME = "node"

    def __init__(self, osh):
        OshBuilder.__init__(self, osh)

    def setDescription(self, value):
        'str -> HostBuilder'
        self.osh.setStringAttribute("discovered_description", value or None)
        return self

    def determineRoles(self):
        'void -> ObjectStateHolder'
        for roleDef in HostRoleEnum().values():
            if roleDef.filter.isAccepted(self.osh):
                self.setRole(roleDef)
        return self.osh

    'methods setAs* are deprecated, use setRole method instead'
    def setAsDesktop(self, isDesktop):
        return self.setRole(HostRoleEnum.DESKTOP, isDesktop)

    def setAsServer(self, isServer):
        return self.setRole(HostRoleEnum.SERVER, isServer)

    def setAsLanSwitch(self, isSwitch):
        return self.setRole(HostRoleEnum.LAN, isSwitch)

    def setAsAtmSwitch(self, isSwitch):
        return self.setRole(HostRoleEnum.ATM, isSwitch)

    def setAsFirewall(self, isFirewall):
        return self.setRole(HostRoleEnum.FIREWALL, isFirewall)

    def setAsRouter(self, isRoute, isRoleApplied=1):
        return self.setRole(HostRoleEnum.ROUTER, isRoute, isRoleApplied)

    def setAsVirtual(self, isVirtual):
        return self.setRole(HostRoleEnum.VIRTUAL, isVirtual)

    def setOsName(self, osName):
        'str -> HostBuilder'
        if osName:
            self.osh.setAttribute('host_os', osName)
            self.osh.setAttribute('host_osaccuracy', '')

            globalSettings = GeneralSettingsConfigFile.getInstance()
            desktopOperationalSystems = globalSettings.getPropertyStringValue(
                                        CollectorsConstants.TAG_DESKTOP_OPERATING_SYSTEMS, '')
            serverOperationalSystems = globalSettings.getPropertyStringValue(
                                        CollectorsConstants.TAG_SERVER_OPERATING_SYSTEMS, '')
            if isMatchedByRegexpList(desktopOperationalSystems, osName):
                self.setRole(HostRoleEnum.DESKTOP)
            elif isMatchedByRegexpList(serverOperationalSystems, osName):
                self.setRole(HostRoleEnum.SERVER)
        return self

    def build(self):
        'void -> ObjectStateHolder'
        return self.determineRoles()

    def setRole(self, roleDef, value=True, isRoleApplied=True):
        'RoleDefinition, bool -> HostBuilder'
        if roleDef.alternativeAttribute:
            self.osh.setBoolAttribute(roleDef.alternativeAttribute, value)
        if value and isRoleApplied:
            list_ = StringVector((roleDef.name,))
            roleAttribute = AttributeStateHolder(self.ATTR_NODE_ROLE, list_)
            self.osh.addAttributeToList(roleAttribute)
        return self

'''
@see Documentation for module methods that are used as
parameter for __BuilderStaticMethod
@see: HostBuilder
'''
HostBuilder.incompleteByIp = _HostBuilderStaticMethod(createHostOSH)
HostBuilder.completeByHostKey = _HostBuilderStaticMethod(createCompleteHostOSH)
HostBuilder.fromClassName = _HostBuilderStaticMethod(ObjectStateHolder)


def createLayer2ConnectionWithLinks(macList, parentSwitch, localInterface=None):
    oshv = ObjectStateHolderVector()
    layer2Osh = ObjectStateHolder('layer2_connection')
    if macList:
        macList.sort()
        layer2Connection_id = ''
        #create local to switch topology part new style if localInterface Do is defined
        if localInterface:
            hostOsh = parentSwitch.hostOSH
            interfOsh = createInterfaceOSH(localInterface.ifMac, hostOsh, localInterface.ifDescr, localInterface.ifIndex, localInterface.ifType, localInterface.ifAdminStatus, localInterface.ifOperStatus, localInterface.ifSpeed, localInterface.ifName, localInterface.ifAlias)
            if interfOsh:
                layer2Connection_id += localInterface.ifMac + ":"
                linkOsh = createLinkOSH('member', layer2Osh, interfOsh)
                oshv.add(hostOsh)
                oshv.add(interfOsh)
                oshv.add(linkOsh)
        #create remote topology part (and local part old style if no interfaceDo defined - left for backward compatibility with NNM)
        for mac in macList:
            hostOsh = None
            if mac and mac.strip():
                macAddress = mac
                if mac.find('.') > 0:
                    macAddress = (''.join([re.findall('..$', hex(int(x)).upper())[0] for  x in mac.split('.')]).replace('X', '0'))
                    hostOsh = createCompleteHostOSH('node', macAddress)
                else:
                    hostOsh = parentSwitch.hostOSH
                if hostOsh:
                    interfOsh = createInterfaceOSH(macAddress, hostOsh)
                    if interfOsh:
                        layer2Connection_id += macAddress + ":"
                        linkOsh = createLinkOSH('member', layer2Osh, interfOsh)
                        oshv.add(hostOsh)
                        oshv.add(interfOsh)
                        oshv.add(linkOsh)
        if layer2Connection_id:
            layer2Connection_id = layer2Connection_id[:len(layer2Connection_id) - 1]
            layer2Osh.setAttribute('layer2_connection_id', str(hash(layer2Connection_id)))
            oshv.add(layer2Osh)
    return oshv


class PathExtractor:
    """
    Helper class that is used to extract the executable path of service from full command line.
    It's applicable to Windows command lines only, since we are relying on specific folder separator
    and are searching the first occurrence of '.exe' or '.bat' extension.
    Class is stateless and can be used in multiple extracts.
    When extraction fails exception is raised.
    """
    def __init__(self):
        self.__replacements = {r"/+": r"\\"}
        self.__modifiers = [
            lambda x: x.strip(),
            self.__useFirstQuotedString,
            self.__applyReplacements]
        # Note: Since due to concatanate two string with python % operation need to replace % to %% in the original string
        self.__mainPatternTemplate = r"(\w:.+?[\\/]|\%%.+?\%%.*?[\\/]|\\\\.+?[\\])%s($|\s+.+)"
        self.__fileNameAnchors = [
            r"[^\\/]+?\.(exe|bat|cmd)",
            # Below we include a known file names that appear without extension and are unique enough to
            # be used as stable anchor. You should NOT add an exception to this list if there is a chance
            # this string will appear in wrong place (e.g. folder name or parameter).
            # Example:
            # - anchor 'service'
            # - command line 'C:\Program Files\Service Folder\Service /VERBOSE'
            # will produce 'C:\Program Files\' path which is wrong
            "svchost",
            "mysqld(-nt)?",
            "TNSLSNR",
            "msiexec"
        ]
        # list of extractors
        self.__extractors = [self.__mainExtractor]

    def __useFirstQuotedString(self, inputString):
        matcher = re.match("\"(.+?)\".*", inputString)
        if matcher:
            return matcher.group(1)
        else:
            return inputString

    def __applyReplacements(self, inputString):
        for key, repl in self.__replacements.items():
            (inputString, _) = re.subn(key, repl, inputString)
        return inputString

    def __mainExtractor(self, inputString):
        for anchor in self.__fileNameAnchors:
            try:
                path = self.__extractWithAnchor(inputString, anchor)
                return path
            except ValueError:
                pass
        raise ValueError

    def __extractWithAnchor(self, inputString, anchor):
        # Note: we have to use Java regex, since jython seems to have a bug with non-greedy qualifiers,
        # i.e. wrong path is extracted
        pattern = Pattern.compile(self.__mainPatternTemplate % anchor, Pattern.CASE_INSENSITIVE)
        matcher = pattern.matcher(String(inputString))
        if matcher.matches():
            return matcher.group(1)
        else:
            raise ValueError

    def extract(self, inputString):
        modifiedInput = inputString
        for modifier in self.__modifiers:
            modifiedInput = modifier(modifiedInput)
        for extractor in self.__extractors:
            try:
                extractedValue = extractor(modifiedInput)
                return extractedValue
            except ValueError:
                pass
        raise ValueError("Failed to extract the path from '%s'" % inputString)

SERVICE_DESCRIPTION_MAX_LENGTH = 1000
SERVICE_COMMAND_LINE_MAX_LENGTH = 2500


def createServiceOSH(hostOsh, serviceName, serviceDescr, serviceCommand, serviceStartType=None, serviceOperatingStatus=None, serviceCanBePaused=None, serviceCanBeUninstalled=None, serviceStartUser=None):
    '''Creates Windows Service OSH by specified service name and node container
    @types: hostOsh, str, str, str[, str, str, str, str, str] -> serviceOsh
    '''
    serviceOsh = ObjectStateHolder('service')
    serviceOsh.setContainer(hostOsh)
    serviceOsh.setAttribute("data_name", serviceName)

    if serviceDescr != None:
        if(len(serviceDescr) > SERVICE_DESCRIPTION_MAX_LENGTH):
            serviceDescr = serviceDescr[0:SERVICE_DESCRIPTION_MAX_LENGTH - 1]
        serviceOsh.setAttribute("service_description", serviceDescr)

    if serviceCommand != None:
        serviceCmdLine = serviceCommand
        if len(serviceCmdLine) > SERVICE_COMMAND_LINE_MAX_LENGTH:
            serviceCmdLine = serviceCmdLine[0:SERVICE_COMMAND_LINE_MAX_LENGTH - 1]
        serviceOsh.setAttribute("service_commandline", serviceCmdLine)
        try:
            extractor = PathExtractor()
            servicePathToExec = extractor.extract(serviceCmdLine)
            serviceOsh.setAttribute("service_pathtoexec", servicePathToExec)
        except ValueError, ex:
            logger.debug(str(ex))
    if serviceStartType:
        serviceOsh.setAttribute("service_starttype", serviceStartType)
    if serviceOperatingStatus:
        serviceOsh.setAttribute("service_operatingstatus", serviceOperatingStatus)
    if serviceCanBePaused:
        serviceOsh.setAttribute("service_canbepaused", serviceCanBePaused)
    if serviceCanBeUninstalled:
        serviceOsh.setAttribute("service_canbeuninstalled", serviceCanBeUninstalled)
    if serviceStartUser:
        serviceOsh.setAttribute("service_startuser", serviceStartUser)
    return serviceOsh


def createVlanOsh(vlanId, parentOsh=None, portIdList=[]):
    if vlanId is None:
        return None
    vlanOsh = ObjectStateHolder('vlan')
    ucmdbVersion = logger.Version().getVersion(ScriptsExecutionManager.getFramework())

    if ucmdbVersion < 9:
        if parentOsh:
            vlanOsh.setContainer(parentOsh)
        else:
            logger.warn('No root container for Vlan %s' % vlanId)
            return None
    setVlanIdAttribute(vlanOsh, vlanId)
    if ucmdbVersion > 9.01:
        vlanUniqueId = None
        if portIdList:
            vlanUniqueId = str(hash(':'.join(portIdList.sort() or portIdList)))
        elif parentOsh:
            try:
                vlanUniqueId = str(hash(parentOsh.getAttributeValue('host_key')))
            except:
                pass
        if vlanUniqueId is None:
            vlanUniqueId = 1
        vlanOsh.setStringAttribute('vlan_unique_id', vlanUniqueId)
    return vlanOsh
