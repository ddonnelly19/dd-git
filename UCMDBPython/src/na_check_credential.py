#coding=utf-8

import na_discover

from check_credential import connect, Result


def _naServerConnect(credId, ip, Framework):
    r'''@types: str, str, Framework -> Result
    @raise java.lang.Exception on connection failure
    @raise Exception on connection failure
    '''

    client = None
    try:
        client = na_discover.createJavaClient(Framework, ip, credId)

    finally:
        client and client.close()

    return Result(True)


def DiscoveryMain(framework):
    return connect(framework, checkConnectFn=_naServerConnect)
