# coding=utf-8
'''
@author: ekondrashev, iyani

This module contains methods to parse command line produced by ps or wmic
to provide information about options used.

== Usage:

    unparsedCommandLine = 'program -option value -Dproperty=value'    # ps output
    args = cmdlineutils.splitArgs(unparsedCommandLine)                # split args into array (should do the same as command line interpreter)

    options = cmdlineutils.Options()                                  # build known options
    options.addOption(cmdlineutils.OptionBuilder.hasArgs(2).\
                      withValueSeparator().create('D'))
    options.addOption(cmdlineutils.Options("option", hasArg=true))

    parsedCommandLine = cmdlineutils.parseCommandLine(options, args)  # actual parsing
    value = parsedCommandLine.getOptionValue('option')                # get command line options


== Known limitations:

There is no known way to parse "ps -e -o args" output if there were spaces or
quotes in the original commandline.

I.e. a program run with these arguments:

    ./hello -option "quoted value"
    ./hello -option quoted value

will produce the same "ps -e -o args" output:

    /path/to/hello -option quoted value

I such case you should think of another way to treat it
'''
from __future__ import nested_scopes
import re
from org.apache.commons.cli import (
    ParseException as JParseException,
    Options as JOptions,
    Option as JOption,
    OptionBuilder as JOptionBuilder,
    GnuParser as JGnuParser
    )


class CommandLine:
    '''
    Wrapper around org.apache.commons.cli CommandLine.

    @see: http://commons.apache.org/cli/api-release/org/apache/commons/cli/CommandLine.html
    '''
    def __init__(self, commandLine):
        self.__commandLine = commandLine

    def getOptions(self):
        '''
        Returns a list of parsed options.
        '''
        options = []
        for option in self.__commandLine.getOptions():
            options.append(option)
        return options

    def hasOption(self, optionName):
        '''
        Returns True if an option with optionName was parsed.
        '''
        return self.__commandLine.hasOption(optionName)

    def getOptionValue(self, optionName):
        '''
        Returns a value of option with optionName.
        '''
        return self.__commandLine.getOptionValue(optionName)

    def getOptionProperties(self, optionName):
        '''
        Returns a dictionary of properties in optionName.
        E.g. this commandline:

         '-Dproperty1=value1 -Dproperty2=value2'

        will result in that getOptionProperties('D') will return this:

        { 'property1': 'value1', 'property2': 'value2' }
        '''
        return self.__commandLine.getOptionProperties(optionName)

    def __eq__(self, param):
        if isinstance(param, CommandLine):
            return (self.__commandLine.getOptions() ==
                    param.__commandLine.getOptions())
        else:
            return NotImplemented


class CmdLine:
    '''
    Represents unparsed command line.
    Just a wrapper around the command line string
    '''
    def __init__(self, commandLine):
        self.origCmdLine = commandLine
        self.normCmdLine = self.normalizeCmdLine(commandLine)

    def normalizeCmdLine(self, cmdLine):
        if cmdLine:
            tmpCmdLine = self.__collapsDirs(cmdLine)
            return self.__removeQuotes(tmpCmdLine)

    def __collapsDirs(self, cmdLine):
        if cmdLine:
            # windows notation
            tmpLine = re.sub(r"[\w\-\!.,\~ ]+\\\.\.\\", '', cmdLine)
            # unix notation
            tmpLine = re.sub(r"[\w\-.,\!\~ ]+/\.\./", '', tmpLine)
            return tmpLine
        return cmdLine

    def __removeQuotes(self, cmdLine):
        if cmdLine:
            return cmdLine.replace('\"', '')
        return cmdLine

    def getCommandLine(self):
        return self.origCmdLine

    def getNormalizedComdLine(self):
        return self.normCmdLine

    def __eq__(self, param):
        if not isinstance(param, CmdLine):
            return NotImplemented
        return (self.origCmdLine == param.getCommandLine()
                or self.normCmdLine == param.getNormalizedComdLine())

    def __ne__(self, other):
        eq = self.__eq__(other)
        if eq != NotImplemented:
            return not eq
        else:
            return eq

    def __hash__(self):
        return hash(self.normCmdLine)

    def newInstance(self, cmdLine):
        return CmdLine(cmdLine)


def splitArgs(commandLine):
    '''Splits input command line with a whitespaces,
    taking into account argument quotation, escaping of a whitespaces
    and doublequotes
    str -> [str]
    '''
    _ARG_ALIAS_PATTERN = '_#arg%s'
    argAliasToArg = {}
    argc = [0]  # workaround python nested scopes limitation
                # (you can't bind a new value to a name in
                # a non-global scope).

    def repl_func(matchobj):
        # make alias from argNumber
        argAlias = _ARG_ALIAS_PATTERN % argc[0]
        argAliasToArg[argAlias] = matchobj.group(0)

        argc[0] += 1
        return argAlias

    matcher2 = re.compile(r'''
                           [^"^\s]*        # multiple any characters except
                                           # quote or space
                           "               # followed by a quoted string
                           [^"]*           # match multiple
                                           # any characters except quote
                           "               # closing quote
                           ''', re.X)
    commandLine = re.sub(matcher2, repl_func, commandLine)
    args = re.split(r'(?<!\\)\s', commandLine)
    return map(lambda arg: arg in argAliasToArg.keys() \
                            and argAliasToArg[arg] or arg, args)


def parseCommandLine(options, args):
    '''
    Represents a list of arguments parsed against a Options descriptor.
    known limitations: ps output is without quotes.

    @types: commandlineutils.Options, [str] -> commandlineutils.CommandLine

    @param args: an array of command line arguments.
                To construct it use splitArgs

    @raise: commandlineutils.ParseException -
                     if an error occurs while parsing
                     the arguments, e.g., missing argument for an option.
    @raise: java.lang.IllegalArgumentException -
                     if option contains invalid symbol like ':'

    @see: http://commons.apache.org/cli/api-release/org/apache/commons/cli/Parser.html
    @see: http://commons.apache.org/cli/api-release/org/apache/commons/cli/CommandLine.html
    '''
    parser = __Parser()
    try:
        return CommandLine(parser.parse(options, args))
    except JParseException, ex:
        raise ParseException(ex.getMessage())


class ParseException(Exception):
    '''Base for Exceptions thrown during parsing of a command-line.
    @see: http://commons.apache.org/cli/api-release/org/apache/commons/cli/ParseException.html
    '''
    pass


class __Parser(JGnuParser):
    '''
    Problem:
        commons-cli library expects all possible options to be passed to the parser
        while creating CommandLine object.
        Otherwise UnrecognizedOptionException is raised.
        To change this behavior a parser
        with overridden processOption is used
    '''

    def processOption(self, arg, iterator):
        '''
        Overloaded to ignore unknown options
        '''
        hasOption = self.getOptions().hasOption(arg)
        if (hasOption):
            self.super__processOption(arg, iterator)


'''Proxy for commons-cli org.apache.commons.cli.OptionBuilder
Describes a single command-line option.
It maintains information regarding the short-name of the option, the long-name,
if any exists, a flag indicating if an argument is required for this option,
and a self-documenting description of the option.
An Option is not created independently, but is create through an instance
of Options.

@see: http://commons.apache.org/cli/api-release/index.html
'''
OptionBuilder = JOptionBuilder
Options = JOptions


class Option(JOption):
    '''Proxy for commons-cli org.apache.commons.cli.Option
    Describes a single command-line option.
    It maintains information regarding the short-name of the option,
    the long-name, if any exists, a flag indicating if an argument is required
    for this option, and a self-documenting description of the option.
    An Option is not created independantly, but is create through an instance
    of Options.

    @see: http://commons.apache.org/cli/api-release/index.html
    '''
    def __init__(self, optName='', longOptName='', hasArg=False, optDescription=''):
        if longOptName != '':
            JOption.__init__(self, optName, longOptName, hasArg, optDescription)
        else:
            JOption.__init__(self, optName, hasArg, optDescription)

    def __eq__(self, other):
        if not isinstance(other, Option):
            return NotImplemented

        return (other.getOpt() == self.getOpt() and
                other.getLongOpt() == self.getLongOpt() and
                other.hasArg() == self.hasArg() and
                other.getDescription() == self.getDescription())

    def __ne__(self, other):
        eq = self.__eq__(other)
        if eq != NotImplemented:
            return not eq
        else:
            return eq
