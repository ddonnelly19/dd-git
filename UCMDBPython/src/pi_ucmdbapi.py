#coding=utf-8
import string
import re

import logger
import modeling

from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector
from java.util import Properties
from java.net import URL
from com.hp.ucmdb.api.client.http import HttpRequestSubmitter,HttpUcmdbServiceProvider
from com.hp.ucmdb.api.client.session import SessionProperties, CustomerSessionImpl
from com.hp.ucmdb.api.client import UcmdbServiceImpl

def connect(urlString, username, password):
    props = Properties()
    url = URL(urlString)
    urlConn = url.openConnection()
    props.load(urlConn.getInputStream())
    urlConn.disconnect();
    
    provider = HttpUcmdbServiceProvider(url, props)
    reqPath = props.get("RequestURI")
    authPath = props.get("AuthenticateURI")
    
    sessProps = SessionProperties()
    sessProps.setClientContext(provider.createClientContext("UCMDB"))
    sessProps.setRequestPath(reqPath)
    sessProps.setCustomerContext(provider.createCustomerContext(1))
    
    session = CustomerSessionImpl(sessProps)
    
    creds = provider.createCredentials(username, password)

    submitter = HttpRequestSubmitter(session, url, reqPath, authPath, creds, False)
    submitter.authenticate()
    return UcmdbServiceImpl(submitter, session, logger)       
    

def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()
    
    conn = connect("","","")
    conn = UcmdbServiceImpl(None, None, None)

    ## Write implementation to return new result CIs here...

    return OSHVResult