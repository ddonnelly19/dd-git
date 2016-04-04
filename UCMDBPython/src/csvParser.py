#coding=utf-8
'''
Created on Jul 17, 2009
@author: vvitvitskiy
'''
from java.lang import Iterable, UnsupportedOperationException
from java.util import Iterator
from java.lang.Integer import parseInt
from java.lang.Double import parseDouble
from java.lang.Float import parseFloat
from import_converters import stringToBoolean
from java.io import BufferedReader

class Processor:
    '''
    Csv File processor
    '''
    __DEFAULT_PARSER_DELIMITER = ','

    def __init__(self, delimiter = __DEFAULT_PARSER_DELIMITER, minTokenAmount = 1):
        '''
        Construct processor that process CSV stream and produce
        rows split on tokens by 'delimiter', where if
        row has amount of tokens less than 'minTokenAmount'
        it is skipped
        @param delimiter: delimiter for tokens in row
        @param minTokenAmount: if amount of tokens in rows is less
        than this value -> row is skipped
        '''
        self.__delimiter = delimiter
        self.__minTokenAmount = minTokenAmount
        self.__rowToStartIndex = 0

    def setRowIndexToStartFrom(self, index):
        '''
        Skip rows in order to start import from row with necessary index
        @param index:
        '''
        self.__rowToStartIndex = index

    def processByParser(self, parser):
        '''Get CSV file processed by customized parser
        csv.Parser -> csv.File'''
        return self.__process(parser)

    def process(self, reader):
        '''Process csv file from stream reader
        java.io.Reader -> csv.File
        @deprecated: Use processByParser method instead
        '''
        parser = Parser(reader, self.__delimiter)
        parser.setRowToStartIndex(self.__rowToStartIndex)
        return self.__process(parser)

    def __process(self, parser):
        tokens = parser.parseNext()
        rows = []

        while tokens is not None:
            # consider that line can not be empty
            if len(tokens) >= self.__minTokenAmount:
                row = Row(self.__getStripped(tokens))
                rows.append(row)
            tokens = parser.parseNext()
        return File(rows)

    def __getStripped(self, tokens):
        strippedTokens = []
        for token in tokens:
            strippedTokens.append(token.strip())
        return strippedTokens


class File(Iterable):
    '''
    View of CSV file that contains list of rows split on tokens
    '''
    def __init__(self, rows):
        '''
        Construct file with specified rows
        '''
        self.__rows = rows

    def iterator(self):
        '''
        Returns an iterator over the rows in this file in proper sequence.
        This implementation returns a straightforward implementation of the iterator interface.
        Note that the iterator returned by this method will throw an UnsupportedOperationException in response to its remove method.
        '''
        return __FileIterator(self.__rows)

    def toString(self):
        '''
        Returns instance short information like '{row_amount: N}'
        '''
        return '{row_amount: %s}' % len(self.__rows)

    def getRows(self):
        '''
        Returns copy of list of rows
        @return: parsed rows
        '''
        return list(self.__rows)


class __FileIterator(Iterator):
    #TODO: override hash code and equals method for iterator

    def __init__(self, rows):
        self.__rows = rows
        self.__size = len(rows)
        self.__currentIndex = 0

    def hasNext(self):
        '''
        Returns true if the iteration has more elements.
        @return: boolean
        '''
        return self.__currentIndex != self.__size

    def hasNextRow(self):
        '''
        Returns true if the iteration has more elements.
        @return: boolean
        '''
        return self.hasNext()

    def next(self):
        '''
        Returns the next element in the iteration.
        @return: CsvRow next row
        '''
        r = self.__rows[self.__currentIndex]
        self.__currentIndex += 1
        return r

    def nextRow(self):
        '''
        Returns the next element in the iteration.
        @return: CsvRow next row
        '''
        return self.next()


class Row:
    '''
    View of Row that represents CSV file row split on tokens.
    '''
    def __init__(self, tokens):
        '''
        Construct row with specified tokens
        '''
        self.__tokens = tokens

    def getString(self, index):
        '''
        Retrieves the value of the designated token in the current row
        as an string.
        @return: string
        '''
        return self.__tokens[index]

    def getBoolean(self, index):
        '''
        Retrieves the value of the designated token in the current row
        as an boolean
        '''
        # version 2.2.1 has BOOL function
        return stringToBoolean(self.__tokens[index])

    def getFloat(self, index):
        '''
        Retrieves the value of the designated token in the current row
        as an java.lang.Float in Java programming language.
        '''
        return parseFloat(self.__tokens[index])

    def getDouble(self, index):
        '''
        Retrieves the value of the designated token in the current row
        as an java.lang.Double in Java programming language.
        '''
        return parseDouble(self.__tokens[index])

    def getInt(self, index):
        '''
        Retrieves the value of the designated token in the current row
        as an java.lang.Integer in Java programming language.
        '''
        return parseInt(self.__tokens[index])

class Parser:
    '''
    CSV content parser
    '''
    DEFAULT_QUOTE_SYMB = '"'
    DEFAULT_ESCAPE_SYMB = "\\"
    DEFAULT_ROW_TO_START_INDEX = 0

    def __init__(self, reader, delimiter):
        '''
        Constructs parser for stream
        @param reader: java.io.Reader
        @param delimiter: the separator of tokens
        @raise Exception: if reader of delimiter is None
        '''
        if reader is None:
            raise Exception, "Reader can not be None"
        if delimiter is None:
            raise Exception, "Delimiter can not be None"

        #try to make reader as BufferedReader
        if isinstance(reader, BufferedReader):
            self.__reader = reader
        else:
            self.__reader = BufferedReader(reader)

        self.__escapeSeq = Parser.DEFAULT_ESCAPE_SYMB
        self.__delimiter = delimiter

        self.__rowToStartIndex = Parser.DEFAULT_ROW_TO_START_INDEX
        self.__quotesymb = Parser.DEFAULT_QUOTE_SYMB

        self.__isHeaderLineProcessed = 0

    def setQuoteSymbol(self, symbol):
        '''
        Set the quote symbol
        @param symbol: the quote symbol
        '''
        self.__quotesymb = symbol or self.DEFAULT_QUOTE_SYMB

    def getQuoteSymbol(self):
        return self.__quotesymb

    def setRowToStartIndex(self, index):
        '''
        Set the index, that indicates row number from
        witch parsing will be started.
        Fist row has index 0 and so on.
        @param index: index of row to start
        '''
        self.__rowToStartIndex = index or Parser.DEFAULT_ROW_TO_START_INDEX

    def getRowToStartIndex(self):
        return self.__rowToStartIndex

    def parseNext(self):
        '''
        Parse next line
        @return: tokens of parsed line
        '''
        line = self.__readNextLine()
        tokens = None
        if line is not None:
            tokens = line.strip() and self.__parseLine(line) or []
        return tokens

    def __readNextLine(self):
        if not self.__isHeaderLineProcessed and self.__rowToStartIndex:
            for i in range(0, self.__rowToStartIndex):
                self.__reader.readLine()
            self.__isHeaderLineProcessed = 1
        return self.__reader.readLine()

    def __isEscaped(self, charIndex, line):
        'int, str -> bool'
        escapeSymbIdx = charIndex - len(self.__escapeSeq)
        return (escapeSymbIdx > -1
                and line[escapeSymbIdx: charIndex] == self.__escapeSeq)

    def __parseLine(self, line):
        tokensOnThisLine = []

        sb = ''
        inQuotes = 0
        while 1:
            if inQuotes:
                sb += "\n"
                line = self.__readNextLine()
                if line is None:
                    break

            i = 0
            while i < len(line):
                c = line[i]
                if c == self.__quotesymb:
                    # escape quote
                    if self.__isEscaped(i, line):
                        sb = sb[:-len(self.__escapeSeq)]
                        sb += c
                    # treat two quote symbols as one
                    elif (len(line) > (i+1)
                        and line[i+1] == self.__quotesymb):
                            sb += c
                            i+=1
                    else:
                        inQuotes = not inQuotes
                elif c == self.__delimiter and not inQuotes:
                    # escape delimiter
                    if self.__isEscaped(i, line):
                        sb = sb[:-len(self.__escapeSeq)]
                        sb += c
                    else:
                        #save token and process next
                        tokensOnThisLine.append(sb)
                        sb = ''
                else:
                    sb += c
                i+=1
            #do-while condition
            if not inQuotes:
                break

        tokensOnThisLine.append(sb)
        return tokensOnThisLine

    def close(self):
        '''
        Close reader
        '''
        self.__reader.close()
