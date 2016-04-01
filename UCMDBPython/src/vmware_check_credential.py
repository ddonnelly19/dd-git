#coding=utf-8
'''
Created on Sep 10, 2012

@author: ekondrashev
'''
from vmware_vim_utils import UrlFromProtocolGenerator
from vmware_vim_utils import connectByUrlAndCredentialsId \
        as vmwareConnectByUrlAndCredentialsId

from check_credential import connect, Result


def _vmwareServerConnect(credId, ip, Framework):
    r'''@types: str, str, Framework -> Result
    @raise java.lang.Exception on connection failure
    @raise Exception on connection failure
    '''
    urlGenerator = UrlFromProtocolGenerator(ip, Framework)
    urlString = urlGenerator.getUrl(credId, None, None)
    client = None
    try:
        client = vmwareConnectByUrlAndCredentialsId(Framework, urlString,
                                                    credId)
    finally:
        client and client.close()

    return Result(True)


def DiscoveryMain(framework):
    return connect(framework, checkConnectFn=_vmwareServerConnect)
