#coding=utf-8
from java.lang import String
import re

import netutils
import modeling
from org.python.core import Py
from java.util import Date
from java.text import SimpleDateFormat
from java.util import TimeZone

def getHostKey(host, domain):
    return netutils.getHostAddress(host) + " " + domain

def getHost(hostName):
    host = netutils.getHostAddress(hostName)
    if host:
        return modeling.createHostOSH(host)
    else:
        return None

def getFileFromPath(path):
    ss = String(path)
    if(ss.indexOf("\\")==-1):
        return path
    return ss.substring(ss.lastIndexOf("\\")+1)

def getPath(path):
    ss = String(path)
    if(ss.indexOf("\\")==-1):
        return path
    return ss.substring(0,ss.lastIndexOf("\\"))

def replace(query,data):
    q = Py.newString(query)
    spliter = re.compile("[\?]{2}")
    split = spliter.split(q)
    return split[0]+data+split[1]

def replaceAll(query,data):
    q = Py.newString(query)
    spliter = re.compile("[\?]{2}")
    split = spliter.split(q)
    sb=[]
    count = len(split)
    sb.append(split[0])
    idx = 1
    while idx<count:
        sb.append(data)
        sb.append(split[idx])
        idx=idx+1
    return ''.join(sb)

def replaceAllByArray(query,data):
    q = Py.newString(query)
    spliter = re.compile("[\?]{2}")
    split = spliter.split(q)
    sb=[]
    count = len(split)
    sb.append(split[0])
    idx = 1
    while idx<count:
        sb.append(data[idx-1])
        sb.append(split[idx])
        idx=idx+1
    return ''.join(sb)

def getDisk(path,host_id):
    found_disk_drive = re.match('(\w):\\.*', path)
    if found_disk_drive:
        disk_drive = found_disk_drive.group(1).upper()
        type = modeling.UNKNOWN_STORAGE_TYPE
        return modeling.createDiskOSH(host_id, disk_drive, type, name = disk_drive)

def addFromMap(oshvMap,oshv):
    map(oshv.add, oshvMap.values())

def replaceFileSeparator(path):
    path = path.replace('\\\\','\\')
    path = path.replace('//','\\')
    path = path.replace('/','\\')
    return path.strip()

def mapToInString(objectMap,attribute):
    sb = []
    append = 'false'
    values = objectMap.values()
    for osh in values:
        ash = osh.getAttribute(attribute)
        if ash is not None:
            if append == 'true':
                sb.append(',')
            sb.append("'")
            sb.append(ash.getValue())
            sb.append("'")
            append = 'true'
    return ''.join(sb)

######################################################
def getSqlServer(name,host,sqlserverid):
    return modeling.createOshByCmdbId("sqlserver", sqlserverid)

def getSqlDateInGMT(date):
    """
        @type: long->str
        @param: date - timestamp
    """
    dateObj = Date(date)
    df = SimpleDateFormat()
    df.setTimeZone(TimeZone.getTimeZone("GMT"))
    # Default Java Date.toString() format
    df.applyPattern('EEE MMM dd HH:mm:ss zzz yyyy')
    return df.format(dateObj)
