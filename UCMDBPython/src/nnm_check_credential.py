#coding=utf-8
'''
Created on Sep 10, 2012

@author: ekondrashev
'''
import logger
from check_credential import connect, Result
import NNM_Integration_Utils

from com.hp.ucmdb.discovery.library.credentials.dictionary import\
            ProtocolDictionaryManager


def _nnmServerConnect(credId, ip, Framework):
    r'''@types: str, str, Framework -> Result
    @raise java.lang.Exception on connection failure
    @raise Exception on connection failure
    '''

    protocol = ProtocolDictionaryManager.getProtocolById(credId)

    port = protocol.getProtocolAttribute('nnmprotocol_port')
    username = protocol.getProtocolAttribute('nnmprotocol_user')
    password = protocol.getProtocolAttribute('nnmprotocol_password')
    nnmprotocol = protocol.getProtocolAttribute('nnmprotocol_protocol')

    logger.debug('NNM Check Credentials: Server: %s, Port: %s, Username: %s'\
                                                        % (ip, port, username))

    # try getting 5 node objects for the test
    api = NNM_Integration_Utils.NNMiApi(ip, port, username, password,
                                        "5", "5", nnmprotocol, Framework)
    filters = api.getFilters()
    found = 0
    ndStub = api.getStub(NNM_Integration_Utils.NnmServicesEnum().Node)
    for filter_ in filters:
        allNodesArray = ndStub.getNodes(filter_)
        allNodes = allNodesArray.getItem()
        if allNodes != None:
            found = 1
        else:
            break
    if found:
        logger.debug("Retrieved %s Node Objects" % (len(allNodes)))
    else:
        logger.debug('Did not find any Node objects')

    return Result(True)


def DiscoveryMain(framework):
    return connect(framework, checkConnectFn=_nnmServerConnect)
