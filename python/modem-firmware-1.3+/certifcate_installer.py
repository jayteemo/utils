#!/usr/bin/env python3
#
# Copyright (c) 2021 Nordic Semiconductor ASA
#
# SPDX-License-Identifier: LicenseRef-Nordic-5-Clause

import argparse
import sys
import time
import serial
import platform
import rtt_interface
from serial.tools import list_ports
from colorama import init, Fore, Back, Style
from enum import Enum

CMD_TERM_DICT = {'NULL': '\0',
                 'CR':   '\r',
                 'LF':   '\n',
                 'CRLF': '\r\n'}
# 'CR' is the default termination value for the at_host library in the nRF Connect SDK
cmd_term_key = 'CR'
is_macos = platform.system() == 'Darwin'
is_windows = platform.system() == 'Windows'
is_linux = platform.system() == 'Linux'
full_encoding = 'mbcs' if is_windows else 'ascii'
lf_done = False
plain = False
verbose = False
serial_timeout = 1
aws_ca  = "-----BEGIN CERTIFICATE-----\nMIIDQTCCAimgAwIBAgITBmyfz5m/jAo54vB4ikPmljZbyjANBgkqhkiG9w0BAQsF\nADA5MQswCQYDVQQGEwJVUzEPMA0GA1UEChMGQW1hem9uMRkwFwYDVQQDExBBbWF6\nb24gUm9vdCBDQSAxMB4XDTE1MDUyNjAwMDAwMFoXDTM4MDExNzAwMDAwMFowOTEL\nMAkGA1UEBhMCVVMxDzANBgNVBAoTBkFtYXpvbjEZMBcGA1UEAxMQQW1hem9uIFJv\nb3QgQ0EgMTCCASIwDQYJKoZIhvcNAQEBBQADggEPADCCAQoCggEBALJ4gHHKeNXj\nca9HgFB0fW7Y14h29Jlo91ghYPl0hAEvrAIthtOgQ3pOsqTQNroBvo3bSMgHFzZM\n9O6II8c+6zf1tRn4SWiw3te5djgdYZ6k/oI2peVKVuRF4fn9tBb6dNqcmzU5L/qw\nIFAGbHrQgLKm+a/sRxmPUDgH3KKHOVj4utWp+UhnMJbulHheb4mjUcAwhmahRWa6\nVOujw5H5SNz/0egwLX0tdHA114gk957EWW67c4cX8jJGKLhD+rcdqsq08p8kDi1L\n93FcXmn/6pUCyziKrlA4b9v7LWIbxcceVOF34GfID5yHI9Y/QCB/IIDEgEw+OyQm\njgSubJrIqg0CAwEAAaNCMEAwDwYDVR0TAQH/BAUwAwEB/zAOBgNVHQ8BAf8EBAMC\nAYYwHQYDVR0OBBYEFIQYzIU07LwMlJQuCFmcx7IQTgoIMA0GCSqGSIb3DQEBCwUA\nA4IBAQCY8jdaQZChGsV2USggNiMOruYou6r4lK5IpDB/G/wkjUu0yKGX9rbxenDI\nU5PMCCjjmCXPI6T53iHTfIUJrU6adTrCC2qJeHZERxhlbI1Bjjt/msv0tadQ1wUs\nN+gDS63pYaACbvXy8MWy7Vu33PqUXHeeE6V/Uq2V8viTO96LXFvKWlJbYK8U90vv\no/ufQJVtMVT8QtPHRh8jrdkPSHCa2XV4cdFyQzR1bldZwgJcJmApzyMZFo6IQ6XU\n5MsI+yMRQ+hDKXJioaldXgjUkK642M4UwtBV8ob2xJNDd2ZhwLnoQdeXeGADbkpy\nrqXRfboQnoZsG4q5WTP468SQvvG5\n-----END CERTIFICATE-----\n"
coap_ca = "-----BEGIN CERTIFICATE-----\nMIIBjzCCATagAwIBAgIUOEakGUS/7BfSlprkly7UK43ZAwowCgYIKoZIzj0EAwIw\nFDESMBAGA1UEAwwJblJGIENsb3VkMB4XDTIzMDUyNDEyMzUzMloXDTQ4MTIzMDEy\nMzUzMlowFDESMBAGA1UEAwwJblJGIENsb3VkMFkwEwYHKoZIzj0CAQYIKoZIzj0D\nAQcDQgAEPVmJXT4TA1ljMcbPH0hxlzMDiPX73FHsdGM/6mqAwq9m2Nunr5/gTQQF\nMBUZJaQ/rUycLmrT8i+NZ0f/OzoFsKNmMGQwHQYDVR0OBBYEFGusC7QaV825v0Ci\nqEv2m1HhiScSMB8GA1UdIwQYMBaAFGusC7QaV825v0CiqEv2m1HhiScSMBIGA1Ud\nEwEB/wQIMAYBAf8CAQAwDgYDVR0PAQH/BAQDAgGGMAoGCCqGSM49BAMCA0cAMEQC\nIH/C3yf5aNFSFlm44CoP5P8L9aW/5woNrzN/kU5I+H38AiAwiHYlPclp25LgY8e2\nn7e2W/H1LXJ7S3ENDBwKUF4qyw==\n-----END CERTIFICATE-----\n"
prov_ca = "-----BEGIN CERTIFICATE-----\nMIIBUDCB96ADAgECAgkA/YgJ9vjCE48wCgYIKoZIzj0EAwIwIjEgMB4GA1UEAwwX\nZGV2LW5yZi1wcm92aXNpb25pbmctY2EwHhcNMjMwMTA5MTIwNDQ3WhcNMzMwMTA2\nMTIwNDQ3WjAiMSAwHgYDVQQDDBdkZXYtbnJmLXByb3Zpc2lvbmluZy1jYTBZMBMG\nByqGSM49AgEGCCqGSM49AwEHA0IABFfKcaEkRik+3dPO1yQRYQ/NzXgt6rxHr//D\nq4jDycMJx4x5VUWX65+50j9ebLGKwFlXI0uhfLrCI1ftOrrHfbujFjAUMBIGA1Ud\nEwEB/wQIMAYBAf8CAQEwCgYIKoZIzj0EAwIDSAAwRQIgVLCesd2h1XttBp6jKsx2\nnzlrvfWqkOUdOgk0Wfy93uUCIQCkE3HlEXbaV9HgALzFdIV1Vk0emb2+zpwA4VrH\nPDi0Aw==\n-----END CERTIFICATE-----\n"
IMEI_LEN = 15

def parse_args():
    global verbose

    parser = argparse.ArgumentParser(description="Certificate Installer",
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--coap",
                        help="Install the CoAP server root CA cert in addition to the AWS root CA cert",
                        action='store_true', default=False)
    parser.add_argument("--prov",
                        help="Install the nrf_provisioning root CA cert",
                        action='store_true', default=False)
    parser.add_argument("-S", "--sectag", type=int,
                        help="integer: Security tag to use", default=16842753)
    parser.add_argument("-d", "--delete",
                        help="bool: Delete sectag from modem first",
                        action='store_true', default=False)
    parser.add_argument("--term", type=str,
                        help="AT command termination:" + "".join([' {}'.format(k) for k, v in CMD_TERM_DICT.items()]),
                        default=cmd_term_key)
    parser.add_argument("-v", "--verbose",
                        help="bool: Make output verbose",
                        action='store_true', default=False)
    parser.add_argument("-P", "--plain",
                        help="bool: Plain output (no colors)",
                        action='store_true', default=False)
    # Serial options
    parser.add_argument("--port", type=str,
                        help="Specify which serial port to open, otherwise pick from list",
                        default=None)
    parser.add_argument("-A", "--all",
                        help="List ports of all types, not just Nordic devices",
                        action='store_true', default=False)
    parser.add_argument("--xonxoff",
                        help="Enable software flow control for serial connection",
                        action='store_true', default=False)
    parser.add_argument("--rtscts_off",
                        help="Disable hardware (RTS/CTS) flow control for serial connection",
                        action='store_true', default=False)
    parser.add_argument("--dsrdtr",
                        help="Enable hardware (DSR/DTR) flow control for serial connection",
                        action='store_true', default=False)
    # RTT options
    parser.add_argument("--rtt",
                        help="Use RTT instead of serial. Requires device run Modem Shell sample application configured with RTT overlay",
                        action='store_true', default=False)
    parser.add_argument("--jlink_sn", type=int,
                        help="Serial number of J-Link device to use for RTT; optional",
                        default=None)
    parser.add_argument("--mosh_rtt_hex", type=str, help="Optional filepath to RTT enabled Modem Shell hex file. If provided, device will be erased and programmed",
                        default="")
    args = parser.parse_args()
    verbose = args.verbose
    return args

def ensure_lf(line):
    global lf_done
    done = lf_done
    lf_done = True
    return '\n' + line if not done else line

def local_style(line):
    return ensure_lf(Fore.CYAN + line
                     + Style.RESET_ALL) if not plain else line

def hivis_style(line):
    return ensure_lf(Fore.MAGENTA + line
                     + Style.RESET_ALL) if not plain else line


def send_style(line):
    return ensure_lf(Fore.BLUE + line
                     + Style.RESET_ALL) if not plain else line

def error_style(line):
    return ensure_lf(Fore.RED + line + Style.RESET_ALL) if not plain else line

def ask_for_port(selected_port, list_all):
    """
    Show a list of ports and ask the user for a choice, unless user specified
    a specific port on the command line. To make selection easier on systems
    with long device names, also allow the input of an index.
    """
    ports = []
    dev_types = []
    usb_patterns = [(r'THINGY91', 'Thingy:91', False),
                    (r'PCA20035', 'Thingy:91', False),
                    (r'0009600',  'nRF9160-DK', False)]
    if selected_port == None and not list_all:
        pattern = r'SER=(' + r'|'.join(name[0] for name in usb_patterns) + r')'
        print(local_style('Available ports:'))
    else:
        pattern = r''

    port_num = 1
    for n, (port, desc, hwid) in enumerate(sorted(list_ports.grep(pattern)), 1):

        if not is_macos:
            # if a specific port is not requested, filter out ports with
            # LOCATION in hwid that do not end in '.0' because these are
            # usually not the logging or shell ports
            if selected_port == None and not list_all and 'LOCATION' in hwid:
                if hwid[-2] != '.' or hwid[-1] != '0':
                    if verbose:
                        print(local_style('Skipping: {:2}: {:20} {!r} {!r}'.
                                          format(port_num, port, desc, hwid)))
                    continue
        else:
            # if a specific port not requested, filter out ports whose /dev
            # does not end in a 1
            if selected_port == None and not list_all and port[-1] != '1':
                if verbose:
                    print(local_style('Skipping: {:2}: {:20} {!r} {!r}'.
                                      format(port_num, port, desc, hwid)))
                continue

        name = ''
        for nm in usb_patterns:
            if nm[0] in hwid:
                name = nm[1]
                break

        if selected_port != None:
            if selected_port == port:
                return port
        else:
            print(local_style('{:2}: {:20} {:17}'.format(port_num, port, name)))
            if verbose:
                print(local_style('  {!r} {!r}'.format(desc, hwid)))

            ports.append(port)
            port_num += 1

    if len(ports) == 0:
        sys.stderr.write(error_style('No device found\n'))
        return None
    if len(ports) == 1:
        return ports[0]
    while True:
        port = input('--- Enter port index: ')
        try:
            index = int(port) - 1
            if not 0 <= index < len(ports):
                sys.stderr.write(error_style('--- Invalid index!\n'))
                continue
        except ValueError:
            pass
        else:
            port = ports[index]
        return port

def write_line(line, hidden = False):
    global cmd_term_key
    if not hidden:
        print(send_style('-> {}'.format(line)))
    if ser:
        ser.write(bytes((line + CMD_TERM_DICT[cmd_term_key]).encode('utf-8')))
    elif rtt:
        rtt_interface.send_rtt(rtt, line + CMD_TERM_DICT[cmd_term_key])

def wait_for_prompt(val1=None, val2=None, timeout=15, store=None):
    global lf_done
    found = False
    retval = False
    output = None

    if ser:
        ser.flush()
    else:
        rtt_lines = rtt_interface.readlines_at_rtt(rtt, timeout)

    while not found and timeout != 0:
        if ser:
            line = ser.readline()
        else:
            if len(rtt_lines) == 0:
                break
            line = rtt_lines.pop(0).encode()


        if line == b'\r\n':
            # Skip the initial CRLF (see 3GPP TS 27.007 AT cmd specification)
            continue

        if line == None or len(line) == 0:
            if timeout > 0:
                timeout -= serial_timeout
            continue

        sys.stdout.write('<- ' + str(line, encoding=full_encoding))

        if val1 in line:
            found = True
            retval = True
        elif val2 != None and val2 in line:
            found = True
            retval = False
        elif store != None and (store in line or str(store) in str(line)):
            output = line

    lf_done = b'\n' in line
    if ser:
        ser.flush()
    if store != None and output == None:
        print(error_style('String {} not detected in line {}'.format(store,
                                                                    line)))

    if timeout == 0:
        print(error_style('Serial timeout'))

    return retval, output

def main():
    global plain
    global ser
    global rtt
    global cmd_term_key

    # initialize argumenst
    args = parse_args()
    plain = args.plain
    rtt = None

    if args.term in CMD_TERM_DICT.keys():
        cmd_term_key = args.term
    else:
        print(error_style('Invalid --term value provided, using default'))

    # initialize colorama
    if is_windows:
        init(convert = not plain)

    if verbose:
        print(local_style('OS detect: Linux={}, MacOS={}, Windows={}'.
                          format(is_linux, is_macos, is_windows)))

    if args.coap and args.prov:
        print(error_style('The options --coap and --prov are mutually exclusive'))
        sys.exit(1)

    # Setup connection
    if args.rtt:
        cmd_term_key = 'CRLF'

        rtt = rtt_interface.connect_rtt(args.jlink_sn, args.mosh_rtt_hex)
        if not rtt:
            sys.stderr.write(error_style('Failed connect to device via RTT'))
            sys.exit(2)

        if not rtt_interface.enable_at_cmds_mosh_rtt(rtt):
            sys.stderr.write(error_style('Failed to enable AT commands via RTT'))
            sys.exit(3)
        ser = None
    else:
        # get a serial port to use
        port = ask_for_port(args.port, args.all)
        if port == None:
            sys.exit(4)

        print(local_style('Opening port {}...'.format(port)))

        # try to open the serial port
        try:
            ser = serial.Serial(port, 115200, xonxoff= args.xonxoff, rtscts=(not args.rtscts_off),
                                dsrdtr=args.dsrdtr, timeout=serial_timeout)
            ser.reset_input_buffer()
            ser.reset_output_buffer()
        except serial.serialutil.SerialException:
            sys.stderr.write(error_style('Port could not be opened; not a device, or open already\n'))
            sys.exit(5)

    # prepare modem so we can interact with security keys
    print(local_style('Disabling LTE and GNSS...'))
    write_line('AT+CFUN=4')

    retval = wait_for_prompt(b'OK')
    if not retval:
        print(error_style('Unable to communicate'))
        sys.exit(6)

    # get the IMEI
    write_line('AT+CGSN')
    retval, output = wait_for_prompt(b'OK', b'ERROR', store=b'\r\n')
    if not retval:
        print(error_style('Failed to obtain IMEI'))
        sys.exit(7)

    # display the IMEI for reference
    imei = str(output.decode("utf-8"))[:IMEI_LEN]
    print(hivis_style('Device IMEI: ' + imei))

    # get the modem firmware version
    write_line('AT+CGMR')
    retval, output = wait_for_prompt(b'OK', b'ERROR', store=b'\r\n')
    if not retval:
        print(error_style('Failed to obtain modem FW version'))
        cleanup()
        sys.exit(8)
    # display version for reference
    mfw_ver = str(output.decode("utf-8")).rstrip('\r\n')
    print(hivis_style('Modem FW Version: ' + mfw_ver))

    # delete the root CA, an error probably means the slot was already empty
    if args.delete:
        print(local_style('Deleting root CA in sectag {}...'.format(args.sectag)))
        write_line('AT%CMNG=3,{},0'.format(args.sectag))
        wait_for_prompt(b'OK', b'ERROR')

    # write to AWS CA modem
    print(local_style('Writing AWS CA to modem...'))
    if args.coap and not args.prov:
        modem_ca = coap_ca + aws_ca
    elif args.prov and not args.coap:
        modem_ca = prov_ca
    else:
        modem_ca = aws_ca

    write_line('AT%CMNG=0,{},0,"{}"'.format(args.sectag, modem_ca))
    wait_for_prompt(b'OK', b'ERROR')
    time.sleep(1)

    if rtt:
        rtt.close()

if __name__ == '__main__':
    main()
