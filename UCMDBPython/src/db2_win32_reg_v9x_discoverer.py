# coding=utf-8
'''
Created on Apr 8, 2013

@author: ekondrashev
'''
import db2_win_reg_base_discoverer


SUPPORTED_VERSIONS = (
                      ((9, 1), 32),
                      ((9, 5), 32),
                      ((9, 7), 32),
                      ((9, 8), 32),
                      ((10, 1), 32),
                      )


get_version = db2_win_reg_base_discoverer.get_version
GetPlatformVersion = db2_win_reg_base_discoverer.GetPlatformVersion
GetInstanceNameByPid = db2_win_reg_base_discoverer.GetInstanceNameByPid
GetClusterInstanceNameByPid = db2_win_reg_base_discoverer.GetClusterInstanceNameByPid