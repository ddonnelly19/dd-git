#coding=utf-8
# SQLDiscoveryTutorial.py
#    Database Discovery Tutorial v1.1
#    October 24 2011 - updated April 5, 2015 for UCMDB version 10
#    Author: J. Roberts, HP CORD

# Java imports
#    data types
from java.lang import Boolean
from java.lang import String
from java.lang import Integer
from java.lang import Long
from java.lang import Double

# stack trace error handling
from java.lang import Exception as JavaException

# Universal Discovery / UCMDB imports
#     CI/attributes and links holder
from appilog.common.system.types import ObjectStateHolder
#     OSH container
from appilog.common.system.types.vectors import ObjectStateHolderVector
#    Client object
from com.mercury.topaz.cmdb.shared.model.object.id import CmdbObjectID
from com.hp.ucmdb.discovery.library.clients import ClientsConsts

#    python string-handling
import string
#     Universal Discovery error handling
import errormessages
#     logger log4j logging object
import logger

#     database client connection
import SqlServer
import SqlServerConnection
#     relationship and "graph-building" simplification object
import modeling

#
# query client and parse data 
#
def collectData(connection, hostId,sqlServer):
    # perform person query
    resultset = connection.getTable("SELECT Key_Field, external_record_id, name_field, an_int_value, a_long_value, a_normal_string, a_long_string, boolean_bitfield  FROM UDGettingStarted.dbo.Sample_Table_1 WHERE external_record_id is not NULL")
    # create the result holder for the CIs we're about to create
    OSHVResult = ObjectStateHolderVector()
    
    # loop through the person query results
    while resultset.next():
        # put the row data into variables
        myKey = resultset.getString('Key_Field').strip()
        myExternalKey = resultset.getString('external_record_id')
        myFirstName = resultset.getString('name_field')
        myLastName = resultset.getString('a_normal_string')
        myEmployeeNumber = resultset.getString('an_int_value')
        myDescription = resultset.getString('a_long_string')
        myBool = resultset.getBoolean('boolean_bitfield')

        #how to query for an unknown length string
        #if myDescription is None, then the truncation will fail unless you check first
        if(myDescription):
            #if myDescription's length is less than 250, the string will remain unchanged
            myDescription = myDescription[:250]
        
        # create a person CI
        myPersonCI = ObjectStateHolder('person')

        # ID key
        whole_key = myKey+" "+myFirstName+" "+myLastName
        
        #  assign attribute values from the variables
        myPersonCI.setAttribute('name',whole_key)
        myPersonCI.setAttribute('given_name',myFirstName)
        myPersonCI.setAttribute('surname',myLastName)
        myPersonCI.setAttribute('employee_number',myEmployeeNumber)
        myPersonCI.setAttribute('data_note',myDescription)
        myPersonCI.setAttribute('distinguished_name','OU='+myFirstName+' '+myLastName+', CN='+myExternalKey)

        # how to translate boolean
        mybt = Boolean(1)
        mybf = Boolean(0)
        
        if(myBool):
            myPersonCI.setAttribute('active_person',mybt)
        else:
            myPersonCI.setAttribute('active_person',mybf)
        
        # add the completed person CI to the OSH holder for storage until the pattern finishes and sends all the CIs to the server
        OSHVResult.add(myPersonCI)
        
        # perform location query using person data location key
        myLocations = connection.getTable("SELECT ID, dereferenced_ID, dirty_text_field, empty_field, dirty_numeric_text_field FROM UDGettingStarted.dbo.Sample_Table_2 WHERE dereferenced_id = '"+myExternalKey+"'")
        
        # if we found a row, then attempt to create a location 
        if(myLocations):
            # ensure we handle errors properly and don't bail if there is any incidental error
            try:
                # position the array cursor to the first row
                myLocations.next()
                # get the variables from the array row
                myLocationID = myLocations.getString('ID')
                myLocationName = myLocations.getString('dirty_text_field')
                # create the location CI
                myLocationCI = ObjectStateHolder('location')
                # set the location attribute values
                myLocationCI.setAttribute('name',myLocationName)
                # set location_type because it is required by the reconciliation engine
                myLocationCI.setAttribute('location_type','site')
                # add the location CI to the OSH
                OSHVResult.add(myLocationCI)
                
                # create a membership link from location to person
                myLink = modeling.createLinkOSH('membership', myLocationCI, myPersonCI)
                # add the location CI to the total result
                OSHVResult.add(myLink)

            # catch if there is no corresponding location from the person's key to lookup the location record
            except:
                logger.warn("no location found for "+myFirstName+" "+myLastName)
        
    # close result arrays for proper memory management
    resultset.close()     
    myLocations.close()
    # return the CI holder as the return value of the collectData function
    return OSHVResult
#
#  The main function of the discovery script
#
def DiscoveryMain(Framework):
    # best practice to log when your script starts and stops
    logger.info("SimpleDatabaseQuery.py started")

    # set up handle objects for the Client object
    OSHVResult = ObjectStateHolderVector()
    CmdbOIDFactory = CmdbObjectID.Factory
    
    # how to get a parameter from the discovery job
    TableName = Framework.getParameter('tablename')
    
    # hostId is the reference identifier for the sql server's host computer
    hostId= CmdbOIDFactory.restoreObjectID(Framework.getDestinationAttribute('hostId'))     
    
    # sqlServerId is the reference identifier for the sql server object 
    sqlServerId= CmdbOIDFactory.restoreObjectID(Framework.getDestinationAttribute('id'))

    try:
        # create a client object to create a connection
        dbClient = Framework.createClient()
        # establish a connection to the target
        # - use credentials, log on, use the protocol, get ready to query
        connection = SqlServerConnection.ClientSqlServerConnection(dbClient)
        # execute the collectData functiona and add all the location and person and links from
        OSHVResult.addAll(collectData(connection,hostId,sqlServerId))
        # log off the client and destroy the connection
        dbClient.close()
        # best practice to log when your script starts and stops
        # - must be done before the return statement so this line is the last line to be executed if there were no exceptions
        logger.info("SimpleDatabaseQuery.py finished")
        # this ends the script and returns the result
        return OSHVResult
    # catch any errors raised from the script - all the functionality is done inside this except's try block
    except Exception, ex:
        # ex contains the exception.  You can logger.debug(ex) for it to show up in the probe's WrapperProbe
        logger.error(ex) 
    except:
        # report on the stack trace
        exInfo = logger.prepareJythonStackTrace('')
        errormessages.resolveAndReport(exInfo, protocol, Framework)
