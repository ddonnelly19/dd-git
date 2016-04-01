'''
Created on  25-07-2006

@author:        Eduard Lekanne
@change:        Ralf Schulz, Asi Garty, Ivan Yani
'''
# coding=utf-8
import logger
import modeling
import re
import hostresource


def isHexadecimalName(dataName):
    if dataName and re.match(r"^[\dabcdefABCDEF]+$", dataName.strip()):
        logger.warn('Skipping Hex Software: ' + dataName)
        return 1


def dateConvert(datetime):
    # This subroutine is needed to convert the value returned in hrSWInstalledDate back to a understandable format
    # E.g. the output is 07:D6:07:19:0A:23:20:00 which means yyyymmddhhmmssmsec
    # This routine is sending back the date and time in the format mm/dd/yyyy hh:mm:ss
    datetime = datetime.replace(':', '')
    datetimestamp_year_int = int(datetime[0:4], 16)
    datetimestamp_month_int = int(datetime[4:6], 16)
    datetimestamp_day_int = int(datetime[6:8], 16)
    datetimestamp_hour_int = int(datetime[8:10], 16)
    datetimestamp_minutes_int = int(datetime[10:12], 16)
    datetimestamp_seconds_int = int(datetime[12:14], 16)
    datetimestamp = str(datetimestamp_month_int) + "/" + str(datetimestamp_day_int) + "/" + str(datetimestamp_year_int) + " " + str(datetimestamp_hour_int) + ":" + str(datetimestamp_minutes_int) + ":" + str(datetimestamp_seconds_int)
    return datetimestamp


def doQuerySoftware(client, OSHVResult):
    _hostObj = modeling.createHostOSH(client.getIpAddress())
    softwareList = []
    # going over: .iso.org.dod.internet.mgmt.mib-2.host.hrSWInstalled.hrSWInstalledTable.hrSWInstalledEntry
    # and getting the following:	 hrSWInstalledName                      hrSWInstalledID               hrSWInstalledType             hrSWInstalledDate
    data_name_mib = '1.3.6.1.2.1.25.6.3.1.2,1.3.6.1.2.1.25.6.3.1.3,string,1.3.6.1.2.1.25.6.3.1.3,string,1.3.6.1.2.1.25.6.3.1.4,string,1.3.6.1.2.1.25.6.3.1.5,hexa'
    resultSet = client.executeQuery(data_name_mib)  # @@CMD_PERMISION snmp protocol execution
    while resultSet.next():
        data_name = resultSet.getString(2)
        if isHexadecimalName(data_name):
            continue
        software_productid = None
        if resultSet.getString(3) != '0.0':
            software_productid = resultSet.getString(3)
        software_type = resultSet.getString(4)
        software_date = dateConvert(resultSet.getString(5))
        if data_name and ((data_name in softwareList) == 0):
            softwareList.append(data_name)
            swOSH = hostresource.doSoftware(_hostObj, data_name, software_productid, software_type, software_date)
            OSHVResult.add(swOSH)
        else:
            logger.debug('software: ', data_name, ' already reported..')
