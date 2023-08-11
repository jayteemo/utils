#!/usr/bin/env python3
#
# Copyright (c) 2021 Nordic Semiconductor ASA
#
# SPDX-License-Identifier: LicenseRef-Nordic-5-Clause

import argparse
import sys
import requests
import csv
import time
import json
import requests
import os
import io
from os import path
from os import makedirs
from ast import literal_eval
from enum import Enum

class ProvisionResult(Enum):
    PERFORMED_SUCCESSFULLY = 0
    PERFORMED_WITH_ERRORS = 1
    PERFORMED_RESULTS_NOT_CONFIRMED = 2
    NOT_PERFORMED_NO_API_KEY = 4
    NOT_PERFORMED_BAD_FILE_PATH = 5
    NOT_PERFORMED_INVALID_CSV_FORMAT = 6
    NOT_PERFORMED_DEVICE_EXISTS = 7
    NOT_PERFORMED_DEV_CHK_FAILED = 8
    NOT_PERFORMED_PROVDEV_CALL_FAILED = 9

from modem_credentials_parser import write_file

DEV_STAGE_DICT = {'dev':     '.dev.',
                  'beta':    '.beta.',
                  'prod':    '.',
                  '':        '.',
                  'feature': '.feature.'}
dev_stage_key = 'prod'

API_URL_START = 'https://api.provisioning'
API_URL_END = 'nrfcloud.com/v1/'
api_url = API_URL_START + DEV_STAGE_DICT[dev_stage_key] + API_URL_END

ERR_FIND_FIRST_STR = "(1-based)]: "
ERR_FIND_END_STR = ".\"}"
MAX_CSV_ROWS = 1000
DEV_LIST_ID_IDX = 0
DEV_LIST_RES_IDX = 1
BULK_OP_REQ_ID = 'bulkOpsRequestId'
AUTH = 'Authorization'
BEARER = 'Bearer '
CLAIMED_DEV = 'claimed-devices'
PROV = 'provisioning'
CLAIM_TOK = 'claimToken'

def parse_args():
    parser = argparse.ArgumentParser(description="nRF Cloud DIaP",
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--apikey", type=str, required=True,
                        help="nRF Cloud API key", default="")
    parser.add_argument("--chk", action='store_true', default=False,
                        help="For single device provisioning, check if device exists before provisioning")
    parser.add_argument("--csv", type=str,
                        help="Filepath to provisioning CSV file", default="provision.csv")
    parser.add_argument("--res", type=str,
                        help="Filepath where the CSV-formatted provisioning result(s) will be saved", default="")
    parser.add_argument("--devinfo", type=str,
                        help="Optional filepath to device info CSV file containing device ID, installed modem FW version, and IMEI",
                        default=None)
    parser.add_argument("--set_mfwv",
                        help="Set the modem FW version in the device's shadow. Requires --devinfo.",
                        action='store_true', default=False)
    parser.add_argument("--name_imei",
                        help="Use the device's IMEI as the friendly name. Requires --devinfo.",
                        action='store_true', default=False)
    parser.add_argument("--name_prefix", type=str,
                        help="Prefix string for IMEI friendly name",
                        default=None)
    parser.add_argument("--stage", type=str,
                        help="Deployment stage; default is prod (blank)", default="")

    args = parser.parse_args()
    return args

def set_dev_stage(stage = ''):
    global api_url
    global dev_stage_key

    if stage in DEV_STAGE_DICT.keys():
        dev_stage_key = stage
        api_url = '{}{}{}'.format(API_URL_START, DEV_STAGE_DICT[dev_stage_key], API_URL_END)
    else:
        print('Invalid stage')

    return api_url

def get_auth_header(api_key):
    if not api_key:
        return None
    return  { AUTH : BEARER + api_key}

def claim_device(api_key, claim_token):
    global api_url
    req = '{}{}'.format(api_url, CLAIMED_DEV)
    payload = {CLAIM_TOK : claim_token}

    return requests.post(req, json=payload, headers=get_auth_header(api_key))

def unclaim_device(api_key, dev_uuid):
    global api_url

    req = '{}{}/{}'.format(api_url, CLAIMED_DEV, dev_uuid)

    return requests.delete(req, headers=get_auth_header(api_key))

def get_create_prov_cmd_req(dev_uuid):
    global api_url
    return '{}{}/{}/{}'.format(api_url, CLAIMED_DEV, dev_uuid, PROV)

def create_provisioning_cmd_client_cert(api_key, dev_uuid, cert_pem,
                                        description='Update client cert',
                                        sec_tag=16842753):
    global api_url

    payload = {}
    request = {}
    cert_obj = {}

    req = get_create_prov_cmd_req(dev_uuid)

    cert_obj['content'] = cert_pem
    cert_obj['secTag'] = sec_tag

    request['clientCertificate'] = cert_obj

    payload['description'] = description
    payload['request'] = request

    return requests.post(req, json=payload, headers=get_auth_header(api_key))

def create_provisioning_cmd_csr(api_key, dev_uuid, description='Generate CSR',
                                attributes='O=Nordic Semiconductor,L=Oslo,C=fi',
                                key_usage='101010000', sec_tag=16842753):
    global api_url

    payload = {}
    request = {}
    csr_obj = {}

    req = get_create_prov_cmd_req(dev_uuid)

    csr_obj['attributes'] = attributes
    csr_obj['keyUsage'] = key_usage
    csr_obj['secTag'] = sec_tag

    request['certificateSigningRequest'] = csr_obj

    payload['description'] = description
    payload['request'] = request

    return requests.post(req, json=payload, headers=get_auth_header(api_key))

def get_provisioning_cmd(api_key, dev_uuid, cmd_id):
    global api_url
    req = '{}{}/{}/{}/{}'.format(api_url, CLAIMED_DEV, dev_uuid, PROV, cmd_id)

    return requests.get(req, headers=get_auth_header(api_key))

def print_api_result(custom_text, api_result, print_response_txt):
    print("{}: {} - {}".format(custom_text, api_result.status_code, api_result.reason))
    if print_response_txt:
        print("Response: {}".format(api_result.text))

def main():
    return

if __name__ == '__main__':
    main()
