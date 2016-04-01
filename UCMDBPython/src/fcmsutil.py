# coding=utf-8
'''
Created on Feb 18, 2014

@author: ekondrashev

This module contains `fcmsutil` command wrapper for HPUX of 11.31 version.

`man fcmsutil` output:

 NAME
      fcmsutil - Fibre Channel Mass Storage Utility Command for Fibre
      Channel Host Bus Adapters

 SYNOPSIS
      /opt/fcms/bin/fcmsutil device_file [options]

      The device_file specifies the Fibre Channel device special file
      associated with the Fibre Channel HBA port.

      The device file has the format /dev/FC_driverX, where X is the instance
      number of the Fibre Channel HBA port, as reported by the ioscan output.

      The [options] that follow the device file are the ones listed in the
      fcmsutil display usage for each type of Fibre Channel driver.  The
      usage of fcmsutil can be seen by running the command alone.  Options
      listed under the fcmsutil usage for different HBAs are supported for
      that HBA.

      In case an invalid device file is specified, that is, if the device
      file does not belong to the fc class, the fcmsutil command will return
      an error and display the usage options of fcmsutil.

      Note:  For all options that take remote-N-Port-ID as an argument,
      remote-N-Port-ID can be replaced with -l loop_id (in Private Loop), or
      -w wwn.

 SECURITY RESTRICTIONS
      The usage of fcmsutil command is restricted to processes having super
      user privileges.  Some of the options require detailed knowledge of
      the device specific adapter.  See privileges(5) for more information
      about privileged access on systems that support fine-grained
      privileges.

 DESCRIPTION
      For a list of all supported Fibre Channel HBAs, please refer to the
      HP-UX Fibre Channel HBA Support Matrix available at:

           http://docs.hp.com/en/FCI-SM/FCI-SM.htm

      The fcmsutil command is a common diagnostic tool used for all Fibre
      Channel Host Bus Adapters supported on HP-UX.  This command provides
      the ability to perform Fibre Channel Test and Echo functionality, read
      the card's registers, and so on.  This command requires the use of a
      device file to indicate the interface over which the requested command
      needs to be performed.

    Options
      fcmsutil options are described below.  Some options are HBA-specific
      and, therefore, are not supported by all Fibre Channel HBAs.

      The list of options supported by each HBA may be obtained by running
      fcmsutil without specifying any arguments.

      All keywords are case-insensitive and are position dependent.

      device_file    Can be used alone or with other options.

                     When used without any options it provides information
                     such as the N_Port ID, Node World Wide Name and Port
                     World Wide Name of the HBA and the switch (when
                     applicable), Topology, the negotiated Link Speed,
                     Vendor ID, Device ID, the Driver State, Hardware Path,
                     Maximum Frame Size, and Driver Version.

                     As per the FC protocol, Node WWN will be numerically
                     one more than the Port WWN.

                     The following topologies are defined:

                     UNINITIALIZED.
                          There is no connectivity to the host bus adapter
                          port or the topology could not be determined.

                     UNKNOWN.
                          The Fibre Channel driver has returned a topology
                          code that the utility does not understand.

                     PRIVATE_LOOP.
                          The host bus adapter is attached to a
                          loop/loopback hood.

                     PUBLIC_LOOP.
                          The host adapter is attached to a loop connected
                          to a Fibre Channel switch.

                     IN_PTTOPT_NPORT/PTTOPT_NPORT.
                          The host bus adapter has come up in a point to
                          point topology.  This topology can be an error if
                          the card was expected to come up in loop topology.
                          Not legal in most cases.

                     PTTOPT_FABRIC.
                          The host bus adapter has come up in a point to
                          point topology when connected through a Fibre
                          Channel switch.  This topology can be an error if
                          the card was expected to come up in loop topology.

                     The following driver states are defined:

                     LOOPBACK_STATE.
                          The host bus adapter is in the loop back test
                          phase.

                     OFFLINE/DISABLED.
                          The host bus adapter is not participating on the
                          loop.  This state is the result of user disabling
                          the card through the disable option in fcmsutil or
                          the Fibre Channel driver being unable to recover
                          from an error.

                     READY/ONLINE.
                          The driver is up and functional.

                     RESETTING.
                          The host bus adapter is being reset.

                     SUSPENDED.
                          The driver has been suspended by the user.

                     AWAITING_LINK_UP.
                          The driver is waiting for the Fibre Channel link
                          to come up.  There is no connectivity to the HBA
                          port.

                     All other states are only transient and should not
                     continue for long.  If the transient state persists,
                     there might be a problem in the hardware connectivity
                     or configuration.

                     The following link speeds are defined:

                     UNINITIALIZED or UNKNOWN.
                          The host bus adapter not could converge to a
                          common link speed or adapter is not connected.

                     1Gb. The link is online and the operating speed is 1
                          gigabits per second.

                     2Gb. The link is online and the operating speed is 2
                          gigabits per second.

                     4Gb. The link is online and the operating speed is 4
                          gigabits per second.

      vpd            This option is used to display "Vital Product Data"
                     information of the HBA.  It includes information such
                     as the product description, part number, engineering
                     date code, part serial number, and so on.  This option
                     is not supported by the TACHYON TL HBAs.

      echo remote-N-Port-ID data_size [count]
                     This option is used to send an ECHO ELS frame on the
                     wire.  It requires two parameters, the remote-N-Port-ID
                     and data-size (size of packet to send).  An optional
                     third argument (count) can be specified for the number
                     of echo packets to be sent.  If the count option is not
                     specified, one packet will be sent.

                     Fibre Channel Echo packets of the specified size are
                     sent to the remote node.  The command completes
                     successfully when an echo response is received from the
                     remote node and matches the data sent, for all packets
                     sent.  The command times out if a response is not
                     received in twice RA_TOV time.  Echo packets cannot be
                     sent in a PUBLIC_LOOP topology.

                     Note: Packet size specified must be a multiple of 4.

      rls remote-N-Port-ID
                     This option is used to send an RLS (Request Link
                     Status) ELS frame on the wire.  It requires one
                     parameter, the remote-N-Port-ID.  The ELS is sent to
                     this remote-N-Port-ID and the response data is
                     displayed.

      test remote-N-Port-ID data_size [count]
                     This option is used to send a TEST ELS on the wire.  It
                     requires two parameters, the remote-N-Port-ID and
                     data-size (size of packet to send).  An optional third
                     argument (count) can be specified for the number of
                     echo packets to be sent.  If the count option is not
                     specified, one packet will be sent.

                     The command completes successfully and immediately on
                     sending all the test packets.

                     Note: Packet size specified must be a multiple of 4.

      read offset [pci]
                     This option is used to read from HBA's internal
                     registers.  It requires one parameter, the offset of
                     the register to read from.  The offset can be specified
                     in either hex or in decimal format.  The offset
                     specified is an offset from the base of the Memory Map.
                     The user of this command is therefore expected to have
                     internal knowledge of the chip.  Reading from the
                     TACHYON frame manager status register (0x01c8) is
                     restricted.

                     An optional second argument (pci) can be specified for
                     Fibre Channel HBAs, to read from the PCI config space.
                     If no second argument is specified, it reads from the
                     chip register space.

      write offset value [pci]

                     This option is used to write into HBA's registers.  It
                     requires two parameters, the offset of the register to
                     write to and the value to be written.

                     An optional third argument (pci) can be specified for
                     the Fibre Channel HBAs, to write into the PCI config
                     space.  If no third argument is specified, it writes
                     into the chip register space.

      [-f] lb        This option is used to perform loopback tests on the
                     port.

                     Warning:  This is a DESTRUCTIVE test, and DATA LOSS
                     during the execution of this test may occur.

                     The -f option can be used to suppress the warning
                     message displayed by the Fibre Channel driver utility.

                     For TL and XL2 HBAs, this option requires one parameter
                     and an optional count:

                     [-f] lb {plm|crpat|cjtpat} [count]

                     Here plm refers to physical link module or gigabit link
                     module, which builds the default payload for the
                     loopback frame.  If either crpat or cjtpat is used,
                     then the card builds specific payloads based on the
                     recommendations in Fibre Channel - Methodologies for
                     Jitter Specifications.  These patterns are designed to
                     generate bit patterns which stress the transmit and
                     receive channels of the card.  The self test then
                     involves sending a packet and receiving back the packet
                     within the adapter and checking its integrity.  Since
                     this self test is at the adapter level, no packet goes
                     on the fibre link.

                     All Fibre Channel HBAs (except TL and XL2) need to
                     specify two parameters.  Here is the syntax:

                     [-f] lb {ext|int} {crpat|cjpat} [count]

                     The first parameter should be either ext or int to
                     specify whether the loopback should be external or
                     internal, respectively.  The second parameter specifies
                     the loopback pattern.  Only crpat and cjtpat options
                     are supported for these cards.  Frames are looped back
                     at the single bit interface in the Internal loopback
                     mode.  For external loopback, frames are sent out and
                     received from the wire.  External loopback mode is
                     supported only in Loop topology.

                     NOTE: In the internal loopback mode, frames are also
                     sent out on the wire even though they are internally
                     looped back at the 1 Bit interface.  The receiver,
                     however, is turned off during this operation.
                     Therefore, it is not safe to run Internal loopback
                     tests when the fiber is connected to a Switch or Hub,
                     as the transmitted loopback frames can disrupt
                     operation on the SAN.

                     An optional third argument (count) can be specified for
                     the number of loopback packets to be sent.  If the
                     count option is not specified, one packet will be sent.

      get local

      get fabric

      get remote {all|remote-N-Port-ID}

                     This option is used to obtain Fibre Channel login
                     parameters of either the local port, the fabric port,
                     or a remote port.  The Fibre Channel HBAs do not
                     support the local option.  If the all argument is
                     specified for the remote option, login parameters and
                     current states of all N_Ports that the initiator is
                     aware of, are displayed.

      [-f] reset     This option is used to reset the HBA (or a single FC
                     port in case of multi-port HBAs).

                     WARNING: This is a DESTRUCTIVE test.  The reset
                     operation will result in aborting communication to all
                     nodes till the process is completed.

                     The -f option can be used to suppress the warning
                     message displayed by the Fibre Channel driver utility.

      [-f] bdr target-device_file

                     This option is used to issue a Bus Device Reset to
                     device.

                     WARNING:  This is a DESTRUCTIVE test.

                     The -f option can be used to suppress the warning
                     message displayed by the Fibre Channel driver utility.

                     This option resets the target, clearing all commands,
                     without doing any checks.

      read_cr        This option can be used to read all of the readable
                     registers on the card and format the detailed
                     information.

      stat [-s]      This option is used to obtain detailed statistics
                     maintained by the driver.  An optional argument -s can
                     be specified to obtain a shortened version of the
                     statistics maintained by the driver.  Generally, the
                     link statistics for the HBA port is displayed.

      clear_stat     This option is used to clear the statistics maintained
                     by the driver.

      nsstat         This option is used to obtain detailed nameserver
                     statistics maintained by the driver.

      clear_nsstat   This option is used to clear the nameserver statistics
                     maintained by the driver.

      devstat {all|remote-N-Port-ID}
                     This option is used to obtain detailed statistics
                     associated with each N_Port that this N_Port has
                     communicated with.

                     If the remote-N-Port-ID is specified, then the
                     statistics associated with that N_Port are displayed.
                     If the all option is specified, statistics associated
                     with all N_Ports that the initiator has been able to
                     communicate with are displayed.  Along with the
                     statistics for each N_Port, it also displays the
                     loop_id (in Private Loop) and the nport_id (in Fabric).

      clear_devstat {all|remote-N-Port-ID}
                     This option is used to clear the statistics associated
                     with a target.

                     If the remote-N-Port-ID is specified, then the
                     statistics associated with that N_Port are cleared.  If
                     the all option is specified, statistics associated with
                     all valid N_Port_IDs are cleared.

      replace_dsk    OBSOLETED.  Starting with HP-UX 11i Version 3, this
                     option is no longer supported.

                     On releases prior to HP-UX 11i Version 3, the Fibre
                     Channel Tachyon TL, Tachyon TL2 and FCD drivers
                     implemented an authentication mechanism to protect
                     against accidental data corruption in case of the
                     replacement of devices.  This mechanism prevented I/O
                     transfer when the target port Worldwide name (WWN)
                     changed for the same remote N-Port-Id.  The replace_dsk
                     option was used to validate replacement of the disk by
                     associating the new WWN with the remote N-Port-Id.
                     Starting with HP-UX 11i Version 3, this authentication
                     mechanism has been replaced by an enhanced mechanism
                     based on the LUN Worldwide Identifier (WWID).  Instead
                     of the fcmsutil replace_dsk command, use the scsimgr
                     commands, replace_wwid and replace_leg_dsf, to validate
                     the replacement of devices.  See the scsimgr(1M)
                     manpage for more information.

      [-f] disable   This option is used to disable the card.

                     WARNING:  This is a DESTRUCTIVE test and communication
                     to all nodes will be terminated.

                     The -f option can be used to suppress the warning
                     message displayed by the Fibre Channel driver utility.

                     This option is typically used when a hardware problem
                     cannot be resolved and is interfering with system
                     performance.

      enable         This option is used to enable the card, typically when
                     a previous hardware problem has been resolved.

      [-k] ns_query_ports
                     This option is used to query the name server and get
                     the list of nports for the Fibre Channel driver.

                     The -k option is used to get the list of nports cached
                     in the driver query buffer.  The name server will not
                     be queried in this case.

      [-f] dump_current_state
                     This option is used to force the driver and firmware to
                     dump their current state information and other data
                     structures.

                     WARNING:  This is a DESTRUCTIVE operation.  This might
                     result in failure of current I/O requests.

                     The -f option can be used to suppress the warning
                     message displayed by the Fibre Channel driver utility.

                     The dump data will be saved in the /tmp directory.  The
                     firmware dump will be stored in a file named FC-
                     driverfw_date-timestamp.dmp and the driver dump will be
                     saved in a file named FC-driverdrv_date-timestamp.dmp.

      dump_saved_state
                     This option is used to retrieve firmware and driver
                     dump saved in the driver memory.  The driver initiates
                     a dump when an internal error is encountered.  Internal
                     errors could be either due to firmware hang or to an
                     irrecoverable error in the firmware or hardware.  The
                     dump files will be saved in the /tmp directory.  The
                     firmware dump will be stored in a file named FC-
                     driverfw_date-timestamp.dmp and the driver dump will be
                     saved in a file named FC-driverdrv_date-timestamp.dmp.
                     These dumps should be sent to HP for further analysis
                     of the problem.

                     NOTE:  The driver does not save any new dumps, until
                     the previously saved dump is retrieved with this
                     option.  The availability of a saved dump can be
                     checked by running fcmsutil device_file.

      dump_nvram     This option is used to display the contents of NVRAM on
                     the adapter.

      rom_fw_update ROM-firmware-file
                     This option is used to update the ROM firmware stored
                     in card's FLASH ROM.

                     WARNING:  This is a DESTRUCTIVE operation.  Using this
                     option may result in failure of current I/O requests.

                     This option requires the name of a binary image file
                     that contains the updated firmware.  This operation
                     should only be performed by qualified personnel.
                     Failure to successfully complete the firmware update
                     may result in adapter and/or system failure in case the
                     boot disks are accessed through this card.

      efi_drv_update EFI-Driver-file
                     This option is used to update the EFI driver stored in
                     card's FLASH ROM.

                     WARNING:  This is a DESTRUCTIVE operation.  Using this
                     option may result in failure of current IO requests.

                     This option requires the name of a binary image file
                     that contains the EFI driver.  This operation should
                     only be performed by qualified personnel.  Failure to
                     successfully complete the EFI driver update may result
                     in adapter and/or system boot up failure if the boot
                     disks are accessed through this card.

      [-f] set_int_delay
                     This option is used to set the interrupt delay mode and
                     value, or to turn off interrupt delay.  Settings made
                     using this option are not persistent across reboots.

                     WARNING:  This is a DESTRUCTIVE operation and will
                     abort communication to all target devices until the
                     process is completed.

                     The complete syntax for this command is:

                     [-f] set_int_delay {off | [-z {5 | 6}] value}

                     The -f option can be used to suppress the warning
                     message.

                     The off option turns off interrupt delay.

                     The interrupt delay mode, also known as Zero Interrupt
                     Operation (ZIO) mode, is set using the -z option.
                     There are two interrupt delay modes available: 5 and 6.
                     Mode 5 delays every interrupt by the interrupt delay
                     period.  Mode 6 delays an interrupt unless there are no
                     active I/Os in the HBA port, in which case the
                     interrupt is generated immediately.  If the -z option
                     is not specified, then mode 6 is used by default.  The
                     interrupt delay period is calculated from the interrupt
                     delay value using the formula:

                     value * 200 microseconds

      get_int_delay  This option displays the current interrupt delay
                     settings for the HBA port.

      sfp            This option is used to display diagnostics information
                     from the card's optical transceiver.  It includes
                     information from the SFF-8472 specification such as
                     cable lengths, current temperature, voltage, transmit
                     and receive power, TX bias, as well as other data.

                     NOTE:  This option is only supported by 4Gb/s capable
                     Fibre Channel cards.

 EXAMPLES
      Print the remote port parameters using the get remote option if the
      driver is idle.  In this example, /dev/td1 is the device file and
      /dev/rdsk/c27t0d0 is the respective raw disk file.

           fcmsutil /dev/td1 get remote 0x98 &lt; /dev/rdsk/c27t0d0

      Print a short listing of the statistics maintained by the driver, with
      /dev/td1 as the device file.

           fcmsutil /dev/td1 stat -s

      Send 5 echo packets of 200 bytes each to a remote N_Port with loop_id
      4, with /dev/td1 as the device file.

           fcmsutil /dev/td1 echo -l 4 200 5

      Print a short listing of the statistics of the device whose remote-N-
      Port-ID is 0x02ae4 and with /dev/td1 as the device file.

           fcmsutil /dev/td1 devstat 0x02ae4

      Clear the device statistics of the device whose wwn is
      0x100000e002219f45 and with /dev/fcd2 as the device file.

           fcmsutil  /dev/fcd2 clear_devstat -w 0x100000e002219f45

      Perform a Internal loopback test, sending 1000 packets with /dev/fcd2
      as the device file.

           fcmsutil /dev/fcd2 lb int crpat 1000

      Display diagnostics information from the HBA's optical transceiver
      with /dev/fcd2 as the device file.

           fcmsutil /dev/fcd2 sfp

 SEE ALSO
      ioscan(1M), privileges(5).

 AUTHOR
      /opt/fcms/bin/fcmsutil was developed by HP.

'''
import command
import fptools
from fptools import comp, identity, methodcaller
from collections import namedtuple
import re
from itertools import ifilter, imap
from iteratortools import second

#Descriptor for `fcmsutil <device_filename>` command result
FcmsutilDescriptor = namedtuple('FcmsutilDescriptor',
                                  ('vendor_id', 'device_id',
                                   'pci_subsystem_vendor_id',
                                   'pci_subsystem_id',
                                   'pci_mode', 'isp_code_verison',
                                   'isp_chip_version', 'topology',
                                   'link_speed', 'local_n_port_id',
                                   'previous_n_port_id',
                                   # PRIVATE_LOOP topology relevant
                                   'local_loop_id',
                                   'n_port_node_world_wide_name',
                                   'n_port_port_world_wide_name',
                                   'switch_port_world_wide_name',
                                   'switch_node_world_wide_name',
                                   'n_port_symbolic_port_name',
                                   'n_port_symbolic_node_name',
                                   'driver_state', 'hardware_path',
                                   'maximum_frame_size',
                                   'driver_firmware_dump_available',
                                   'driver_firmware_dump_timestamp',
                                   'type', 'npiv_supported',
                                   'driver_version'
                                   ))


def parse_fcmsutil(lines):
    '''parses `fcmsutil <device_filename>` command output returning the descriptor object

    @param lines: output of `fcmsutil <device_filename>` command splited by lines
    @type lines: list of str or unicode
    @return: descriptor of fcmsutil command output or None on parse failure
    @rtype: FcmsutilDescriptor
    '''
    separator = '='
    sep_pattern = re.compile('\s*%s\s*' % separator)
    split_by_sep = fptools.comp(second, sep_pattern.split, fptools.methodcaller('strip'))

    lines = ifilter(identity, lines)
    values = map(split_by_sep, lines)
    topology_index = 7
    if len(values) > 7 and not values[topology_index] == 'PRIVATE_LOOP':
        values.insert(11, None)
    if len(values) == 26:
        return FcmsutilDescriptor(*values)


#Descriptor for `fcmsutil <device_filename> vpd` command result
FcmsutilVpdOptionDescriptor = namedtuple('FcmsutilVpdOptionDescriptor',
                                            ('product_description',
                                             'part_number',
                                             'engineering_date_code',
                                             'part_serial_number',
                                             'misc_information',
                                             'mfd_date', 'mfd_id', 'check_sum',
                                             'efi_version',
                                             'rom_firmware_version',
                                             'bios_version', 'fcode_version',
                                             'asset_tag'))


def parse_vpd_option(lines):
    '''parses `fcmsutil <device_filename> vpd` command output returning the descriptor object

    @param lines: output of `fcmsutil <device_filename> vpd` command splited by lines
    @type lines: list of str or unicode
    @return: descriptor of fcmsutil command output or None on parse failure
    @rtype: FcmsutilVpdOptionDescriptor
    '''
    lines = lines[3:]
    separator = '\:'
    sep_pattern = re.compile('\s*%s\s*' % separator)
    split_by_sep = fptools.comp(second, sep_pattern.split, fptools.methodcaller('strip'))

    lines = ifilter(identity, lines)
    values = map(split_by_sep, lines)
    if len(values) == 13:
        return FcmsutilVpdOptionDescriptor(*values)



#Descriptor for `fcmsutil <device_filename> vpd` command result
RemoteOptionDescriptor = namedtuple('RemoteOptionDescriptor',
                                            ('target_n_port_id',
                                             'target_loop_id',
                                             'target_state',
                                             'symbolic_port_name',
                                             'symbolic_node_name',
                                             'port_type',
                                             'fcp_2_support',
                                             'target_port_wwn',
                                             'target_node_wwn',
                                             ))


def parse_remote_all_option(lines):
    '''parses `fcmsutil <device_filename> remote all` command output returning the descriptor object

    @param lines: output of `fcmsutil <device_filename> remote all` command splited by lines
    @type lines: list of str or unicode
    @return: descriptor of fcmsutil command output or None on parse failure
    @rtype: list[RemoteOptionDescriptor]
    '''
    result = []
    if len(lines) > 1:
        separator = '='
        sep_pattern = re.compile('\s*%s\s*' % separator)
        split_by_sep = fptools.comp(sep_pattern.split, methodcaller('strip'))

        lines = ifilter(identity, lines)

        grouped = []
        _kwargs = {}
        for keyval in imap(split_by_sep, lines):
            if len(keyval) == 2:
                key, value = keyval
                if key in _kwargs:
                    grouped.append(_kwargs)
                    _kwargs = {}
                _kwargs[key] = value
        grouped.append(_kwargs)

        for item in grouped:
            target_n_port_id = item.get('Target N_Port_id is')
            target_loop_id = item.get('Target Loop_id is')
            target_state = item.get('Target state')
            symbolic_port_name = item.get('Symbolic Port Name')
            symbolic_node_name = item.get('Symbolic Node Name')
            port_type = item.get('Port Type')
            fcp_2_support = item.get('FCP-2 Support')
            target_port_wwn = item.get('Target Port World Wide Name')
            target_node_wwn = item.get('Target Node World Wide Name')

            result.append(RemoteOptionDescriptor(target_n_port_id,
                                                    target_loop_id,
                                                    target_state,
                                                    symbolic_port_name,
                                                    symbolic_node_name,
                                                    port_type,
                                                    fcp_2_support,
                                                    target_port_wwn,
                                                    target_node_wwn))

    return tuple(result)


def parse_remote_option(lines):
    raise NotImplementedError()


class Cmd(command.BaseCmd):
    '''A wrapper for `fcmsutil` command providing proper handling for each relevant option

    Note:
        the handler will throw command.ExecuteException if
            * the command returns non zero return code
            * the output is empty
    '''

    DEFAULT_HANDLERS = (command.BaseCmd.DEFAULT_HANDLERS +
                        (command.cmdlet.raiseOnNonZeroReturnCode,
                         command.cmdlet.raiseWhenOutputIsNone,
                         command.cmdlet.stripOutput,
                         fptools.methodcaller('splitlines'),
                         command.parser.clean_sudo_last_login_information_in_en,
                         ))

    def __init__(self, cmdline=None, device_filename=None, bin_path='fcmsutil', handler=None):
        '''
        @param cmdline: commandline to use for this command
        @type cmdline: str or unicode
        @param device_filename: the Fibre Channel device special file associated with the Fibre Channel HBA port.
          The device file has the format /dev/FC_driverX, where X is the instance
          number of the Fibre Channel HBA port, as reported by the ioscan output
        @type device_filename: str or unicode
        @param bin_path: path to fcmsutil binary
        @type bin_path: str ot unicode
        @param handler: handler to use for current command
        @type handler: callable[command.Result] -> ?. The default handler returns FcmsutilDescriptor object
        '''
        if not cmdline and not device_filename:
            raise ValueError('Neither cmdline nor device_filename are provided')
        cmdline = cmdline or ' '.join((bin_path, device_filename))
        handler = handler or comp(parse_fcmsutil, self.get_default_handler())
        command.BaseCmd.__init__(self, cmdline, handler=handler)

    def vpd(self):
        '''Create command with `fcmsutil <device_filename> vpd` cmdline and handler returning FcmsutilVpdOptionDescriptor object'''
        handler = comp(parse_vpd_option, self.get_default_handler())
        return Cmd(cmdline='%s vpd' % self.cmdline, handler=handler)

    def remote(self, remote_n_port_id='all'):
        '''Create command with `fcmsutil <device_filename> remote <remote_n_port_id>` cmdline and handler returning FcmsutilRemoteOptionDescriptor colelction'''
        parse = parse_remote_option
        if remote_n_port_id == 'all':
            parse = parse_remote_all_option
        handler = comp(parse, self.get_default_handler())
        return Cmd(cmdline='%s get remote %s' % (self.cmdline, remote_n_port_id), handler=handler)
