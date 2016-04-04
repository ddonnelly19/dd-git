#coding=utf-8
'''
Created on 13 October 2010

@author: ekondrashev
'''

import logger

from file_topology import PathNotFoundException
from file_info_discoverers import WindowsFileInfoDiscovererByBatch,\
    LinuxFileInfoDiscovererByPerl, SunOSFileInfoDiscovererByPerl,\
    UnixFileInfoDiscovererByPerl, PowerShellFileInfoDiscovererByBatch
import file_topology
import entity

_NT_PATH = file_topology.NtPath()
_POSIX_PATH = file_topology.PosixPath()


def createFileSystem(shell):
    '''Factory method creating FileSystem object depending on remote os type
    @param shell : Remote shell
    @type shell: Shell
    @return: Os specific file system object
    @rtype: FileSystem
    '''
    if shell.isWinOs():
        if shell.getClientType() == "powershell":
            return PowerShellFileSystem(shell)
        return WindowsFileSystem(shell)
    else:
        return UnixFileSystem(shell)


class FileFilter:
    '''
    Base class implementing filter logic.
    '''
    def accept(self, file_):
        '''Interface method indicating whether file_ should be accepted or not.
        @param file_: target file_ to be filtered
        @type file_: File
        @return: True if file_ should be accepted or False otherwise
        @rtype: bool
        '''
        raise NotImplemented


class ExtensionsFilter(FileFilter):
    '''
    A file filter deciding whether to accept the file depending on its extension.
    '''
    def __init__(self, extensions):
        '''Constructor for the extension filter.
        @param extensions: list of extensions that should be accepted
        @type extensions: list
        '''
        self.extensions = extensions

    def accept(self, file_):
        if file_ and file_.ext:
            for ext in self.extensions:
                if ext == "*" or (file_.ext.lower() == ext.lower()):
                    return 1
        else:
            return ('*' in self.extensions or '' in self.extensions)
        return 0


class FileSystem:
    'Base class defining methods to work with remote file system.'
    def __init__(self, shell):
        '''Constructor for the file system object.
        @param shell: Remote shell
        @type shell: Shell
        '''
        self._shell = shell

    def __repr__(self):
        return 'FileSystem(%s)' % self._shell

    def filter(self, files, filters):
        '''Filters target files with specified filters.
        list(File), list(FileFilter) -> list(File)
        @param files: target list of files to be filtered
        @type files: list(File)
        @param filters: list of FileFilter to be applied on files collection
        @type filters: list(FileFilter)
        @return: filtered list of files
        @rtype: list(File)
        '''
        for fsFilter in filters:
            files = filter(lambda file_,
                           fsFilter=fsFilter: fsFilter.accept(file_), files)
        return files

    def concat(self, basePath, fullFilenameToAdd):
        '''Concatenates parent and child to one path, returning full path to the file,
        taking in account all prefix and postfix file separators.
        str, str -> str
        @param basePath: parent path
        @type basePath: str
        @param fullFilenameToAdd: target file name
        @type fullFilenameToAdd: str
        @return: full path to the file
        @rtype: str
        '''

        if basePath.endswith(self.FileSeparator):
            if not fullFilenameToAdd.startswith(self.FileSeparator):
                return basePath + fullFilenameToAdd
            else:
                return basePath[:-1] + fullFilenameToAdd
        else:
            if fullFilenameToAdd.startswith(self.FileSeparator):
                return basePath + fullFilenameToAdd
            else:
                return basePath + self.FileSeparator + fullFilenameToAdd

    def getFiles(self, path, recursive=0,  filters=[], fileAttrs=[]):
        '''Returns all files in a specified path accepted by filters.
        Only specified file attributes are discovered.
        If no attributes specified, then file_topology.BASE_FILE_ATTRIBUTES is used.

        str, bool, list(FileFilter), list(FileAttrs) -> list(File)
        @param path: target path to list files at
        @type path: str
        @param recursive: flag indicating whether path should be discovered recursively
        @type recursive: bool
        @param filters: list of filters to be applied on result file collection
        @type filters: list(FileFilter)
        @param fileAttrs: list of file attributes to be discovered
        @type fileAttrs: list(FileAttrs)
        @return: list of discovered File objects
        @rtype: list(File)
        @raises PathNotFoundException if specified path is not valid
        @raises FsException if error occurs while retrieving files
        '''
        raise NotImplemented

    def getFile(self, path, fileAttrs=[], includeAll=0):
        '''Returns file by specified path.
        Only specified file attributes are discovered.
        If no attributes specified, then file_topology.BASE_FILE_ATTRIBUTES is used.

        str, list(FileAttrs) -> File
        @param path: target path of a file to discover
        @type path: str
        @param fileAttrs: list of file attributes to be discovered
        @type fileAttrs: list(FileAttrs)
        @param includeAll: whether get file with SYSTEM and HIDDEN attributes,
        only valid for Windows platform, will be ignored under Unices
        @type path: bool
        @return: list of discovered File objects
        @rtype: list(File)
        @raises PathNotFoundException if specified path is not valid
        @raises FsException if error occurs while retrieving file
        '''
        raise NotImplemented

    def getFileContent(self, path):
        '''
        Get file with the following attributes filled in:
            - name
            - path
            - parent
            - is directory
            - content
        @types: str -> file_topology.File
        '''
        attributes = (file_topology.BASE_FILE_ATTRIBUTES +
                        [file_topology.FileAttrs.CONTENT])
        return self.getFile(path, attributes)

    def exists(self, path):
        '''Checks whether path exists or not.
        str -> bool
        @param path: to to check for existence
        @type: str
        @return: True if path exists, False otherwise
        @rtype: bool
        '''
        raise NotImplemented

    def moveFile(self, srcPath, dstPath):
        '''move file from source path to destination path
        str, str
        '''
        raise NotImplemented

    def removeFile(self, path):
        '''remove file from path
        str
        '''
        raise NotImplemented

    def isDirectory(self, path):
        attr = [file_topology.FileAttrs.IS_DIRECTORY]
        file_info = self.getFile(path, attr)
        return file_info and file_info.isDirectory

    def getTempFolder(self):
        raise NotImplemented


__DISCOVERER_BY_OS_TYPE = {
    'linux': LinuxFileInfoDiscovererByPerl,
    'sunos': SunOSFileInfoDiscovererByPerl
}


class UnixFileSystem(FileSystem):

    def __init__(self, shell):
        FileSystem.__init__(self, shell)
        self.__discovererType =  __DISCOVERER_BY_OS_TYPE.get(shell.getOsType(), UnixFileInfoDiscovererByPerl)
        self.FileSeparator = '/'
        logger.debug('UnixFileSystem created successfully, backend: %s' % self.__discovererType)

    def __normalizePath(self, path):
        r''' @types: str -> str
        @raise ValueError: Path is empty
        '''
        return _POSIX_PATH.normalizePath(path)

    def exists(self, path):
        '''Checks whether path exists or not
        str -> bool
        '''
        path = self.__normalizePath(path)
        return  self.__discovererType(self._shell).exists(path)

    def getFiles(self, path, recursive=0, filters=[], fileAttrs=[]):
        '''Retrieves list of files in specified path.
        str, bool, list(FileFilter) -> list(File)
        @raises PathNotFoundException if specified path is not valid
        @raises FsException if error occurs while retrieving files
        '''

        perlFileDiscoverer = self.__discovererType(self._shell, fileAttrs)
        path = self.__normalizePath(path)
        files = perlFileDiscoverer.getFiles(path)
        return self.filter(files,  filters)

    def getFile(self, path, fileAttrs=[], includeAll=0):
        '''Retrieves file by specified path
        str -> File
        @raises PathNotFoundException if specified path is not valid
        @raises FsException if error occurs while retrieving file
        '''
        perlFileDiscoverer = self.__discovererType(self._shell, fileAttrs)
        path = self.__normalizePath(path)
        return perlFileDiscoverer.getFile(path)

    def getTempFolder(self):
        if self.exists("$TMPDIR"):
            return "$TMPDIR" + self.FileSeparator
        elif self.exists("/temp"):
            return "/temp" + self.FileSeparator
        return "/tmp" + self.FileSeparator

    def moveFile(self, srcPath, dstPath):
        '''move file from source path to destination path
        str, str
        '''
        moveCMD = 'mv -f \"' +srcPath+ '\" \"' +dstPath+ '\"'
        self._shell.execCmd(moveCMD)

    def removeFile(self, path):
        '''remove file from path
        str
        '''
        removeCMD = 'rm -f \"' +path+ '\"'
        self._shell.execCmd(removeCMD)

class WindowsFileSystem(FileSystem):

    def __init__(self, shell):
        FileSystem.__init__(self, shell)
        self.FileSeparator = '\\'
        logger.debug('WindowsFileSystem created successfully')

    def __normalizePath(self, path):
        r''' @types: str -> str
        @raise ValueError: Path to wrap with quotes is empty
        '''
        return _NT_PATH.normalizePath(_NT_PATH.wrapWithQuotes(path))

    def exists(self, path):
        '''Checks whether path exists or not
        str -> bool
        '''
        return WindowsFileInfoDiscovererByBatch(self._shell).exists(self.__normalizePath(path))

    def getFiles(self, path, recursive=0, filters=[], fileAttrs=[]):
        '''Retrieves list of files in specified path.
        str, bool, list(FileFilter) -> list(File)
        @raises PathNotFoundException if specified path is not valid
        @raises FsException if error occurs while retrieving files
        '''

        batchFileRetriever = WindowsFileInfoDiscovererByBatch(self._shell, fileAttrs)
        path = self.__normalizePath(path)
        if (batchFileRetriever.exists(path)):
            files = batchFileRetriever.getFiles(path, recursive)
            return self.filter(files,  filters)
        raise PathNotFoundException(path)

    def getFile(self, path, fileAttrs=[], includeAll=0):
        '''Retrieves file by specified path
        str -> File
        @raises PathNotFoundException if specified path is not valid
        @raises FsException if error occurs while retrieving file
        '''
        path = self.__normalizePath(path)
        batchFileRetriever = WindowsFileInfoDiscovererByBatch(self._shell, fileAttrs)
        if (batchFileRetriever.exists(path, includeAll)):
            return batchFileRetriever.getFile(path)
        raise PathNotFoundException(path)

    def getTempFolder(self):
        return "%temp%" + self.FileSeparator

    def moveFile(self, srcPath, dstPath):
        '''move file from source path to destination path
        str, str
        '''
        moveCMD = 'del \"' +dstPath+ '\" & copy /Y \"' +srcPath+ '\" \"' +dstPath+ '\" & del \"' +srcPath+ '\"'
        self._shell.execCmd(moveCMD)

    def removeFile(self, path):
        '''remove file from path
        str
        '''
        removeCMD = 'del \"' + path + '\"'
        self._shell.execCmd(removeCMD)

class PowerShellFileSystem(WindowsFileSystem):
    def __init__(self, shell):
        FileSystem.__init__(self, shell)
        self.FileSeparator = '\\'
        logger.debug('PowerShellFileSystem created successfully')

    def __normalizePath(self, path):
        r''' @types: str -> str
        @raise ValueError: Path to wrap with quotes is empty
        '''
        return _NT_PATH.normalizePath(_NT_PATH.wrapWithQuotes(path))

    def exists(self, path):
        '''Checks whether path exists or not
        str -> bool
        '''
        return PowerShellFileInfoDiscovererByBatch(self._shell).exists(self.__normalizePath(path))


def getPathToolByShell(shell):
    return getPathTool(createFileSystem(shell))


def getPathTool(fileSystem):
    r'''@type: file_system.FileSystem -> file_topology.Path
    '''
    pathToFsType = {
        WindowsFileSystem: _NT_PATH,
        UnixFileSystem: _POSIX_PATH
    }
    for fsClass, pathUtilInstance in pathToFsType.items():
        if isinstance(fileSystem, fsClass):
            return pathUtilInstance
    raise ValueError('FileSystem type is unknown %s' % fileSystem)


def getPath(fileSystem):
    r'@deprecated: use getPathTool instead'
    return getPathTool(fileSystem)


def UnixPath(path):
    '''Helper method to create unix path instance

    @param path: string representation of unix path to create wrapper against
    @type path: basestring
    @return: Path instance with posix path tool
    @rtype: file_system.Path
    '''
    return Path(path, _POSIX_PATH)


def WinPath(path):
    '''Helper method to create windows path instance

    @param path: string representation of windows path to create wrapper against
    @type path: basestring
    @return: Path instance with nt_path path tool
    @rtype: file_system.Path
    '''
    return Path(path, _NT_PATH)


class Path(entity.Immutable):

    def __init__(self, path, path_tool):
        self.path = path
        self.path_tool = path_tool

    def __str__(self):
        return self.path

    def __add__(self, other):
        new_path = self.path_tool.join(self.path, str(other))
        return Path(new_path, self.path_tool)

    def __eq__(self, other):
        if isinstance(other, Path):
            normpath = self.path_tool.normalizePath
            return normpath(self.path) == normpath(other.path)
        return NotImplemented

    def __ne__(self, other):
        result = self.__eq__(other)
        if result is NotImplemented:
            return result
        return not result

    def get_parent(self, normpath=True):
        path = self.path
        if normpath:
            self.path_tool.normalizePath(path)
        parent_path = self.path_tool.dirName(path)
        return Path(parent_path, self.path_tool)

    @property
    def basename(self):
        return self.path_tool.baseName(self.path)

    @property
    def cmdline(self):
        return self.path_tool.cmdline_path(self.path)
