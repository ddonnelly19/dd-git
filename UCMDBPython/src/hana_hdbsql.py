# coding=utf-8
'''
Created on Nov 13, 2013

@author: ekondrashev
'''
import re
from itertools import imap
import file_system
import shell_interpreter
from iteratortools import findFirst
from fptools import safeFunc as Sfn, comp
import command
from hana_sql_base_command import _Item
import hana_base_command

_HDBSQL_BINARY_NAME = r'hdbsql'
_HDBCLIENT_FOLDER_NAME = r'hdbclient'


def findHdbsqlPathBySid(fs, installationPath, dbSid, is_cmd_exist, shell_executor):
    binName = _HDBSQL_BINARY_NAME
    if fs._shell.isWinOs():
        binName = '%s.exe' % binName

    pathTool = file_system.getPath(fs)

    alternatives = (
                    file_system.Path(installationPath, pathTool) + _HDBCLIENT_FOLDER_NAME + binName,
                    file_system.Path('/usr/sap', pathTool) + _HDBCLIENT_FOLDER_NAME + binName,
                    file_system.Path('/usr/sap', pathTool) + dbSid + _HDBCLIENT_FOLDER_NAME + binName,
                    file_system.Path('/usr/sap', pathTool) + dbSid + 'exe' + 'linuxx86_64' + 'hdb' + binName,
                    file_system.Path('/usr/sap', pathTool) + dbSid + r'SYS' + r'global' + _HDBCLIENT_FOLDER_NAME + binName,
                    file_system.Path('/sapmnt', pathTool) + dbSid + _HDBCLIENT_FOLDER_NAME + binName,
                    file_system.Path('/sapmnt', pathTool) + dbSid + r'global' + _HDBCLIENT_FOLDER_NAME + binName,
                    )

    alternatives = imap(shell_interpreter.normalizePath, alternatives)
    binpath = findFirst(Sfn(fs.exists), alternatives)
    if not binpath:
        bin_in_path = is_cmd_exist(binName) | shell_executor
        if not bin_in_path:
            raise NoHdbsqlException('Hdbsql binary not found')
        binpath = binName
    return binpath


class NoHdbsqlException(Exception):
    pass


class HdbsqlExecuteException(command.ExecuteException):
    pass


class EmptyHdbsqlResultSetException(HdbsqlExecuteException):
    pass


def raise_when_empty(result):
    r'@types: command.Result -> command.Result'
    if not result:
        raise EmptyHdbsqlResultSetException("Output is empty")
    return result


def parse_items(output):
    """Expects stripped output on input.
    @types: str -> list[_Item]
    @tito: {r'''HOST,KEY,VALUE
"k234","sapsystem","4"
1 row selected (0 usec)''' : [_Item(host="k234", key="sapsystem", value="4")],
            r'''HOST,KEY,VALUE
0 row selected (0 usec)''' : [],
        }
    """
    assert output
    res = []
    lines = output.splitlines()
    assert len(lines) >= 2
    fieldNames = lines[0].split(',')
    for line in lines[1:-1]:
        _kwargs = {}
        for key, value in zip(fieldNames, line.split(',')):
            value = value.strip()
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
            _kwargs[key.lower()] = value
        res.append(_Item(**_kwargs))

    return res


class RaiseWhenHdbsqlOutputIsInvalidCmdlet(command.Cmdlet):

    def parseResultSetRowCount(self, output):
        """
        @types: str-> str or None
        @tito: {r'''HOST,KEY,VALUE
"l24","sapsystem","4"
1 row selected (0 usec)

''' : 1 ,
        r'''SCHEMA_NAME,SCHEMA_OWNER
0 rows selected (0 usec)

''' : 0 ,
        r'''* 259: invalid table name: SCHEMAS1: line 1 col 15 (at pos 14) SQLSTATE: HY000
''' : None,}
   """
        lines = output.strip().splitlines()
        assert len(lines)
        m = re.match(r'(\d+) rows? selected .*', lines[-1])
        return m and long(m.group(1))

    def _isOutputValid(self, output):
        return self.parseResultSetRowCount(output) is not None

    def process(self, result):
        r'@types: command.Result -> command.Result'
        if not self._isOutputValid(result.output):
            raise HdbsqlExecuteException("Output is invalid")
        return result


class Cmd(hana_base_command.Cmd, command.Cmdlet):
    DEFAULT_HANDLERS = (hana_base_command.Cmd.DEFAULT_HANDLERS +
                        (command.cmdlet.raiseOnNonZeroReturnCode,
                         command.cmdlet.raiseWhenOutputIsNone,
                         RaiseWhenHdbsqlOutputIsInvalidCmdlet(),
                         command.cmdlet.stripOutput,
                         parse_items,
                         raise_when_empty,
                         ))

    def __init__(self, cmdline, handler=None):
        hana_base_command.Cmd.__init__(self, cmdline, handler=handler)

    def execSql(self, sql):
        raise NotImplementedError('execSql')


class Cmd_v1_0(Cmd):
    def __init__(self, hdbsqlPath, userName, handler=None):
        Cmd.__init__(self, hdbsqlPath, handler=handler)
        self.userName = userName

    def compose_exesql_cmdline(self, sql):
        assert sql and sql.find('"') < 0
        return r'%s -j -U %s "%s"' % (self.cmdline, self.userName, sql)

    def execSql(self, sql):
        return command.Cmd(self.compose_exesql_cmdline(sql), self.handler)

    def exec_sqlcmd(self, sqlcmd):
        cmdline = self.compose_exesql_cmdline(sqlcmd.cmdline)
        handler = comp(sqlcmd.handler, self.handler)
        return command.Cmd(cmdline, handler)

    def process(self, other):
        return self.exec_sqlcmd(other)


def getHdbsqlCommandClass(shell):
    r'@types: shellutils.Shell -> hana_hdbsql.Cmd'
    return Cmd_v1_0
