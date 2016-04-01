# coding=utf-8
'''
Created on Apr 8, 2013

@author: ekondrashev
'''
import db2_win_reg_base_discoverer


SUPPORTED_VERSIONS = (
                      ((9, 1), 64),
                      ((9, 5), 64),
                      ((9, 7), 64),
                      ((9, 8), 64),
                      ((10, 1), 64),
                      )

get_version = db2_win_reg_base_discoverer.get_version
GetPlatformVersion = db2_win_reg_base_discoverer.GetPlatformVersion


class GetInstanceNameByPid(db2_win_reg_base_discoverer.GetInstanceNameByPid):
    KEY_PATH = r'SOFTWARE\Wow6432Node\IBM'

GetClusterInstanceNameByPid = db2_win_reg_base_discoverer.GetClusterInstanceNameByPid