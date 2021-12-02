#!/usr/bin/env python3
#
# Copyright (c) 2021 Nordic Semiconductor ASA
#
# SPDX-License-Identifier: LicenseRef-Nordic-5-Clause

import argparse
import csv
import sys
import platform
import os
from os import path
from os import makedirs
from colorama import init, Fore, Back, Style
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography import x509
import OpenSSL.crypto

MAX_DEV_ID_LEN = 64
MAX_CSV_ROWS = 1000

full_encoding = 'mbcs' if (platform.system() == 'Windows') else 'ascii'
lf_done = False
plain = False

def parse_args():
    parser = argparse.ArgumentParser(description="Create Device Credentials for Provisioning")
    parser.add_argument("-ca", type=str, required=True, help="Filepath to your CA cert PEM", default="")
    parser.add_argument("-ca_key", type=str, required=True, help="Filepath to your CA's private key PEM", default="")
    parser.add_argument("-c", type=str, required=True, help="2 character country code", default="")
    parser.add_argument("-cn", type=str, required=True, help="Common Name; use nRF Cloud device ID/MQTT client ID", default="")
    parser.add_argument("-st", type=str, help="State or Province", default="")
    parser.add_argument("-l", type=str, help="Locality", default="")
    parser.add_argument("-o", type=str, help="Organization", default="")
    parser.add_argument("-ou", type=str, help="Organizational Unit", default="")
    parser.add_argument("-e", "--email", type=str, help="E-mail address", default="")
    parser.add_argument("-dv", type=int, help="Number of days cert is valid", default=(10 * 365))
    parser.add_argument("-p", "--path", type=str, help="Path to save PEM files.", default="./")
    parser.add_argument("-f", "--fileprefix", type=str, help="Prefix for output files", default="")
    parser.add_argument("-nosave", help="Do not save device credentials as PEM", action='store_true', default=False)
    parser.add_argument("-csv", type=str, help="Filepath to provisioning CSV file", default="provision.csv")
    parser.add_argument("-overwrite", help="When saving provisioning CSV, overwrite if file exists", action='store_true', default=False)
    parser.add_argument("-tags", type=str, help="Pipe (|) delimited device tags; enclose in double quotes", default="")
    parser.add_argument("-subtype", type=str, help="Custom device type", default='')
    parser.add_argument("-fwtypes", type=str,
                        help="""
                        Pipe (|) delimited firmware types for FOTA of the set
                        {APP MODEM BOOT SOFTDEVICE BOOTLOADER}; enclose in double quotes
                        """, default="MODEM")
    args = parser.parse_args()
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

def write_file(pathname, filename, bytes):
    """
    save bytes to file
    """

    if not path.isdir(pathname):
        try:
            makedirs(pathname, exist_ok=True)
        except OSError as e:
            raise RuntimeError("Error creating file path")

    full_path = path.join(pathname, filename)

    try:
        f = open(full_path, "wb")
    except OSError:
        raise RuntimeError("Error opening file: " + full_path)

    f.write(bytes)
    print("File created: " + path.abspath(f.name))
    f.close()

    return

def check_provisioning_csv(csv_filename, dev_id):
    exists = False
    row_count = 0

    with open(csv_filename) as csvfile:
        prov = csv.reader(csvfile, delimiter=',')

        for row in prov:
            row_count += 1
            # First column is the device ID
            if row[0] == dev_id:
                exists = True
                print("Device \'{}\' exists in CSV file: ".format(dev_id))

        csvfile.close()

    return exists, row_count

def save_provisioning_csv(csv_filename, append, dev_id, sub_type, tags, fw_types, dev):
    mode = 'a' if append else 'w'

    try:
        with open(csv_filename, mode, newline='\n') as csvfile:
            csv_writer = csv.writer(csvfile, delimiter=',', lineterminator='\n',
                                    quoting=csv.QUOTE_MINIMAL)
            csv_writer.writerow([dev_id, sub_type, tags, fw_types,
                                 str(dev, encoding=full_encoding)])
        print(local_style('File saved'))
    except OSError:
        print(error_style('Error opening file {}'.format(csv_filename)))

def load_ca(ca_pem_filepath):

    try:
        ca_file = open(ca_pem_filepath, "rt")
    except OSError:
        raise RuntimeError("Error opening file: " + ca_pem_filepath)

    file_bytes  = ca_file.read()
    ca_file.close()

    try:
        ca_out = OpenSSL.crypto.load_certificate(OpenSSL.crypto.FILETYPE_PEM, file_bytes)

    except OpenSSL.crypto.Error:
        raise RuntimeError("Error loading PEM file " + ca_pem_filepath)

    return ca_out

def load_ca_key(ca_key_filepath):

    try:
        ca_key_file = open(ca_key_filepath, "rt")
    except OSError:
        raise RuntimeError("Error opening file: " + ca_key_filepath)

    file_bytes  = ca_key_file.read()
    ca_key_file.close()

    key_out = OpenSSL.crypto.load_privatekey(OpenSSL.crypto.FILETYPE_PEM, file_bytes)

    return key_out

def create_device_cert(dv, csr, pub_key, ca_cert, ca_key):
    device_cert = OpenSSL.crypto.X509()
    serial_no = x509.random_serial_number()
    device_cert.set_serial_number(serial_no)
    device_cert.gmtime_adj_notBefore(0)
    device_cert.gmtime_adj_notAfter(dv * 24 * 60 * 60)
    # use subject and public key from CSR
    device_cert.set_subject(csr.get_subject())
    device_cert.set_pubkey(pub_key)
    # sign with the CA
    device_cert.set_issuer(ca_cert.get_subject())
    device_cert.sign(ca_key, "sha256")
    return device_cert

def main():

    args = parse_args()

    if len(args.c) != 2:
        raise RuntimeError("Country code must be 2 characters")

    if not len(args.cn):
        raise RuntimeError("CN (device ID) must be a valid string")
    elif len(args.cn) > MAX_DEV_ID_LEN:
        raise RuntimeError("CN must not exceed {} characters".format(MAX_DEV_ID_LEN))

    dev_id = args.cn

    csv_filepath = os.path.abspath(args.csv)
    if not os.path.exists(os.path.dirname(csv_filepath)):
        raise RuntimeError("Path for CSV file does not exist: " + os.path.dirname(csv_filepath))

    csv_exists = os.path.isfile(csv_filepath)

    if csv_exists and not args.overwrite:
        dev_exists, csv_row_count = check_provisioning_csv(csv_filepath, dev_id)

        print(local_style("Provisioning CSV row count [max {}]: {}".format(MAX_CSV_ROWS, csv_row_count)))
        if csv_row_count >= 1000:
            raise RuntimeError("Provisioning CSV file is full")

        if dev_exists:
            raise RuntimeError("Device already exists in provisioning CSV file")

    ca_cert = load_ca(args.ca)
    ca_key = load_ca_key(args.ca_key)

    print(local_style("Creating device credentials..."))

    # create EC keypair
    private_key = ec.generate_private_key(ec.SECP256R1(), default_backend())
    public_key = private_key.public_key()
    # format to DER for loading into OpenSSL
    priv_der = private_key.private_bytes(encoding=serialization.Encoding.DER, format=serialization.PrivateFormat.PKCS8, encryption_algorithm=serialization.NoEncryption())
    pub_der = public_key.public_bytes(encoding=serialization.Encoding.DER, format=serialization.PublicFormat.SubjectPublicKeyInfo)
    # load into OpenSSL
    priv_key = OpenSSL.crypto.load_privatekey(OpenSSL.crypto.FILETYPE_ASN1, priv_der)
    pub_key = OpenSSL.crypto.load_publickey(OpenSSL.crypto.FILETYPE_ASN1, pub_der)

    # create a CSR
    csr = OpenSSL.crypto.X509Req()

    csr.set_version(0)
    csr.add_extensions([
        OpenSSL.crypto.X509Extension(b'keyUsage', True, b'digitalSignature, nonRepudiation, keyEncipherment, keyAgreement'),])

    # add subject info
    # country and common name are required
    csr.get_subject().C = args.c
    csr.get_subject().CN = dev_id

    if len(args.st):
        csr.get_subject().ST = args.st

    if len(args.l):
        csr.get_subject().L = args.l

    if len(args.o):
        csr.get_subject().O = args.o

    if len(args.ou):
        csr.get_subject().OU = args.ou

    if len(args.email):
        csr.get_subject().emailAddress = args.email

    csr.set_pubkey(pub_key)
    csr.sign(priv_key, 'sha256')

    # create a device cert
    device_cert = create_device_cert(args.dv, csr, pub_key, ca_cert, ca_key)
    # get device cert in PEM format
    dev = OpenSSL.crypto.dump_certificate(OpenSSL.crypto.FILETYPE_PEM, device_cert)

    if not args.nosave:
        # save device cert
        write_file(args.path, args.fileprefix + dev_id + "_crt.pem", dev)

        # save public key
        pub  = OpenSSL.crypto.dump_publickey(OpenSSL.crypto.FILETYPE_PEM, pub_key)
        write_file(args.path, args.fileprefix + dev_id + "_pub.pem", pub)

        # save private key
        priv = OpenSSL.crypto.dump_privatekey(OpenSSL.crypto.FILETYPE_PEM, priv_key)
        write_file(args.path, args.fileprefix + dev_id + "_prv.pem", priv)

    print(local_style('Adding device \'{}\' to provisioning CSV file...'.format(dev_id)))
    append = csv_exists and (not args.overwrite)
    save_provisioning_csv(csv_filepath,
                          append,
                          dev_id,
                          args.subtype,
                          args.tags,
                          args.fwtypes,
                          dev)

    return

if __name__ == '__main__':
    main()
