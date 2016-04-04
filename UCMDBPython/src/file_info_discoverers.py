#coding=utf-8
from file_topology import FileAttrs, BASE_FILE_ATTRIBUTES, File,\
    PathNotFoundException, BatchDiscoveryFsException, PerlDiscoveryFsException
import re
import logger

_FILE_DELIMITER_ESC = r'^<==^>'
_FILE_ATTR_DELIMITER_ESC = r'^<=^>'
_FILE_DELIMITER = r'<==>'
_FILE_ATTR_DELIMITER = r'<=>'


class FileInfoDiscoverer:
    'Base class for file discoverers'

    def __init__(self, shell, reqAttrs=None):
        ''' Base class for file info discoverers
        'NAME' attribute is prerequisite, so it is always retrieved.
        @type shell: Shell
        @type reqAttrs: list(str)
        '''
        self._shell = shell

        if reqAttrs:
            reqAttrs = reqAttrs[:]
            #Add prerequisite NAME attribute
            if FileAttrs.NAME not in reqAttrs:
                reqAttrs.append(FileAttrs.NAME)

            # Parent attribute is parsed automatically on jython side if PATH is requested.
            # Adding PATH if it is not present and PARENT is requested.
            if FileAttrs.PARENT in reqAttrs:
                if FileAttrs.PATH not in reqAttrs:
                    reqAttrs.append(FileAttrs.PATH)

            self._reqAttrs = reqAttrs
        else:
            self._reqAttrs = BASE_FILE_ATTRIBUTES

        if FileAttrs.PARENT in self._reqAttrs:
            #No need to request as it is obtained automatically with PATH attribute
            self._reqAttrs.remove(FileAttrs.PARENT)

    def _getFileAttributeMap(self):
        '''Returns file attribute to discovery approach map.
        -> map(FileAttrs, str)
        '''
        raise NotImplementedError()

    def _getFileAttr(self, attributes, attrName):
        '''list(str), str -> str or None
        Obtains attribute index and tries to get according line from retrieved output
        @raise ValueError: if attribute index is out of retrieved output line count range
        '''
        # check for presence of attrName in required attributes
        if attrName not in self._reqAttrs:
            return None
        index = self._reqAttrs.index(attrName)
        # check for broken output
        if index < len(attributes):
            return attributes[index]
        else:
            raise ValueError('Requested attribute index greater then retrieved attributes list. Output is invalid: %s' % attributes)

    def _parseVersion(self, output):
        '''parses file version from the output
        'str -> str or None'
        '''
        pass

    def parse(self, output):
        '''Parses marker based output and builds File DO
        str -> list(File)
        @raise ValueError: If retrieved line count differs from required attribute count
        '''
        #First line is empty, skip it.
        #        <--Empty line
        #<==>
        #UsefulOutput
        fileBlocks = [fileBlock.strip() for fileBlock in output.split(_FILE_DELIMITER)[1:]]
        fileList = []
        for fileAttrs in fileBlocks:
            #Last line is empty, lets scipt it.
            #attr1value <=>
            #attr2value <=>
            #        <-- empty line
            attrs = [attr.strip() for attr in fileAttrs.split(_FILE_ATTR_DELIMITER)[:-1]]
            if len(self._reqAttrs) == len(attrs):
                fileBlock = self.parseFileAttrs(attrs)
                fileList.append(fileBlock)
            else:
                logger.warn('Obtained data is invalid, got inconsistent attribute count: %d != %d \n %s \n %s' % (len(self._reqAttrs), len(attrs), self._reqAttrs, attrs))
        return fileList


class UnixFileInfoDiscovererByPerl(FileInfoDiscoverer):
    '''Perform discovery using perl scripts which produce output in CSV.
    output is bound to file_topology.File
    File version is not discovered as approaches are platform specific(See FileInfoPerlSunOSDiscoverer and FileInfoPerlLinuxDiscoverer)
    '''
    LIST_FILES_PERL_GLOB = r'''perl -e '
use File::Basename;
$d = shift;
-d dirname($d) || print("Path not found\n") && exit 1;
$d =~ s/\s/\\$&/gs;
@files = glob($d);
$count = @files;
for $file (glob($d)){
    if (-l $file and not -e readlink($file)){
        if ($count>1){
            next;
        } else {
            print("Path not found\n") && exit 1;
        }
    }
    print "%(fileDelimiter)s\n";
    @Stat = stat $file;
    %(fileAttrs)s
}' "%(path)s"'''

    ATTRS_MAPPING = {
          FileAttrs.NAME:    r'printf("%%s %s\n", basename($file));' % _FILE_ATTR_DELIMITER,
          FileAttrs.PERMS:   r'printf("%%04o %s\n" , ($Stat[2]) & 07777);' % _FILE_ATTR_DELIMITER,
          FileAttrs.SIZE:    r'printf("%%s %s\n", $Stat[7]);' % _FILE_ATTR_DELIMITER,
          FileAttrs.PATH:    r'printf("%%s %s\n", $file);' % _FILE_ATTR_DELIMITER,
          FileAttrs.VERSION: r'printf("%s\n");' % _FILE_ATTR_DELIMITER,
          FileAttrs.CONTENT: r'open FH, $file; print while(<FH>);close FH; print("%s\n");' % _FILE_ATTR_DELIMITER,
          FileAttrs.OWNER:   r'printf("%%s %s\n", (getpwuid(@Stat[4]))[0]);' % _FILE_ATTR_DELIMITER,
          FileAttrs.CREATION_TIME:          r'printf("%%s %s\n", @Stat[10]);' % _FILE_ATTR_DELIMITER,
          FileAttrs.LAST_MODIFICATION_TIME: r'printf("%%s %s\n", @Stat[9]);' % _FILE_ATTR_DELIMITER,
          FileAttrs.IS_DIRECTORY: '$isDir=-1;if(-f $file){$isDir=0;}if(-d $file){$isDir=1;} printf("%%s %s\n", $isDir);' % _FILE_ATTR_DELIMITER,
          }

    def _getFileAttributeMap(self):
        return UnixFileInfoDiscovererByPerl.ATTRS_MAPPING

    def buildQuery(self, path):
        '''Builds command line to execute depending on requested file attributes.
        str -> str
        '''
        attrsMapping = self._getFileAttributeMap()
        attrs = []
        for attr in self._reqAttrs:
            queryPart = attrsMapping.get(attr)
            queryPart and attrs.append(queryPart)
        queryParameters = {}
        queryParameters['path'] = path
        queryParameters['fileAttrs'] = '\n'.join(attrs)
        queryParameters['fileDelimiter'] = _FILE_DELIMITER

        return UnixFileInfoDiscovererByPerl.LIST_FILES_PERL_GLOB % queryParameters

    def __list(self, path):
        ''' Make listing of files at specified path
        str -> list(File)
        @raise PerlDiscoveryFsException: script execution failed
        @raise PerlDiscoveryFsException: output is not valid
        @raise PathNotFoundException: path is not valid
        '''

        query = self.buildQuery(path)
        output = self._shell.execCmd(query)

        if not self._shell.getLastCmdReturnCode():
            try:
                return self.parse(output)
            except Exception, ex:
                logger.warnException('')
                raise PerlDiscoveryFsException(ex)
        else:
            if(output and output.strip() == 'Path not found'):
                raise PathNotFoundException(path)
            raise PerlDiscoveryFsException("An error occurred while executing perl script. Output: %s" % output)

    def parseFileAttrs(self, attributes):
        '''list(str) -> File
        Retrieves data from the attribute lines and creates File DO.
        @raise ValueError: retrieved line count differs from required attribute count or attribute value is invalid
        '''

        name = self._getFileAttr(attributes, FileAttrs.NAME)
        path = self._getFileAttr(attributes, FileAttrs.PATH)
        isDirectory = self._getFileAttr(attributes, FileAttrs.IS_DIRECTORY)
        isDirectory = isDirectory and isDirectory.isdigit() and int(isDirectory)

        perms = self._getFileAttr(attributes, FileAttrs.PERMS)
        #Cutting parent directory path
        parentPath = path and name and path.endswith(name) and path[:len(path) - (len(name) + 1)]
        size = self._getFileAttr(attributes, FileAttrs.SIZE)
        owner = self._getFileAttr(attributes, FileAttrs.OWNER)

        lastModificationTime = self._getFileAttr(attributes, FileAttrs.LAST_MODIFICATION_TIME)
        lastModificationTime = lastModificationTime and self._parseTimeInMls(lastModificationTime)

        creationTime = self._getFileAttr(attributes, FileAttrs.CREATION_TIME)
        creationTime = creationTime and self._parseTimeInMls(creationTime)

        version = self._getFileAttr(attributes, FileAttrs.VERSION)
        version = version and self._parseVersion(version)
        content = self._getFileAttr(attributes, FileAttrs.CONTENT)

        file_ = File(name, isDirectory)
        file_.path = path
        file_.parent = parentPath
        file_.owner = owner
        file_.content = content
        if version:
            file_.version = version
        size and file_.setSizeInBytes(size)
        perms and file_.setPermissionsInOctal(perms)
        lastModificationTime and file_.setLastModificationTimeInMls(lastModificationTime)
        creationTime and file_.setCreateTimeInMls(creationTime)
        return file_

    def _parseTimeInMls(self, output):
        '''Parses output for the time in milliseconds occurrence.
        str -> str or None
        '''
        matcher = re.match(r"^\s*(\d+)\s*$", output)
        if matcher:
            return matcher.group(1)

    def getFile(self, path):
        ''' Retrieves file by path.
        str - > File
        @raise PathNotFoundException: if path not valid
        @raise PerlDiscoveryFsException: script execution failure
        @raise PerlDiscoveryFsException: retrieved output is invalid
        '''
        files = self.__list(path)
        if files:
            return files[0]
        raise PerlDiscoveryFsException('Got empty collection: %s' % files)

    def getFiles(self, path):
        ''' Retrieves list of files by path
        str - > list(File)
        @raise PathNotFoundException: if path not valid
        @raise PerlDiscoveryFsException: script execution failed
                                        or retrieved output is invalid
        '''
        fileList = self.__list(r'%s/*' % path)
        fileList.extend(filter(lambda file_: file_.name not in ('.', '..'),
                                self.__list(r'%s/.*' % path)))
        return fileList

    def exists(self, path):
        '''Checks whether path exists or not.
        str -> bool
        '''
        self._shell.execCmd(r'''perl -e 'if(!-f $ARGV[0] and !-d $ARGV[0] and !-l $ARGV[0]){exit(1)}' "%s"''' % path)
        if (self._shell.getLastCmdReturnCode()):
            self._shell.execCmd(r'''perl -e 'if(!-f \"%s\" and !-d \"%s\" and !-l \"%s\"){exit(1)}' ''' % (path, path, path))
        return not self._shell.getLastCmdReturnCode()


class SunOSFileInfoDiscovererByPerl(UnixFileInfoDiscovererByPerl):
    'Perl based file info discoverer defining special case for file version attribute.'

    ATTRS_MAPPING = UnixFileInfoDiscovererByPerl.ATTRS_MAPPING.copy()
    ATTRS_MAPPING[FileAttrs.VERSION] = r'''`pkgchk -l -p "$file"`=~ m/.*Referenced by the following packages:\s*\n\s*([\w.-]+)/;
    printf("%%s%s\n", `pkginfo -l $1 | grep -i VERSION`);''' % _FILE_ATTR_DELIMITER

    def _getFileAttributeMap(self):
        '-> map(str, str)'
        return SunOSFileInfoDiscovererByPerl.ATTRS_MAPPING

    def _parseVersion(self, output):
        'str -> str or None'
        fileVersion = re.search('.*VERSION:\s+([\w.-]+)', output)
        if fileVersion:
            return fileVersion.group(1).strip()


class LinuxFileInfoDiscovererByPerl(UnixFileInfoDiscovererByPerl):
    'Perl based file info discoverer defining special case for file version attribute.'
    ATTRS_MAPPING = UnixFileInfoDiscovererByPerl.ATTRS_MAPPING.copy()
    ATTRS_MAPPING[FileAttrs.VERSION] = r'''printf("%%s%s\n", `rpm -qf $file --qf "VERSION:%%{VERSION}\n" 2> /dev/null| grep VERSION`);''' % _FILE_ATTR_DELIMITER

    def _getFileAttributeMap(self):
        '-> map(str, str)'
        return LinuxFileInfoDiscovererByPerl.ATTRS_MAPPING

    def _parseVersion(self, output):
        'str -> str or None'
        fileVersion = re.search('\s*([\d.-]+).*', output)
        if fileVersion:
            return fileVersion.group(1).strip()


def _unformat(formattedText):
    lines = filter(lambda line: not line.strip().startswith('#'),
                   formattedText.splitlines())
    return reduce(lambda cmdline, line: ''.join((cmdline, ' ', line.strip())),
                  lines,
                  '')


class WindowsFileInfoDiscovererByBatch(FileInfoDiscoverer):
    '''Batch based file info discoverer'''

    LIST_FILES_BATCH = 'cmd /V:ON /c "@echo off & (for %(isRecursive)s %(listDirectoriesOnly)s %%F in (%(path)s) do echo %(fileDelimiter)s %(fileAttrs)s ) &echo on"'

    FILE_ATTRS_MAPPING = {
      FileAttrs.NAME:    '& echo %%~nxF%s ' % _FILE_ATTR_DELIMITER_ESC,
      FileAttrs.PERMS:   '& echo %%~aF%s ' % _FILE_ATTR_DELIMITER_ESC,
      FileAttrs.SIZE:    '& echo %%~zF%s ' % _FILE_ATTR_DELIMITER_ESC,
      FileAttrs.PATH:    '& echo %%~fF%s ' % _FILE_ATTR_DELIMITER_ESC,
      FileAttrs.CONTENT: '& type %%~sF &echo %s' % _FILE_ATTR_DELIMITER_ESC,
      FileAttrs.OWNER:   _unformat(r'''
      & (if exist %%~sF\NUL
          # if directory
          # take list of files of parent directory
          # and filter them by name
          # iterate over filtered candidates
          # Iteration needed to split candidate line onto tokens and take
          # 3rd and rest for owner information
          (for /f "Tokens=3*" %%i in ('dir /q /a /-c "%%~fF\.." ^| findstr /c:"%%~nxF"')
              do echo %%~j%s )
        ELSE
          # the same action steps but against file
          (for /f "Tokens=3*" %%i in ('dir /q /a /-c "%%~fF" ^| findstr /c:"%%~nxF"')
              do echo %%~j%s ))''') % (_FILE_ATTR_DELIMITER_ESC,
                                       _FILE_ATTR_DELIMITER_ESC),
      FileAttrs.CREATION_TIME:          '''&set FULL_PATH=%%~fF& wmic datafile where "name = '!FULL_PATH:\=\\\\!'" get InstallDate /format:list < %%SystemRoot%%\win.ini &echo %s''' % _FILE_ATTR_DELIMITER_ESC,
      FileAttrs.LAST_MODIFICATION_TIME: '''&set FULL_PATH=%%~fF& wmic datafile where "name = '!FULL_PATH:\=\\\\!'" get LastModified /format:list < %%SystemRoot%%\win.ini &echo %s''' % _FILE_ATTR_DELIMITER_ESC,
      FileAttrs.VERSION:                '''&set FULL_PATH=%%~fF& wmic datafile where "name = '!FULL_PATH:\=\\\\!'" get version /format:list < %%SystemRoot%%\win.ini &echo %s''' % _FILE_ATTR_DELIMITER_ESC,
      FileAttrs.IS_DIRECTORY: '& (if exist %%~sF\NUL (echo 1) ELSE (echo 0))&echo %s' % _FILE_ATTR_DELIMITER_ESC,
      }

    DIRECTORY_ATTRS_MAPPING = FILE_ATTRS_MAPPING.copy()
    DIRECTORY_ATTRS_MAPPING[FileAttrs.OWNER] = '& echo %s ' % _FILE_ATTR_DELIMITER_ESC

    def __init__(self, shell, reqAttrs=None):
        '''Batch script based file info retriever.
        Current implementation uses for loop instruction to retrieve base file attributes.
        Exceptions are 'OWNER'(dir based), 'IS_DIRECTORY'(if exists), 'CREATION_TIME'(wmic), 'LAST_MODIFICATION_TIME'(wmic), 'VERSION'(wmic) attributes.
        Remember that 'SIZE' and 'NAME' attributes are required if you want to retrieve 'OWNER' attribute.
        @param reqAttrs: list of file attributes to retrieve. If None then all file attributes is requested.
        '''
        additionalAttrs = []

        # If OWNER is present, we should add size to parse correct owner value
        if reqAttrs and FileAttrs.OWNER in reqAttrs and FileAttrs.SIZE not in reqAttrs:
            additionalAttrs.append(FileAttrs.SIZE)

        FileInfoDiscoverer.__init__(self, shell, reqAttrs and (reqAttrs + additionalAttrs))

    def _getFileAttributeMap(self, listDirectoriesOnly=0):
        return (listDirectoriesOnly and WindowsFileInfoDiscovererByBatch.DIRECTORY_ATTRS_MAPPING
                or WindowsFileInfoDiscovererByBatch.FILE_ATTRS_MAPPING)

    def buildQuery(self, path, isRecursive=0, listDirectoriesOnly=0):
        '''
        str, bool -> str
        '''
        attrsMapping = self._getFileAttributeMap(listDirectoriesOnly)
        attrs = []
        for attr in self._reqAttrs:
            queryPart = attrsMapping.get(attr)
            queryPart and attrs.append(queryPart)
        queryParameters = {}
        queryParameters['isRecursive'] = isRecursive and r'/R' or ''
        queryParameters['listDirectoriesOnly'] = listDirectoriesOnly and r'/D' or ''
        queryParameters['path'] = path
        queryParameters['fileAttrs'] = ''.join(attrs)
        queryParameters['fileDelimiter'] = _FILE_DELIMITER_ESC

        return WindowsFileInfoDiscovererByBatch.LIST_FILES_BATCH % queryParameters

    def parseFileAttrs(self, attributes):
        '''list(str) -> File
        Retrieves data from the attribute lines and creates File DO.
        @raise ValueError: If retrieved line count differs from required attribute count
        '''

        name = self._getFileAttr(attributes, FileAttrs.NAME)
        path = self._getFileAttr(attributes, FileAttrs.PATH)
        isDirectory = self._getFileAttr(attributes, FileAttrs.IS_DIRECTORY)
        isDirectory = isDirectory and isDirectory.isdigit() and int(isDirectory)

        perms = self._getFileAttr(attributes, FileAttrs.PERMS)
        isDirectory = perms and perms[0] == 'd' or isDirectory

        #Cutting parent directory path
        parentPath = path and name and path.endswith(name) and path[:len(path) - (len(name) + 1)]

        file_ = File(name, isDirectory)
        file_.setPermissionsInText(perms)
        file_.path = path
        file_.parent = parentPath
        size = self._getFileAttr(attributes, FileAttrs.SIZE)

        owner = self._getFileAttr(attributes, FileAttrs.OWNER)
        if owner:
            owner = name and owner[:len(owner) - len(name)].strip() or owner
            owner = size and owner[owner.find(size) + len(size):].strip() or owner

        lastModificationTime = self._getFileAttr(attributes, FileAttrs.LAST_MODIFICATION_TIME)
        lastModificationTime = lastModificationTime and self._parseUTCTime(lastModificationTime)

        creationTime = self._getFileAttr(attributes, FileAttrs.CREATION_TIME)
        creationTime = creationTime and self._parseUTCTime(creationTime)

        version = self._getFileAttr(attributes, FileAttrs.VERSION)
        version = version and self._parseVersion(version)

        content = self._getFileAttr(attributes, FileAttrs.CONTENT)

        file_.owner = owner
        size and file_.setSizeInBytes(size)
        file_.version = version
        file_.content = content
        lastModificationTime and file_.setLastModificationTimeInUTC(lastModificationTime)
        creationTime and file_.setCreateTimeInUTC(creationTime)
        return file_

    def _parseVersion(self, output):
        'str -> str or None'
        matcher = re.search(r'([\d., ]+)', output)
        if matcher:
            return matcher.group(1).strip()

    def _parseUTCTime(self, output):
        'str -> str or None'
        UTC_DATE_LENGTH = 25
        matcher = re.search(r'([\d.+-]{%s})' % UTC_DATE_LENGTH, output)
        if matcher:
            return matcher.group(1).strip()

    def __list(self, path, listDirectoriesOnly=0):
        '''Shell, str, str - > list(File)
        Executes target script and parses retrieved csv output,
        converting it to File DO.
        @raise BatchDiscoveryFsException: on script execution failure
                                        or if retrieved csv is invalid
        '''
        batchQuery = self.buildQuery(path,
                                    listDirectoriesOnly=listDirectoriesOnly)
        output = self._shell.execCmd(batchQuery)
        if not self._shell.getLastCmdReturnCode():
            try:
                return self.parse(output)
            except Exception, ex:
                raise BatchDiscoveryFsException(ex)
        else:
            msg = "An error occurred while executing batch script"
            raise BatchDiscoveryFsException(msg)

    def exists(self, path, includeAll=0):
        if includeAll != 0:
            self._shell.execCmd('dir /a /b %s' % path)
        else:
            self._shell.execCmd('dir /b %s' % path)
        return not self._shell.getLastCmdReturnCode()

    def cd(self, path):
        '''Changes the directory to specified path
        str -> None
        @raise PathNotFoundException: if specified path is not valid
        '''
        self._shell.execCmd(r'cd /D %s' % path)
        if self._shell.getLastCmdReturnCode() != 0:
            raise PathNotFoundException(path)

    def getFiles(self, path, isRecursive=0):
        '''Shell, str, bool - > list(File)
        Retrieves list of files by path
        @raise PathNotFoundException: if path not valid
        @raise BatchDiscoveryFsException: on script execution failure or
                                        if retrieved output is invalid
        '''
        # Need to change path to target directory, because for loop works only
        # with current path when iterating over files
        self.cd(path)
        result = []
        # Discover files
        result.extend(self.__list('*'))
        #Discover directories
        result.extend(self.__list('*', listDirectoriesOnly=1))
        return result

    def getFile(self, path):
        '''Shell, str - > File
        Retrieves file by path.
        @raise PathNotFoundException: if path not valid
        @raise BatchDiscoveryFsException: on script execution failure
                                            or if retrieved output is invalid
        '''
        files = self.__list(path)
        if files:
            return files[0]
        raise BatchDiscoveryFsException('Got empty collection: %s' % files)

class PowerShellFileInfoDiscovererByBatch(WindowsFileInfoDiscovererByBatch):
    def __init__(self, shell, reqAttrs=None):
        WindowsFileInfoDiscovererByBatch.__init__(self, shell, reqAttrs)


    def exists(self, path, includeAll=0):
        if includeAll != 0:
            self._shell.execCmd('cmd.exe /c "dir /a /b %s"' % path)
        else:
            self._shell.execCmd('cmd.exe /c "dir /b %s"' % path)
        return not self._shell.getLastCmdReturnCode()


def __getLinuxScript():
    path = r''
    linuxDiscoverer = LinuxFileInfoDiscovererByPerl(None, BASE_FILE_ATTRIBUTES + [FileAttrs.CONTENT])
    return linuxDiscoverer.buildQuery(r'%s/*' % path)


def __getBatchScript():
    winDiscoverer = WindowsFileInfoDiscovererByBatch(None, BASE_FILE_ATTRIBUTES + [FileAttrs.CONTENT])
    return  winDiscoverer.buildQuery('*', listDirectoriesOnly=1)
