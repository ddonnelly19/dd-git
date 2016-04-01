#coding=utf-8
# 
# iSeries Object Discovery by Eview
#
# This discovery will discover Iseries object such as jobs,files,programs,libraries,queues
#
# Created on Sept 20 , 2011
#
# @author: podom
#
# CP10 -  Initial version 
# CP10 Cup 1 Fixed CR 70111 Traceback becuase of missing module Netlinks_Services

 
import string, re, logger, modeling
import eview400_lib 
from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector
from java.util import Date
from eview400_lib import isNotNull, isNull
from com.hp.ucmdb.discovery.library.common import CollectorsParameters
from string import upper, lower
from modeling import _CMDB_CLASS_MODEL

# Variables  
global Framework
PARAM_HOST_ID = 'hostId'
PARAM_LPAR_NAME = 'LparName'





_CMD_GETJOBS = ''
_CMD_GETJOBS_QUEUE = ''
_CMD_GETOUT_QUEUE = ''
_CMD_GETOBJ_LIB =''


def concatenate(*args):
    return ''.join(map(str,args))

def appendToList(originalList, newList):
    tempList = []
    if isNull(originalList):
        originalList = tempList
    for val in newList:
        if isNotNull(val):
            originalList.append(val)
    return originalList

def appendToDictionary(originalDict, newDict):
    dict = {}
    if isNull(originalDict):
        originalDict = dict
    for (x, y) in newDict.items():
        if isNotNull(y) and not originalDict.has_key(x):
            originalDict[x] = y
    return originalDict



# EView Command Execution Methods 

def ev1_getJobs(ls):
    joblist = []
    output = ls.evApiCmd(_CMD_GETJOBS,'01')
    if output.isSuccess() and len(output.cmdResponseList) > 0:
        for line in output.cmdResponseList:
            splitline = line.split('|')
            if splitline[0] =='EOF':
                continue
            else:                
                joblist.append (splitline)
    else:
        logger.reportWarning( "Get Jobs information command failed") 
        #raise Exception, "Get Jobs Queue information command failed"   
    return joblist

def ev2_getJobsQueue(ls):
    jobqueuelist = []
    output = ls.evApiCmd(_CMD_GETJOBS_QUEUE,'07')
    if output.isSuccess() and len(output.cmdResponseList) > 0:
        for line in output.cmdResponseList:
            splitline = line.split('|')
            if splitline[0] =='EOF':
                continue
            else:                
                jobqueuelist.append (splitline) 
    else:
        logger.reportWarning( "Get Jobs Queue information command failed") 
        #raise Exception, "Get Jobs Queue information command failed"   
    return jobqueuelist

def ev3_getOutQueue(ls):
    outqueuelist = []
    output = ls.evApiCmd(_CMD_GETOUT_QUEUE,'08')
    if output.isSuccess() and len(output.cmdResponseList) > 0:
        for line in output.cmdResponseList:
            splitline = line.split('|')
            if splitline[0] =='EOF':
                continue
            else:                
                outqueuelist.append (splitline) 
    else:
        logger.reportWarning( "Get Output Queue information command failed") 
        #raise Exception, "Get Output Queue information command failed"   
    return outqueuelist

def ev4_getObjLib(ls):
    liblist = []
    output = ls.evApiCmd(_CMD_GETOBJ_LIB,'10','*ALL|*ALL|*LIB')
    if output.isSuccess() and len(output.cmdResponseList) > 0:
        for line in output.cmdResponseList:
            splitline = line.split('|')
            if splitline[0] =='EOF':
                continue
            else:                
                liblist.append (splitline)              
    else:
        logger.reportWarning( "Get Object Library information command failed") 
        #raise Exception, "Get Object Library information command failed"   
    return liblist

def ev5_getObjPgm(ls):
    pgmlist = []
    output = ls.evApiCmd(_CMD_GETOBJ_LIB,'10','*ALL|*ALL|*PGM')
    if output.isSuccess() and len(output.cmdResponseList) > 0:
        for line in output.cmdResponseList:
            splitline = line.split('|')
            if splitline[0] =='EOF':
                continue
            else:                
                pgmlist.append (splitline)              
    else:
        logger.reportWarning( "GGet Object Program information command failed") 
        #raise Exception, "Get Object Program information command failed"   
    return pgmlist


#    OSHV Creation Methods



def osh_createJobOsh(lparOsh, jobsLists):
    _vector = ObjectStateHolderVector() 
    str_name = 'name'       
    for job in jobsLists:        
        if isNotNull(job[0]):
            jobOsh = ObjectStateHolder('iseries_job') 
            jobOsh.setAttribute(str_name, job[0].strip())                     
            jobOsh.setAttribute('owner', job[1])
            jobOsh.setAttribute('job_id', int(job[2]))
            jobOsh.setAttribute('job_int_id', job[3])
            jobOsh.setAttribute('job_status', job[4])
            jobOsh.setAttribute('job_type', job[5])
            jobOsh.setContainer(lparOsh)
            _vector.add(jobOsh)
            subsystem = job[6].strip() 
            if isNotNull(subsystem):               
                subsystemOSH = ObjectStateHolder('iseriessubsystem')
                subsystemOSH.setAttribute(str_name,subsystem)
                subsystemOSH.setAttribute('discovered_product_name',subsystem)
                subsystemOSH.setContainer(lparOsh)
                _vector.add(subsystemOSH)  
                memberOsh = modeling.createLinkOSH('membership', jobOsh, subsystemOSH)         
                _vector.add(memberOsh)
    return _vector

def osh_createJobQueueOsh(lparOsh, jobsQueueLists):
    _vector = ObjectStateHolderVector() 
    str_name = 'name'       
    for queue in jobsQueueLists:        
        if isNotNull(queue[0]):
            key = concatenate(queue[0].strip(),queue[1].strip())
            jobqueueOsh = ObjectStateHolder('iseries_jobqueue') 
            jobqueueOsh.setAttribute(str_name, key)
            jobqueueOsh.setAttribute('queue_name', queue[0].strip())                     
            jobqueueOsh.setAttribute('library_name', queue[1].strip())
            jobqueueOsh.setAttribute('number_of__jobs' , int(queue[2]))
            jobqueueOsh.setAttribute('subsystem_name', queue[3].strip())
            jobqueueOsh.setAttribute('queue_status', queue[4].strip())
            jobqueueOsh.setContainer(lparOsh)
            _vector.add(jobqueueOsh)
            subsystem = queue[3].strip() 
            if isNotNull(subsystem):               
                subsystemOSH = ObjectStateHolder('iseriessubsystem')
                subsystemOSH.setAttribute(str_name,subsystem)
                subsystemOSH.setAttribute('discovered_product_name',subsystem)
                subsystemOSH.setContainer(lparOsh)
                _vector.add(subsystemOSH)  
                memberOsh = modeling.createLinkOSH('membership', jobqueueOsh, subsystemOSH)         
                _vector.add(memberOsh)
    return _vector

def osh_createOutQueueOsh(lparOsh, outQueueLists):
    _vector = ObjectStateHolderVector() 
    str_name = 'name'       
    for queue in outQueueLists:        
        if isNotNull(queue[0]):
            key = concatenate(queue[0].strip(),queue[1].strip())
            outqueueOsh = ObjectStateHolder('iseries_outqueue') 
            outqueueOsh.setAttribute(str_name, key)                     
            outqueueOsh.setAttribute('queue_name', queue[0].strip()) 
            outqueueOsh.setAttribute('library_name', queue[1].strip())
            outqueueOsh.setAttribute('number_of__files' , int(queue[2]))
            outqueueOsh.setAttribute('writer', queue[3].strip())
            outqueueOsh.setAttribute('queue_status', queue[4].strip())
            outqueueOsh.setContainer(lparOsh)
            _vector.add(outqueueOsh)
            subsystem = queue[3].strip() 
            if isNotNull(subsystem):               
                subsystemOSH = ObjectStateHolder('iseriessubsystem')
                subsystemOSH.setAttribute(str_name,subsystem)
                subsystemOSH.setAttribute('discovered_product_name',subsystem)
                subsystemOSH.setContainer(lparOsh)
                _vector.add(subsystemOSH)  
                memberOsh = modeling.createLinkOSH('membership', outqueueOsh, subsystemOSH)         
                _vector.add(memberOsh)
    return _vector


def osh_createLibOsh(lparOsh, liblists):
    _vector = ObjectStateHolderVector() 
    str_name = 'name'       
    for lib in liblists:        
        if isNotNull(lib[0]):
            key = concatenate(lib[0].strip(),lib[1].strip())
            libraryOsh = ObjectStateHolder('iseries_library') 
            libraryOsh.setAttribute(str_name, key)
            libraryOsh.setAttribute('object_name',lib[0].strip())                     
            libraryOsh.setAttribute('library_name', lib[1].strip())
            libraryOsh.setAttribute('type' , lib[2].strip())
            libraryOsh.setAttribute('program_create_time', lib[3].strip())
            libraryOsh.setAttribute('program_change_time', lib[4].strip())
            libraryOsh.setAttribute('creator', lib[5].strip())
            libraryOsh.setAttribute('owner', lib[6].strip())
            libraryOsh.setAttribute('size', lib[7].strip())
            libraryOsh.setAttribute('description', lib[9].strip())
            libraryOsh.setContainer(lparOsh)
            _vector.add(libraryOsh)
            
    return _vector

def osh_createPgmOsh(lparOsh, pgmlists):
    _vector = ObjectStateHolderVector() 
    str_name = 'name'       
    for pgm in pgmlists:        
        if isNotNull(pgm[0]):
            key = concatenate(pgm[0].strip(),pgm[1].strip())
            programOsh = ObjectStateHolder('iseries_program') 
            programOsh.setAttribute(str_name, key)
            programOsh.setAttribute('object_name',pgm[0].strip())                     
            programOsh.setAttribute('library_name', pgm[1].strip())           
            programOsh.setAttribute('type' , pgm[2].strip())
            programOsh.setAttribute('program_create_time', pgm[3].strip())
            programOsh.setAttribute('program_change_time', pgm[4].strip())
            programOsh.setAttribute('creator', pgm[5].strip())
            programOsh.setAttribute('owner', pgm[6].strip())
            programOsh.setAttribute('size', pgm[7].strip())
            programOsh.setAttribute('description', pgm[9].strip())
            programOsh.setContainer(lparOsh)
            _vector.add(programOsh)
            
    return _vector



def processiSeriesObjects(ls, lparOsh,  Framework):
    
    # Process LPAR iSeries Objects
    _vector = ObjectStateHolderVector()
    
    #===========================================================================
    # Run commands and create OSHs
    #===========================================================================

     
    ''' Discover the Active Jobs if the parameter is true'''
    createJobs = Framework.getParameter('discover_Jobs')
    if isNotNull(createJobs) and string.lower(createJobs) == 'true':
        jobslist = ev1_getJobs(ls)   
        #logger.debug (jobslist)
        _vector.addAll(osh_createJobOsh(lparOsh, jobslist))
        
    ''' Discover the  Jobs Queue and Output Queue if the parameter is true'''
    createQueue = Framework.getParameter('discover_Queue')
    if isNotNull(createQueue) and string.lower(createQueue) == 'true':
        jobsqueuelist = ev2_getJobsQueue(ls) 
        #logger.debug (jobsqueuelist)  
        _vector.addAll(osh_createJobQueueOsh(lparOsh, jobsqueuelist))
        outqueuelist = ev3_getOutQueue(ls) 
        #logger.debug (outqueuelist)  
        _vector.addAll(osh_createOutQueueOsh(lparOsh, outqueuelist))


    ''' Discover the  Object Libraries if the parameter is true'''
    createLib = Framework.getParameter('discover_Library')
    if isNotNull(createLib) and string.lower(createLib) == 'true':
        liblist = ev4_getObjLib(ls) 
        #logger.debug (liblist)  
        _vector.addAll(osh_createLibOsh(lparOsh, liblist))
 
    ''' Discover the  Object Programs if the parameter is true'''
    createPgm = Framework.getParameter('discover_Program')
    if isNotNull(createPgm) and string.lower(createPgm) == 'true':
        pgmlist = ev5_getObjPgm(ls) 
        #logger.debug (pgmlist)  
        _vector.addAll(osh_createPgmOsh(lparOsh, pgmlist))
        
       
  
    return _vector

#######
# MAIN
#######

def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()   
    
    # create LPAR node
    hostId = Framework.getDestinationAttribute(PARAM_HOST_ID)
    lparOsh = None
    if eview400_lib.isNotNull(hostId):
        lparOsh = modeling.createOshByCmdbIdString('host_node', hostId)
    
    ls = eview400_lib.EvShell(Framework)
    (iseriesObjectOSHV) = processiSeriesObjects(ls, lparOsh,  Framework)
    OSHVResult.addAll(iseriesObjectOSHV)
    
    ls.closeClient()
  
    return OSHVResult
