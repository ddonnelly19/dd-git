#coding=utf-8
from __future__ import nested_scopes

import re
import string

import logger
import modeling
import shellutils
import errormessages

from java.lang import Exception as JavaException
from java.lang import System
from java.lang import Boolean
from java.util import Calendar
from java.util import Date
from java.util import Properties
from java.text import SimpleDateFormat
from java.text import ParsePosition
from java.lang import String
from java.io import ByteArrayInputStream

from file_ver_lib import getFileLastModificationTime, getFileVersionByShell

from org.jdom.input import SAXBuilder
from com.hp.ucmdb.discovery.library.communication.downloader.cfgfiles import GeneralSettingsConfigFile
from com.hp.ucmdb.discovery.library.clients.agents import BaseAgent
from com.hp.ucmdb.discovery.library.common import CollectorsParameters

from jregex import Pattern
from jregex import REFlags
from file_system import ExtensionsFilter, createFileSystem
from file_info_discoverers import PathNotFoundException
from file_topology import FileAttrs
import file_topology
import file_system

######## FileMonitor ###################################################################################
class FileMonitor:
    def __init__(self, Framework, shellUtils, OSHVResult, extensions, hostId, binaryExtensions = ""):
        self.Framework = Framework
        self.OSHVResult    = OSHVResult
        self.shellUtils = shellUtils
        self.hostId = hostId
        self.hostOSH = None
        self.discoverUnixHiddenFiles = Boolean.parseBoolean(self.Framework.getParameter('discoverUnixHiddenFiles'))
        if self.hostId is not None:
            self.hostOSH = modeling.createOshByCmdbIdString('host', self.hostId)
        self.protocol = shellUtils.getClientType()
        self.recursive = Boolean.parseBoolean(self.Framework.getParameter('recursively'))

        self.extensions = self.__parseExtensions(extensions)
        self.binaryExtensions = self.__parseExtensions(binaryExtensions)

        #Init all I18N Strings language and codepage
        #        language = self.Framework.getDestinationAttribute('language')
        language = shellUtils.osLanguage.bundlePostfix

        langBund = None
        if (language != None) and (language != 'NA'):
            langBund = self.Framework.getEnvironmentInformation().getBundle('langFileMonitoring',language)
        else:
            langBund = self.Framework.getEnvironmentInformation().getBundle('langFileMonitoring')

        self.__fileSystem = createFileSystem(shellUtils)

        # Windows
        self.strWindowsCanotFind     = langBund.getString('windows_dir_str_canot_find')
        self.strWindowsFileNotFound     = langBund.getString('windows_dir_str_file_not_found')
        self.strWindowsDirectoryOf     = langBund.getString('windows_dir_str_directory_of') + ' '
        self.strWindowsDirectoryOfPattern = langBund.getString('windows_dir_str_directory_of_pattern')
        self.strWindowsFiles         = langBund.getString('windows_dir_str_files')
        self.strWindowsDir         = langBund.getString('windows_dir_str_dir')
        self.strWindowsAm         = langBund.getString('windows_dir_str_am')
        self.strWindowsPm         = langBund.getString('windows_dir_str_pm')
        self.regWindowsPermissions     = langBund.getString('windows_attrib_reg_permissions')
        self.strWindowsUpperP         = langBund.getString('windows_dir_str_upper_p')
        self.strWindowsLowerP         = langBund.getString('windows_dir_str_lower_p')
        # Unix
        self.strUnixNoSuchFile         = langBund.getString('unix_ls_str_no_such_file')
        self.strUnixTotal        = langBund.getString('unix_ls_str_total')

        #shold find files by full name and not by extention
        logger.debug('FileMonitor created successfully')
        self.FileSeparator = None
        if self.shellUtils.isWinOs():
            self.FileSeparator = '\\'
        else:
            self.FileSeparator = '/'

    def __parseExtensions(self, extensionString):
        extensions = []
        #Do not check for 'NA' assuming that 'NA" may be file extension itself
        if (extensionString and extensionString != ""):
            extensionsString = extensionString.replace(" ", "")
            extensions = extensionsString.split(',')
        return extensions

    def createSymLink(self, src, dest):
        """
        Creates and returns symlink to src
        using (in fallback order) linkd, mklink and junction commands.
        str, str -> str
        @param src: valid path to source folder of a symlink
        @param dest: target path of symlink
        @raise ValueError: on creation error, or if src is not valid path or if src or dest is None or empty
        @return: path to the created symlink
        """
        if not src or not dest: raise ValueError, 'Neither src or dest should not be None'

        if self.exists(src):
            self.shellUtils.execAlternateCmdsList(['linkd %s %s' % (src, dest), \
                                'mklink /d %s %s' % (src, dest)])
            if self.shellUtils.getLastCmdReturnCode() != 0:
                localFile = CollectorsParameters.BASE_PROBE_MGR_DIR + CollectorsParameters.getDiscoveryResourceFolder() + \
                    CollectorsParameters.FILE_SEPARATOR + 'junction.exe'
                self.shellUtils.copyFileIfNeeded(localFile)
                self.shellUtils.execCmd('junction %s %s /accepteula' % (dest, src))

            if self.shellUtils.getLastCmdReturnCode() != 0:
                raise ValueError, "Failed to create symbolic link"
        else:
            raise ValueError, 'src is not valid path'
        return dest

    def removeSymLink(self, path):
        """
        Removes symlink previously created by @createSymLink().
        @raise ValueError: on removing error or if path is None or empty
        str -> None
        """
        if not path: raise ValueError, 'Location should not be None'

        self.shellUtils.execCmd('rd %s' % (path))
        if self.shellUtils.getLastCmdReturnCode() != 0:
            raise ValueError, 'Unable to delete junction point'

    def getFilesByPath(self, parentOSH, paths):
        slashDel = '/'
        if self.shellUtils.isWinOs():
            slashDel = '\\'
        for path in paths:
            folder = None
            name = None
            path = self.rebuildPath(path)
            slash = string.rfind(path, slashDel)
            if slash > 0:
                folder = path[0:slash]
                name = path[slash+1:]
            else:
                logger.warn('Path ', path, ' for configuration file is not absolute path')
                continue
            self.getFiles(parentOSH, folder, name)

    def getFilesInPath(self, path, filePattern):
        locations = []
        findCommand = 'find ' + path + ' -name ' + filePattern + ' -type f'
        if self.shellUtils.isWinOs():
            if (path.find(' ') > 0) and (path[0] != '\"'):
                path = '\"' + path + '\"' + filePattern
            else:
                path = path + filePattern
            findCommand = 'dir ' + path + ' /s /b'

        findResults = self.shellUtils.execCmd(findCommand)
        if (self.shellUtils.getLastCmdReturnCode() != 0):
            return []
        templocation = findResults.split('\n')

        for i in range(0, len(templocation)):
            locationPath = templocation[i].strip()
            if locationPath.find(self.FileSeparator + filePattern) != -1:
                locations.append(locationPath)
        return locations

    def listFiles(self, folder, fileNameFilter = None):
        folder = self.rebuildPath(folder)
        if self.shellUtils.isWinOs():
            return self.listFilesWindows(folder, fileNameFilter)
        else:
            return self.listFilesUnix(folder, fileNameFilter)

    def __getWinFiles(self, folder, args, pattern = "%s", fileNameFilter = None):
        """
        Executes 'dir' command on a target folder with passed args. Then formats filename according to passed pattern, and filters
        result list by fileNameFilter to get only necessary files and dirs. If fileNameFilter is None all files are collected.
        If pattern is omitted no formatting applied.
        @param folder: parent folder
        @type cmd: string
        @param args: Command arguments to run 'dir' command with. See 'dir /?' for available options.
        @type args: string
        @param pattern: Pattern to format retrieved filenames, so if pattern="%s//" and retrieved filename = "name1",
                        the result filename would be resultFilename="name1//"
        @type pattern: string
        @param fileNameFilter: Name filter to filter retrieved filenames.
        @type fileNameFilter: filter
        @return: List of formatted filenames filtered and sorted according to passed args.
        @rtype: list
        """
        result = []
        output = self.shellUtils.execCmd('dir \"%s\" %s' % (folder, args))#@@CMD_PERMISION shell protocol execution
        logger.debug('dir command result=%s' % output)
        if output is None or output.strip() == self.strWindowsFileNotFound:
            logger.debug('failed getting folder ', folder, ' - ', output)
            return result

        for file in output.strip().split('\n'):
            if file.strip():
                fileName = pattern % file.rstrip()
                if fileName and (not fileNameFilter or fileNameFilter.accept(fileName)):
                    result.append(fileName)
        return result

    def listFilesWindows(self, folder, fileNameFilter = None):
        """
        Collects all files and folders of specified parent folder. Returns only files that are accepted by passed fileNameFilter.
        If fileNameFilter is None all files are accepted.
        @param folder: parent folder
        @type folder: string
        @param fileNameFilter: Name filter to filter retrieved filenames.
        @type fileNameFilter: filter
        @return: List of formatted filenames filtered and sorted according to passed args.
        @rtype: list
        """
        logger.debug('WINDOWS: listing files from ', folder)
        result = []
        #/B - Uses bare format (no heading information or summary).
        #/A:D - List only directories
        dir_args = '/B /A:D'
        result.extend(self.__getWinFiles(folder, dir_args, "%s\\", fileNameFilter))

        #/B - Uses bare format (no heading information or summary).
        #/A:-D - List only files
        file_args = '/B /A:-D'
        result.extend(self.__getWinFiles(folder, file_args, "%s", fileNameFilter))
        return result

    def listFilesUnix(self, folder, fileNameFilter = None):
        logger.debug('UNIX: listing files from ', folder)
        files = []
        lsFullPathCommand = '/bin/ls -FA1 %s' % folder
        lsNonColored = 'ls -FA1 --color=never %s' % folder
        lsCommand = 'ls -FA1 %s' % folder
        ls_res = self.shellUtils.execAlternateCmds(lsFullPathCommand,lsNonColored,lsCommand) #@@CMD_PERMISION shell protocol execution
        if ls_res.find(self.strUnixNoSuchFile) > 0 or self.shellUtils.getLastCmdReturnCode()!=0:
            logger.debug('failed getting folder ', folder)
            return files
        lines = ls_res.splitlines()
        for line in lines:
            line = line.strip()
            if line:
                if line[-1] not in '=>@|':
                #Skipping FIFOs(|), sockets(=), links(@) and doors (>)
                    if line.endswith('*'):
                    #stripping asterisk for files that can be executed
                        line = line [:-1]
                    if (fileNameFilter is None) or fileNameFilter.accept(line):
                        files.append(line)
        return files

    def __reportFiles(self, parentOSH, files):
        res = None
        for file in files :
            self.reportFile(parentOSH, file)
        return res

    def reportFile(self, parentOSH, file):
        if not self.isInExtensions(file.ext, self.binaryExtensions):
            f = self.__fileSystem.getFile(file.path, [FileAttrs.CONTENT, FileAttrs.VERSION])
            file.content = f.content
            file.version = f.version

        documentOSH = modeling.createConfigurationDocumentOshByFile(file, parentOSH)
        self.addResult(documentOSH)
        return documentOSH

    def _findUnixHiddenFilesRecursively(self, path):
        findCommand = 'find "%s" -type f -name ".*"' % path

        output = self.shellUtils.execCmd(findCommand)
        if self.shellUtils.getLastCmdReturnCode() == 0:
            return map(string.strip, output.strip().split('\n'))
        return []

    def _findFilesWithoutExtensionRecursively(self, path):
        findCommand = 'find "%s" -type f -not -name "*.*"' % path

        if self.shellUtils.isWinOs():
            if (path.find(' ') > 0) and (path[0] != '\"'):
                path = r'"%s"' % path
            else:
                path = path
            findCommand = 'dir /s /b /a-d %s| findstr /v /c:"."' % path

        output = self.shellUtils.execCmd(findCommand)
        if self.shellUtils.getLastCmdReturnCode() == 0:
            return map(string.strip, output.strip().split('\n'))
        return []

    def _findFilesRecursively(self, path, filePattern):
            r'''@types: str, str -> list(str)
            '''
            findCommand = 'find "%s" -type f | grep "%s"' % (path, filePattern)
            if self.shellUtils.isWinOs():
                if (path.find(' ') > 0) and (path[0] != '\"'):
                    path = r'"%s"' % path
                else:
                    path = path
                findCommand = 'dir %s /s /b | findstr %s' % (path, filePattern)

            output = self.shellUtils.execCmd(findCommand)
            if self.shellUtils.getLastCmdReturnCode() == 0:
                return map(string.strip, output.strip().split('\n'))
            return []

    def getFiles(self, parentOSH, path, fileName = None, reportFiles = 1):
        '''Obtains files by specified path. There are two scenario possible:
        1. Specified fileName is not empty or None - only target file if it is found returned.
        Path is regarded as parent folder in that case.
        2. Specified path is a path to file - only target file if it is found returned.
        3. Specified path is a path to folder - list of files containing in the path is returned.
        ObjectStateHolder, str, str - File or list(File) or None
        '''

        if parentOSH is None:
            if self.hostOSH is not None:
                parentOSH = self.hostOSH
            else:
                raise ValueError, "Neither parentOSH nor hostOSH are initialized"

        path = self.rebuildPath(path)

        try:
            requiredAttributes = [FileAttrs.NAME, FileAttrs.OWNER, FileAttrs.PERMS, \
                                  FileAttrs.SIZE, FileAttrs.PATH, \
                                  FileAttrs.CREATION_TIME, FileAttrs.VERSION,
                                  FileAttrs.LAST_MODIFICATION_TIME, FileAttrs.IS_DIRECTORY ]
            files = []
            file = None
            if fileName:
                filePath = self.__fileSystem.concat(path, fileName)
                file = self.__fileSystem.getFile(filePath, requiredAttributes)
                files.append(file)
            else:
                try:
                    file = self.__fileSystem.getFile(path, requiredAttributes)
                    if (not file.isDirectory):
                        files.append(file)
                except PathNotFoundException, ex:
                    raise ex
                except:
                    logger.debugException('Error retrieving file, perhaps it is a path')

            if (not file or file.isDirectory):
                extFilter = file_system.ExtensionsFilter(self.extensions)
                if self.recursive:
                    paths = []
                    # Looking for file candidates based on some pattern in name to make
                    # deeper discovery using file_system
                    
                    for ext in self.extensions:
                        if len(ext) == 0:
                            #get files without extension
                            paths.extend(self._findFilesWithoutExtensionRecursively(path))
                        else:
                            paths.extend(self._findFilesRecursively(path, '.%s' % ext))

                    
#                    for extension in map(lambda ext: '.%s' % ext, self.extensions):
#                        paths.extend(self._findFilesRecursively(path, extension))
                    if not self.shellUtils.isWinOs() and self.discoverUnixHiddenFiles:
                        paths.extend(self._findUnixHiddenFilesRecursively(path))
                    for path in paths:
                        if self.shellUtils.isWinOs():
                            file = self.__fileSystem.getFile(path, fileAttrs = [file_topology.FileAttrs.NAME, file_topology.FileAttrs.IS_DIRECTORY])
                            if file.isDirectory:
                                continue
                        file = self.__fileSystem.getFile(path, fileAttrs = requiredAttributes)
                        files.append(file)

                else:
                    files = self.__fileSystem.getFiles(path, self.recursive, fileAttrs = requiredAttributes)

                filterFn = None
                if not self.shellUtils.isWinOs():
                    if self.discoverUnixHiddenFiles:
                        filterFn = lambda f: f.name.startswith('.') or extFilter.accept(f)
                    else:
                        filterFn = lambda f: not f.name.startswith('.') and extFilter.accept(f)
                else:
                    filterFn = extFilter.accept
                                     
                files = filter(filterFn, files)


            if reportFiles:
                self.__reportFiles(parentOSH, filter(lambda file: file.isDirectory, files))

            return files

        except PathNotFoundException:
            logger.debug('NEW_FS: Path not found %s' % path)
        except:
            logger.debugException('NEW_FS_ERROR')
#                return self.getFilesWindows(parentOSH, path, fileName)

    def exists(self, path):
        """
        Checks whether path exists or not
        str -> bool
        @raise ValueError: if path is None or empty
        @param path: target path to be checked
        """
        if not path:
            raise ValueError, 'path should not be None or empty'
        if self.shellUtils.isWinOs():
            return self.checkWindowsPath( path )
        else:
            return self.checkUnixPath( path )

    ##########################################
    # Parameters- (path: the path to test)
    # Return Value- (int: 1/0)
    # Description: Check if the given path is valid, return 1 if it is,
    #        0 if its not.
    #########################################
    def checkPath(self, path):
        if (path[0] != '"'):
            path = '"'+path +'"'
        return self.exists(path)

    ##################################################################################
    # parameters:
    # This Method loops over all folders defined in the pattern and fetch files from them
    ##################################################################################
    def getAllFiles(self):
        FOLDERS = self.Framework.getParameter('folders')
        folders = string.split(FOLDERS, ',')
        isWinOS = self.shellUtils.isWinOs()
        files = []
        for folder in folders:
            folder = folder.strip()
            # Filter non relevant pathes for current os type
            if (not isWinOS) == (folder and folder[0] == '/'):
                files.extend(self.getFiles(None, folder))
        return files

    def rebuildPath(self, path):
        return self.shellUtils.rebuildPath(path)

    def normalizePath(self, path):
        if not path:
            raise ValueError, 'path should not be None or empty'

        if self.shellUtils.isWinOs():
            if (not path.startswith('"') and not path.endswith('"')):
                path = '"%s"' % path
            path = re.sub('/','\\\\',path)
        else:
            path = re.sub('\\\\','/',path)
        return path

    def isInExtensions(self, extension, extensions):
        if extension:
            for ext in extensions:
                if ext == '*' or ext.lower() == extension.lower():
                    return 1
        else:
            return ('*' in extensions or '' in extensions)
        return 0
    ##################################################################################
    # parameters:
    # * parentOSH - The Document/File parent ObjectStateHolder (If you set the Directory as parent, this could be None)
    # * folder    - The folder path (it can also be a file path)
    # * createDir - Set this to 1 if you want to create a Directory OSH
    #
    # This Method triggers the relavant getFilesXXX method according to the protocol type
    ##################################################################################
    def buildDocument(self, parentOSH,delimeter,directory,name,extension,lastmodifiedDate,size,owner,permissions):
        if self.isInExtensions(extension, self.extensions):
            return self.buildConfigFileByFullName(parentOSH, delimeter,directory,name,extension,lastmodifiedDate,size,owner,permissions)

    def buildConfigFileByFullName(self, parentOSH, delimeter,directory,name,extension,lastmodifiedDate,size,owner,permissions):
        f = file_topology.File(name, 0)
        fullFilePath = self.buildFullPath(directory, delimeter, name, extension)
        if not self.isInExtensions(extension, self.binaryExtensions):
            f = self.__fileSystem.getFile(fullFilePath, [FileAttrs.CONTENT, FileAttrs.VERSION])

        documentOSH = self.createDocument(parentOSH, fullFilePath, name, extension,
                                          lastmodifiedDate, size, owner, permissions, f.content, f.version);

        self.addResult(documentOSH)
        return f.content

    def buildFullPath(self, directory, delimeter, name, extension):
        fullFilePath = str(directory) + str(delimeter) + str(name)
        if extension is not None:
            theExtention = str(extension)
            if len(theExtention) > 0:
                fullFilePath = fullFilePath  + '.' + theExtention
        return fullFilePath

    def createDocument(self, parentOSH, path,
                       name, extension, lastmodifiedDate,
                       size, owner, permissions, data, fileVersion = None):
        if extension:
            name = '%s.%s' % (name, extension)

        documentOSH = modeling.createConfigurationDocumentOSH(name, path, data, parentOSH, None, lastmodifiedDate, None, fileVersion)
        if size:
            documentOSH.setLongAttribute('document_size', size)
        documentOSH.setAttribute('document_osowner', owner)
        documentOSH.setAttribute('document_permissions', permissions)
        return documentOSH

    def addResult(self, obj):
        if self.recursive:
            self.Framework.sendObject(obj)
        else:
            self.OSHVResult.add(obj)
    ###########################################################
    ## Discovery on Unix
    ###########################################################
    # parameters:
    # * parentOSH - The Document/File parent ObjectStateHolder (If you set the Directory as parent, this could be None)
    # * folder    - The folder path (it can also be a file path)
    #
    # This Method execute 'ls' command using the client, it then creates document OSH's from the results-
    # If the document extension appears in self.extensions list, it will also retrieve the document data.
    # The document is then linked to the parentOSH (if its not None), if createDir is set to 1, it will create
    # a Directory OSH and link the document to it.
    ###########################################################
    def getFilesUnix(self, parentOSH, folder, searchFileName = None):
        if parentOSH is None:
            if self.hostOSH is not None:
                parentOSH = self.hostOSH
            else:
                raise ValueError, "Neither parentOSH nor hostOSH are initialized"

        logger.debug('UNIX: getting files from ', folder)

#        ls_command = 'ls -lA ' + folder
#        ls_res = self.client.executeCmd( ls_command )
        lsFullPathCommand = '/bin/ls -lA %s' % folder
        lsNonColored = 'ls -lA --color=never %s' % folder
        lsCommand = 'ls -lA %s' % folder
        if self.recursive:
            lsFullPathCommand = '/bin/ls -R -lA %s' % folder
            lsNonColored = 'ls -R -lA --color=never %s' % folder
            lsCommand = 'ls -R -lA %s' % folder

        ls_res = self.shellUtils.execAlternateCmds(lsFullPathCommand,lsNonColored,lsCommand) #@@CMD_PERMISION shell protocol execution

        if ls_res.find(self.strUnixNoSuchFile) > 0:
            logger.debug('failed getting folder ', folder)
            return

        lines = ls_res.split('\n')

        currFolder = folder
        for line in lines:
            line = line.strip()
            if line:
                # Find out current folder in recursive search
                # for instance
                #/tmp/file_mon1:
                if line.startswith(folder) and line.endswith(':'):
                    currFolder = line[:-1]
                    continue

                if line.find(self.strUnixTotal) == 0:
                    # skip the first line
                    continue
                if line[0] == '-':
                    # this is not a directory or a link
                    tokens = line.split(' ')

                    notEmptyTokens = []
                    for token in tokens:
                        strippedToken = token.strip()
                        if strippedToken != '':
                            notEmptyTokens += [strippedToken]

                    if len(notEmptyTokens) > 7:
                        permissions = notEmptyTokens[0].strip()
                        owner = notEmptyTokens[2].strip() + ':' + notEmptyTokens[3].strip()
                        size = notEmptyTokens[4].strip()
#                        lastmodified = notEmptyTokens[5].strip() + ' ' + notEmptyTokens[6].strip() + ' ' + notEmptyTokens[7].strip()
                        fullName = notEmptyTokens[7].strip()

                        extInd = fullName.rfind('.')

                        if searchFileName != None:
                            if searchFileName != fullName:
                                continue
                            name = fullName
                            if extInd > 0:
                                name = fullName[:extInd]
                                extension = fullName[extInd+1:]
                            else:
                                extension = ''
                        elif extInd > 0:
                            name = fullName[0:extInd]
                            extension = fullName[extInd+1:]
                        else:
                            name = fullName
                            extension = ''


                        slash = string.rfind(name, '/')
                        if (slash > 0):
                            name = name[slash+1:len(name)]

                        lastmodifiedDate = getFileLastModificationTime(self.shellUtils, currFolder + self.FileSeparator + fullName)
                        logger.debug("Full Name is " + fullName)
                        if logger.isDebugEnabled():
                            logger.debug('------------------------------------------------')
                            logger.debug('lastmodified = ', str(lastmodifiedDate))
                            logger.debug('size = ', size)
                            logger.debug('owner = ', owner)
                            logger.debug('name = ', name)
                            logger.debug('extension = ', extension)
                            logger.debug('------------------------------------------------')
#                        lastmodifiedDate = self.parseUnixDate(lastmodified)

                        # in case folder already contains name and extension -
                        # remove it from folder for buildDocument correct work:
                        if folder.endswith('%s.%s' % (name, extension)):
                            folder = folder[:folder.index('%s.%s' % (name,extension))]
                        elif folder.endswith('%s.%s"' % (name, extension)):
                            folder = folder[:folder.index('%s.%s"' % (name,extension))] + '"'
                        if searchFileName != None:
                            return self.buildConfigFileByFullName(parentOSH, '/',currFolder,name,extension,lastmodifiedDate,size,owner,permissions)
                        else:
                            # JEO - Fidelity
                            # must strip filename from 'folder' argument if it was included
                            # OOTB WebSphere failing to read files because this code specified the name twice
                            # <2008-10-09 17:26:20,843> [DEBUG] [JobExecuterWorker-3:fmr_JMX_J2EE_Websphere_10.33.193.45] (SSHAgent.java:525) - doExecuteCommandSSH: result [cat: /fmtc1pmmk1/was/610/profiles/base/config/cells/fmtc1pmmk1_ND_CELL/nodes/fmtc1pmmk1_BD_NODE/servers/nodeagent/server.xml/server.xml: Not a directory
                            lastslash = string.rfind(fullName, '/')
                            if (lastslash>0):
                                folder = fullName[0:lastslash+1]
                            self.buildDocument(parentOSH, '/',currFolder,name,extension,lastmodifiedDate,size,owner,permissions)

    ##########################################
    # Parameters- (path: the path to test)
    # Return Value- (int: 1/0)
    # Description: Check if the given path is valid, return 1 if it is,
    #        0 if its not.
    #########################################
    def checkUnixPath(self,path):
        logger.debug('UNIX: Check if path is valid ', path)

        ls_command = 'ls -lA ' + path
        ls_res = self.shellUtils.execCmd( ls_command )#@@CMD_PERMISION shell protocol execution
        if (self.shellUtils.getLastCmdReturnCode() != 0):
            logger.debug('path is not valid:', path)
#        if ls_res.find(self.strUnixNoSuchFile) > 0:
#            logger.debug('path is not valid:', path)
            return 0
        return 1


    def parseUnixDate(self, lastmodified):
        # ls command displays year only if the time of last modification is greater than six months ago
        if lastmodified.find(':') > 0:
            nowDate = Date(System.currentTimeMillis())
            calendar = Calendar.getInstance()
            calendar.setTime(nowDate)
            year = calendar.get(Calendar.YEAR)
            lastYear = year - 1
            lastmodifiedDate = SimpleDateFormat('yyyy MMM d HH:mm').parse(int(year).toString() + ' ' + lastmodified,ParsePosition(0))
            if lastmodifiedDate == None:
                lastmodifiedDate = SimpleDateFormat('yyyy d. MMM HH:mm').parse(int(year).toString() + ' ' + lastmodified,ParsePosition(0))
            if (lastmodifiedDate != None) and (lastmodifiedDate.getTime() > nowDate.getTime()):
                lastmodifiedDate = SimpleDateFormat('yyyy MMM d HH:mm').parse(int(lastYear).toString() + ' ' + lastmodified,ParsePosition(0))
                if lastmodifiedDate == None:
                    lastmodifiedDate = SimpleDateFormat('yyyy d. MMM HH:mm').parse(int(lastYear).toString() + ' ' + lastmodified,ParsePosition(0))
        else:
            lastmodifiedDate = SimpleDateFormat('MMM d yyyy').parse(lastmodified,ParsePosition(0))
            if lastmodifiedDate == None:
                lastmodifiedDate = SimpleDateFormat('d. MMM yyyy').parse(lastmodified,ParsePosition(0))
        return lastmodifiedDate


    ###########################################################
    ## Discovery on Windows
    ###########################################################
    # parameters:
    # * parentOSH - The Document/File parent ObjectStateHolder (If you set the Directory as parent, this could be None)
    # * client     - The Shell client
    # * folder    - The folder path (it can also be a file path)
    #
    # This Method execute 'dir' command using the client, it then creates document OSH's from the results-
    # If the document extension appears in self.extensions list, it will also retrieve the document data.
    # The document is then linked to the parentOSH (id its not None), if createDir is set to 1, it will
    # create a Directory OSH and link to it.
    ###########################################################
    def getFilesWindows(self, parentOSH, folder, searchFileName = None):
        if parentOSH is None:
            if self.hostOSH is not None:
                parentOSH = self.hostOSH
            else:
                raise ValueError, "Neither parentOSH nor hostOSH are initialized"

        logger.debug('WINDOWS: getting files from ', folder)
        if searchFileName == None:
            logger.debug('File name is null')
        else:
            logger.debug('File name is ', searchFileName)

        dir_command = 'dir \"%s\" /Q /-C' %  folder

        if self.recursive:
            dir_command = dir_command + ' /s'

        dir_res = self.shellUtils.execCmd( dir_command )#@@CMD_PERMISION shell protocol execution
        logger.debug('dir command result=%s' %dir_res)

        if dir_res == None or dir_res.find(self.strWindowsCanotFind) >= 0:
            logger.debug('failed getting folder ', folder, ' - ', dir_res)
            return
        #dir_res = stripNtcmdHeaders(result)

        if dir_res.find(self.strWindowsDirectoryOf) == -1:
            logger.debug('failed getting folder ', folder, ' - ', dir_res)
            return

        lines = dir_res.split('\n')

        directory = None
        dirOfLen = len(self.strWindowsDirectoryOf)
        for line in lines:
            if len(line) == 0:
                continue
            if re.search(self.strWindowsFileNotFound, line):
                return
            directoryBuffer = re.search(self.strWindowsDirectoryOfPattern, line)
            if directoryBuffer:
                directory = directoryBuffer.group(1).strip()
                continue

#            dirStartIndex =line.find(self.strWindowsDirectoryOf)
#            if dirStartIndex >= 0:
#                tmp = (line[dirStartIndex+dirOfLen:])
#                directory = str(tmp[0:tmp.find('\n')].strip())
#                continue

            if (not self.recursive) and line.find(self.strWindowsFiles) >= 0:
                break

            if line.find(self.strWindowsDir) > 0:
                continue

            slashIndex = line.find('\\')
            owner = ''
            tokens = None
            if slashIndex != -1:
                tokens = line[:slashIndex].split(' ')
                if len(tokens) < 4:
                    continue
                ownerStartIndex = line.find(tokens[len(tokens) - 1])
                fileNameIndex = ownerStartIndex + 23
                owner = line[ownerStartIndex:fileNameIndex].strip()
            else:
                dotsIndex = line.find('...')
                if dotsIndex != -1:
                    tokens = line[:dotsIndex].split(' ')
                    if len(tokens) < 4:
                        continue
                    fileNameIndex = dotsIndex + len('...')
                else:
                    continue

            fullName = line[fileNameIndex:].strip()

            fileStr = String(fullName)

            idx = fileStr.lastIndexOf('.')

            if searchFileName != None:
                if fullName.lower() != searchFileName.lower():
                    continue
                name = fullName
                if idx > 0:
                    name = fullName[:idx]
                    extension = fullName[idx+1:]
                else:
                    extension = ''
            else:
                name = None
                extension = None
                try:
                    name = fileStr.substring(0,idx)
                    extension = fileStr.substring(idx+1,fileStr.length())
                except:
                    if (name == None and extension == None):
                        name = fileStr
                        extension = ''
                    else:
                        continue

            logger.debug('<---------------------------->')
            logger.debug(line)
            logger.debug('<---------------------------->')

            tokens.remove(tokens[len(tokens) - 1])
            lastmodified = None
            size = ''

            notEmptyTokens = []
            for token in tokens:
                strippedToken = token.strip()
                if strippedToken != '':
                    notEmptyTokens += [strippedToken]

            # can be three formats:
            # 12/15/2004 10:37 AM 24488 MERCURY\okogan sqlnet.log
            # 07/24/2002 02:00p 10000 BUILTIN\Administrators sfc.exe
            # 07/24/2002 02:00 10000 BUILTIN\Administrators sfc.exe

            if notEmptyTokens[2] != self.strWindowsAm and notEmptyTokens[2] != self.strWindowsPm:
#                lastmodified = notEmptyTokens[0].strip() + ' ' + notEmptyTokens[1].strip()
                size = notEmptyTokens[2].strip()
            else:
#                lastmodified = notEmptyTokens[0].strip() + ' ' + notEmptyTokens[1].strip() + ' ' + notEmptyTokens[2].strip()
                size = notEmptyTokens[3].strip()

            lastmodifiedDate = getFileLastModificationTime(self.shellUtils, str(directory) + '\\' + fullName)

            if logger.isDebugEnabled():
                logger.debug('------------------------------------------------')
                logger.debug('lastmodified = ', str(lastmodifiedDate))
                logger.debug('size = ', size)
                logger.debug('owner = ', owner)
                logger.debug('name = ', name)
                logger.debug('extension = ', extension)
                logger.debug('------------------------------------------------')

            # Get permissions (attributes)
            permissions = ''
            attrib_command = "attrib " + '"' + str(directory) + '\\' + (fullName) + '"'
            attrib_res = self.shellUtils.execCmd( attrib_command )#@@CMD_PERMISION shell protocol execution
            #attrib_res = stripNtcmdHeaders(attrib_res)
            pattern = Pattern(self.regWindowsPermissions, REFlags.DOTALL)
            match = pattern.matcher(attrib_res)
            if match.find() == 1:
                permissions = match.group(1)

#            lastmodifiedDate = self.parseWindowsDate(lastmodified)

            if searchFileName != None:
                return self.buildConfigFileByFullName(parentOSH, '\\',directory,name,extension,lastmodifiedDate,size,owner,permissions)
            else:
                self.buildDocument(parentOSH, '\\',directory,name,extension,lastmodifiedDate,size,owner,permissions)

    ##########################################
    # Parameters- (path: the path to test)
    # Return Value- (int: 1/0)
    # Description: Check if the given path is valid, return 1 if it is,
    #        0 if its not.
    #########################################
    def checkWindowsPath(self, path):
        logger.debug('WINDOWS: Check if path is valid ', path)

        file_exist_cmd = '(if EXIST %s (echo 0) else (echo 1))' % path
        res = self.shellUtils.execCmd( file_exist_cmd )#@@CMD_PERMISION shell protocol execution
        if (res == None)  or (res.strip() != '0'):
#        if dir_res == None or dir_res.find(self.strWindowsCanotFind) >= 0 or dir_res.find(self.strWindowsFileNotFound) >= 0:
            logger.debug('failed getting folder ', path, ' - result: ', res)
            return 0
        return 1

    def parseWindowsDate(self, lastmodified):
        # 12/19/2004  10:16 AM
        # some times we bring data - 18/01/2008 09.21 - we fix this here
        tokens = lastmodified.split(' ')
        tokens[1] = tokens[1][:2] + ':' + tokens[1][3:]
        lastmodified = ''
        for token in tokens:
            lastmodified = lastmodified + token + ' '

        lastmodified = lastmodified.strip()
        lastmodifiedDate = SimpleDateFormat('dd/MM/yyyy HH:mm').parse(lastmodified,ParsePosition(0))
        if lastmodifiedDate is None:
            lastmodifiedDate = SimpleDateFormat('dd.MM.yyyy HH:mm').parse(lastmodified,ParsePosition(0))

        if lastmodifiedDate is not None:
            if lastmodified.find(self.strWindowsLowerP) > 0 or lastmodified.find(self.strWindowsUpperP) > 0:
                millesecs = lastmodifiedDate.getTime()
                lastmodifiedDate = Date(millesecs + 12*60*60*1000)
        return lastmodifiedDate

    def stripNtcmdHeaders(self, data):
        pattern = Pattern('Connecting to remote service ... Ok(.*)Remote command returned 0',REFlags.DOTALL)
        match = pattern.matcher(data)
        if match.find() == 1:
            return string.strip(match.group(1))
        logger.debug('failed to get file content: ', data)
        return None

    # safe sudo cat verifies that cat command does not contain file redirection character
    # file redirection should never happen but its possible if XML files being parsed are corrupted
    # we must guarantee that MAM will never redirect sudo cat in any circumstance to avoid creating or corrupting files
    def safecat(self, path, useSudo = 0):
        return self.shellUtils.safecat(path,useSudo)

    def getContent(self, path):
        """Retrieves content of the file.
        str -> str
        @raise ValueError: if path is None or empty or path contains redirect '>' symbol
        @raise Exception: on getting content failure
        @param path: the path of a file to get content of
        @return: content of the file found at specified path
        """
        if not path:
            raise ValueError, 'path should not be None or empty'
        # search for redirect character
        m = re.search('>', path)
        if m != None:
            # constructed cat command contains redirect; log error and do not execute
            logger.warn('Illegal cat command, contains redirect: [%s]' % path)
            raise ValueError, 'Illegal cat command, contains redirect'

        #Don't think its normal
        #path = self.normalizePath(path)

        if self.shellUtils.isWinOs():
            cmd = 'type %s' % path
            self.shellUtils.lastExecutedCommand = cmd
            fileContents = self.shellUtils.execCmd(cmd)#@@CMD_PERMISION shell protocol execution
            if not self.shellUtils.getLastCmdReturnCode():
                return fileContents
            else:
                logger.warn('Failed getting contents of %s file' % path)
                raise Exception, 'Failed getting contents of file'
        else:
            cmd = 'cat %s' % path
            self.shellUtils.lastExecutedCommand = cmd
            fileContents = self.shellUtils.execCmd(cmd)#@@CMD_PERMISION shell protocol execution
            if not self.shellUtils.getLastCmdReturnCode():
                return fileContents
            else:
                logger.warn('Failed getting contents of %s file' % path)
                raise Exception, 'Failed getting contents of file'

    def deleteFolder(self, path):
        if not self.shellUtils.isWinOs(): raise NotImplemented, "deleteDirectoryViaShellCommand() is not supported on non-Windows machines"
        if not path: raise ValueError, "path is empty"
        self.shellUtils.execCmd("rmdir \"%s\" /s /q" % path)
        errorCode = self.shellUtils.getLastCmdReturnCode()
        if errorCode != 0:
            raise ValueError, "Failed deleting directory '%s'" % path

    def createFolder(self, path):
        if not self.shellUtils.isWinOs(): raise NotImplemented, "createDirectoryViaShellCommand() is not supported on non-Windows machines"
        if not path: raise ValueError, "path is empty"
        self.shellUtils.execCmd("mkdir \"%s\"" % path)
        errorCode = self.shellUtils.getLastCmdReturnCode()
        if errorCode != 0:
            raise ValueError, "Failed creating directory '%s'" % path

    def getFileContent(self, path):
        r'@types: str -> str or None'
        try:
            logger.debug('Getting content of ', path)
            return self.shellUtils.getXML(path)
        except:
            logger.debugException('Failed to get content of file ', path)
            return None

    def loadPropertiesFile(self, path):
        props = Properties()
        readmeContent = None
        try:
            readmeContent = self.shellUtils.getXML(path)
        except:
            logger.debugException('Failed to get content of file:', path)
        else:
            try:
                strContent = String(readmeContent)
                props.load(ByteArrayInputStream(strContent.getBytes()))
            except:
                logger.debugException('Failed to load properties file:', path)
        return props

class FileMonitorEx:
    def __init__(self, Framework, OSHVResult, shellUtils = None):
        self.Framework = Framework
        self.OSHVResult = OSHVResult
        self.shellUtils = shellUtils
        self.fileMonitor = None
        self.ipaddress = None
        self.hostId = None
        self.hostOSH = None
        self.FileSeparator = None
        self.connect()

    def connect(self):
        protocolName = self.Framework.getDestinationAttribute('Protocol')
        try:
            self.ipaddress = self.Framework.getDestinationAttribute('ip_address')
            self.hostId = self.Framework.getDestinationAttribute('hostId')
            self.hostOSH = modeling.createOshByCmdbIdString('host', self.hostId)

            if self.shellUtils is None:
                properties = Properties()
                codePage = self.Framework.getDestinationAttribute('codepage')
                if (codePage != None) and (codePage != 'NA'):
                    properties.put(BaseAgent.ENCODING, codePage)
                properties.setProperty('QUOTE_CMD', 'true')

                client = self.Framework.createClient(properties)
                self.shellUtils = shellutils.ShellFactory().createShell(client, protocolName)

            self.fileMonitor = FileMonitor(self.Framework, self.shellUtils, None, '', self.hostId)
            self.FileSeparator = self.fileMonitor.FileSeparator
        except JavaException, ex:
            strException = ex.getMessage()
            errormessages.resolveAndReport(strException, protocolName, self.Framework)
            self.shellUtils = None
            self.fileMonitor = None
        except:
            strException = logger.prepareJythonStackTrace('')
            errormessages.resolveAndReport(strException, protocolName, self.Framework)
            self.shellUtils = None
            self.fileMonitor = None

    def normalizeDir(self, dir):
        if (dir is not None) and (len(dir) > 0):
            if dir[len(dir) - 1] == '\"':
                dir = dir[0:len(dir) - 1]

            if dir[0] == '\"':
                dir = dir[1:]

            dir = self.allignPath(dir)

            if dir[len(dir) - 1] != self.FileSeparator:
                dir = dir + self.FileSeparator
        return dir

    def loadPropertiesFile(self, path):
        return self.fileMonitor.loadPropertiesFile(path)

    def getParentDir(self, dir):
        if dir is None:
            return None

        if len(dir) == 0:
            return None

        res = dir.replace('\\', '/')
        if res[len(res) - 1] != '/':
            res = res + '/'

        m = re.search('(.+)/.+?/$', res)
        if m is None:
            return None

        parentDir = m.group(1)
        parentDir = parentDir.replace('/', self.FileSeparator)  + self.FileSeparator
        return parentDir

    def allignPath(self, path):
        path = path.replace('/', self.FileSeparator).replace('\\', self.FileSeparator)
        if path[1] == ':':
            path = path[0:1].upper() + path[1:]
        return path

    def isDir(self, path):
        return (path is not None) and (len(path) > 0) and (path[len(path) - 1] == self.FileSeparator)

    def getFileName(self, file):
        if file is None:
            return None
        parentDir = self.getParentDir(file)
        if parentDir is None:
            return None
        return file[len(parentDir):]

    def createCF(self, container, path, fileContent = None, fileNameToBe = None):
        logger.debug('Creating configuration file ', path)
        if fileContent is None:
            fileContent = self.fileMonitor.getFileContent(path)
        if fileContent is None:
            return None
        fileName = fileNameToBe
        if fileName is None:
            fileName = self.getFileName(path)
        configFileOsh = modeling.createConfigurationDocumentOSH(fileName, path, fileContent, container, None, None, None, None, 'UTF-8')
        return configFileOsh

    def loadXmlFile(self, path, container = None, fileContent = None):
        'str, osh, str -> Document'
        saxBuilder = SAXBuilder()
        globalSettings = GeneralSettingsConfigFile.getInstance()
        loadExternalDTD = globalSettings.getPropertyBooleanValue('loadExternalDTD', 1)
        saxBuilder.setFeature("http://apache.org/xml/features/nonvalidating/load-external-dtd", loadExternalDTD)
        doc = None
        try:
            fileContent = fileContent or self.fileMonitor.getFileContent(path)
            if fileContent:
                try:
                    strContent = String(fileContent)
                    strContent = String(strContent.substring(0, strContent.lastIndexOf('>') + 1))
                    doc = saxBuilder.build(ByteArrayInputStream(strContent.getBytes()))
                    if container is not None:
                        cfOSH = self.createCF(container, path, fileContent)
                        if cfOSH is not None:
                            self.OSHVResult.add(cfOSH)
                except:
                    logger.debugException('Failed to load xml file:', path)
        except:
            logger.debugException('Failed to get content of file:', path)
        return doc
