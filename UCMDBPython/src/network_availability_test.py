#coding=utf-8
import subprocess
import locale
import re
import logger
import ip_addr

from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector

from java.lang import System

def get_os_name():
    # have to get os name with java, instead of the pythonic way, as this script is run with jython
    return System.getProperty('os.name')

def get_codepage():
        '''
            Call chcp command and parse the result to get default code page.
            An example output of 'chcp':
                'Active code page: 437'
        '''
        codepage = None
        try:
            proc = subprocess.Popen(['chcp.com'], stdout = subprocess.PIPE)
            out, err = proc.communicate()
            match = re.search(r'(\d+)', out)
            if match:
                codepage = match.group()
        except Exception, e:
            pass
        return codepage

def get_default_encoding():
    return get_codepage() if get_os_name().startswith('Windows') else locale.getdefaultlocale()[1]

def decode_result(text):
    '''
        The output of ping command is encoded with OS's default encoding, it needs to be decoded
        when the encoding is not utf-8.
    '''
    result = None
    try:
        encoding = get_default_encoding()
        result = text.decode(encoding) if encoding else text
    except LookupError:
        # some encodings (eg cp936 for chinese) are missing in jython, try to decode with java
        # not using java in the first place because encodings like cp850 will fail (encoding windows-1252 is used in java)
        from java.nio.charset import Charset
        from java.lang import String
        result = String(text, Charset.defaultCharset())
    return result

def build_OSHV_result(result):
    OSHVResult = ObjectStateHolderVector()
    osh = ObjectStateHolder('network_availability_test_result')
    osh.setAttribute('result', result)
    OSHVResult.add(osh)
    return OSHVResult

def DiscoveryMain(Framework):

    ip = Framework.getDestinationAttribute('ip')
    count = Framework.getDestinationAttribute('count') or 4

    if not ip_addr.isValidIpAddress(ip):
        logger.error('SECURITY ALERT - invalid ip address \'%s\' received, someone might be exploiting your system.' % ip)
        return build_OSHV_result('\'%s\' is not a valid ip address' % ip)

    os_name = get_os_name()
    count_option = '-n' if os_name.startswith('Windows') else '-c'

    logger.debug('going to ping %s %s times' % (ip, count))

    result = ''
    try:
        count = max(min(100, int(count)), 1) # 1 <= count <= 100
        p = subprocess.Popen(['ping', count_option, str(count), str(ip)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = p.communicate()
        if p.returncode == 0 or p.returncode == 1:
            result = decode_result(stdout)
        else:
            result = decode_result(stderr)

    except Exception, e:
        result = str(e)

    logger.debug(result)

    return build_OSHV_result(result)
