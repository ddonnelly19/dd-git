#coding=utf-8
'''
Created on Dec 25, 2012

@author: iyani
'''

import re


_BIOS_ASSET_TAG_INVALID_PATTERN_STRINGS = (
   r'no asset tag', 
   r'empty(\s+value)?',
   r'not set', 
   r'none',
   r'system asset tag', 
)


_SERVICE_TAG_INVALID_PATTERN_STRINGS = (
    r'unknown', 
    r'system serial number',
    r'sys-1234567890',
    r'\.+'
)

_BIOS_ASSET_TAG_INVALID_PATTERNS = [re.compile(patternStr, re.I) for patternStr in _BIOS_ASSET_TAG_INVALID_PATTERN_STRINGS]

_SERVICE_TAG_INVALID_PATTERNS = [re.compile(patternStr, re.I) for patternStr in _SERVICE_TAG_INVALID_PATTERN_STRINGS]


def isBiosAssetTagValid(biosAssetTag):
    '''
    string -> bool
    '''
    return _isTagValid(biosAssetTag, _BIOS_ASSET_TAG_INVALID_PATTERNS)


def isServiceTagValid(serviceTag):
    '''
    string -> bool
    '''
    return _isTagValid(serviceTag, _SERVICE_TAG_INVALID_PATTERNS)


def _tagMatchesPattern(tagValue, pattern):
    return pattern.match(tagValue) is not None


def _isTagValid(tagValue, invalidPatterns):

    tagValue = tagValue and tagValue.strip()
    if not tagValue:
        return False
    
    for pattern in invalidPatterns:
        if pattern.match(tagValue):
            return False
        
    return True
