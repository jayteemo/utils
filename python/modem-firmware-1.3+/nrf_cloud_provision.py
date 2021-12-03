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

API_URL = "https://api.nrfcloud.com/v1/"
ERR_FIND_FIRST_STR = "(1-based)]: "
ERR_FIND_END_STR = ".\"}"
MAX_CSV_ROWS = 1000
DEV_LIST_ID_IDX = 0
DEV_LIST_RES_IDX = 1
BULK_OP_REQ_ID = "bulkOpsRequestId"

def parse_args():
    parser = argparse.ArgumentParser(description="nRF Cloud Device Provisioning",
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--apikey", type=str, required=True,
                        help="nRF Cloud API key", default="")
    parser.add_argument("--chk", action='store_true', default=False,
                        help="For single device provisioning, check if device exists before provisioning")
    parser.add_argument("--csv", type=str,
                        help="Filepath to provisioning CSV file", default="provision.csv")
    parser.add_argument("--res", type=str,
                        help="Filepath where the CSV-formatted provisioning result(s) will be saved", default="")

    args = parser.parse_args()
    return args

def get_bulk_ops_result(api_key, bulk_ops_req_id):
    hdr = {'Authorization': 'Bearer ' + api_key}
    req = API_URL + "bulk-ops-requests/" + bulk_ops_req_id
    return requests.get(req, headers=hdr)

def fetch_device(api_key, device_id):
    hdr = {'Authorization': 'Bearer ' + api_key}
    req = API_URL + "devices/" + device_id
    return requests.get(req, headers=hdr)

def provision_devices(api_key, csv_filepath):
    hdr = {'Authorization': 'Bearer ' + api_key,
           'content-type' : 'text/csv',
           'Accept-Encoding' : '*'}

    req = API_URL + "devices"

    with open(csv_filepath,'rb') as payload:
        api_result = requests.post(req, data=payload, headers=hdr)
        payload.close()
        return api_result

def print_api_result(custom_text, api_result, print_response_txt):
    print("{}: {} - {}".format(custom_text, api_result.status_code, api_result.reason))
    if print_response_txt:
        print("Response: {}".format(api_result.text))

def get_provisioning_results(api_key, bulk_ops_req_id):

    print("Fetching results for {}: {}".format(BULK_OP_REQ_ID, bulk_ops_req_id))

    while True:
        print("Waiting 5s...")
        time.sleep(5)

        api_result = get_bulk_ops_result(api_key, bulk_ops_req_id)

        if api_result.status_code != 200:
            print("Failed to fetch provisioning result")
            return None

        api_result_json = api_result.json()

        print("Provisioning status: " + api_result_json["status"])

        if api_result_json["status"] == "IN_PROGRESS" or api_result_json["status"] == "PENDING":
            continue

        return api_result


def parse_err_msg(err_str):

    # Until the error msg is fixed by the cloud, we have to do some extra parsing...
    # See IRIS-3758

    # Search for the end of the first item, which is just a general error msg
    err_begin_idx = err_str.find(ERR_FIND_FIRST_STR)

    # Find the end of the detailed error list, which has escaped quotes
    err_end_idx = err_str.rfind(ERR_FIND_END_STR)

    if err_begin_idx == -1 or err_end_idx == -1:
        print("Unhandled error response format")
        return

    # Inspect the first item for total number of reported errors
    err_begin_str = err_str[:err_begin_idx]
    err_cnt = 0
    for s in err_begin_str.split():
        if s.isdigit():
            err_cnt = int(s)
            break

    if err_cnt == 0:
        print("Warning: no errors reported")

    # Get the start of the detailed error list, which is after the first item
    err_json_str = err_str[ (err_begin_idx + len(ERR_FIND_FIRST_STR)) : err_end_idx]

    # Fix the escaped quotes
    err_json_str = literal_eval("'%s'" % err_json_str)

    # Return the error count and the json formatted error dict
    return err_cnt, json.loads(err_json_str)

def update_device_list_err(dev_list, err_dict):

    list_sz = len(dev_list)

    # Loop through the dictionary of errors
    for err_item in err_dict:

        # The key is the error text and the value is a json array (python list)
        # of indicies into the provisioning CSV file, and also the device list
        idx_list = err_dict[err_item]

        # Use the indicies to access the device list
        for dev_idx in idx_list:
            i = dev_idx -1
            if i >= list_sz:
                print("Reported device index out of range: {}".format(dev_idx))
                continue

            # Add the error message to the device list
            if len(err_item) == 0 or err_item == ' ':
                # In case of an empty error message...
                dev_list[i][DEV_LIST_RES_IDX] = 'ERROR_UNKNOWN'
            else:
                dev_list[i][DEV_LIST_RES_IDX] = err_item

    # Set status for devices without an error
    dev_list = update_device_list_ok(dev_list)

    return dev_list

def update_device_list_ok(dev_list):

    # Go through the list and add 'OK' to any devices without an error
    for dev in dev_list:
        if len(dev[DEV_LIST_RES_IDX]) == 0:
            dev[DEV_LIST_RES_IDX] = 'OK'

    return dev_list

def read_prov_csv(csv_filepath):
    device_list = []
    with open(csv_filepath) as csvfile:
        prov = csv.reader(csvfile, delimiter=',')
        row_count = sum(1 for row in prov)
        print("Rows in CSV file: " + str(row_count))

        if row_count > MAX_CSV_ROWS:
            print("CSV file contains {} rows; must not exceed {}".format(row_count, MAX_CSV_ROWS))
            csvfile.close()
            return None

        csvfile.seek(0)
        prov = csv.reader(csvfile, delimiter=',')

        for row in prov:
            # First column in each row is the device ID
            # Add a list to the list [ <device_id>, <result_string> ]
            device_list.append([row[0], ''])

        csvfile.close()

    return device_list

def save_or_print(results, result_filepath):
    # Save to file or print to console
    if result_filepath:
        write_file(os.path.dirname(result_filepath),
                   os.path.basename(result_filepath),
                   results.getvalue().encode('utf-8'))
    else:
        print(results.getvalue())

def save_results(bulk_results_json, err_cnt, dev_list, result_filepath):
    results = io.StringIO()

    # Write the data from the bulk ops status
    for k, v in bulk_results_json.items():
        results.write(k + ',' + v + '\n')

    results.write('Error count,' + str(err_cnt) + '\n')
    results.write('\n')

    if dev_list is not None:
        results.write('Device ID,Result' + '\n')
        # Write the items in the device list
        for dev_entry in dev_list:
            results.write(dev_entry[DEV_LIST_ID_IDX] + ',' +
                          dev_entry[DEV_LIST_RES_IDX] + '\n')
    else:
        results.write('Error output could not be accessed\n')

    save_or_print(results, result_filepath)

def save_bulk_ops_id(bulk_ops_req_id, result_filepath):
    results = io.StringIO()

    results.write('{},{}\n'.format(BULK_OP_REQ_ID, bulk_ops_req_id))
    results.write('Bulk operations result could not be accessed\n')

    save_or_print(results, result_filepath)

def do_provisioning(api_key, csv_in, res_out, do_check):

    if len(api_key) < 1:
        print("API key must be provided")
        return ProvisionResult.NOT_PERFORMED_NO_API_KEY

    result_filepath = ''
    if len(res_out):
        result_filepath = os.path.abspath(res_out)
        if not os.path.exists(os.path.dirname(result_filepath)):
            print("Path for result file does not exist: " + os.path.dirname(result_filepath))
            return ProvisionResult.NOT_PERFORMED_BAD_FILE_PATH

    csv_filepath = os.path.abspath(csv_in)
    if not os.path.exists(csv_filepath):
        print("CSV file does not exist: " + csv_filepath)
        return ProvisionResult.NOT_PERFORMED_BAD_FILE_PATH

    device_list = read_prov_csv(csv_filepath)
    if device_list is None:
        print("CSV file is not valid")
        return ProvisionResult.NOT_PERFORMED_INVALID_CSV_FORMAT

    device_list_len = len(device_list)
    print("Devices to be provisioned: " + str(device_list_len))

    if do_check and device_list_len == 1:
         # Get the device ID of the first (only) item in the list
        dev_id = device_list[0][DEV_LIST_ID_IDX]
        result = fetch_device(api_key, dev_id)

        if result.status_code == 404:
            print("Device \"{}\" does not yet exist, provisioning...".format(dev_id))
        elif result.status_code == 200:
            print("Device \"{}\" already provisioned".format(dev_id))
            return ProvisionResult.NOT_PERFORMED_DEVICE_EXISTS
        else:
            print_api_result("FetchDevice API call failed", result, True)
            return ProvisionResult.NOT_PERFORMED_DEV_CHK_FAILED

    elif do_check:
        print("More than one device in CSV file, ignoring chk flag")

    # Call the ProvisionDevices endpoint
    prov_result = provision_devices(api_key, csv_filepath)
    print_api_result("ProvisionDevices API call result", prov_result, True)

    if prov_result.status_code != 202:
        print("Provisioning failed")
        return ProvisionResult.NOT_PERFORMED_PROVDEV_CALL_FAILED

    # The response to a successful ProvisionDevices call will contain a bulk operations request ID
    bulk_req_id = prov_result.json()[BULK_OP_REQ_ID]

    # The device provisioning status is obtained through the FetchBulkOpsRequest endpoint
    bulk_results = get_provisioning_results(api_key, bulk_req_id)
    if bulk_results is None:
        print("Could not get results for {}: {}".format(BULK_OP_REQ_ID, bulk_req_id))
        save_bulk_ops_id(bulk_req_id, result_filepath)
        return ProvisionResult.PERFORMED_RESULTS_NOT_CONFIRMED

    err_count = 0
    bulk_results_json = bulk_results.json()

    if bulk_results_json["status"] == "FAILED":
        print("Failure during provisioning, downloading error summary...")

        # Errors are detailed in a JSON file, which must be downloaded separately
        error_results = requests.get(bulk_results_json["errorSummaryUrl"])

        if error_results.status_code == 200:
            # Parse the error message and update the device list
            err_count, err_json = parse_err_msg(error_results.text)
            device_list = update_device_list_err(device_list, err_json)
        else:
            print("Could not access error output: " + error_results.text)
            device_list = None

    elif bulk_results_json["status"] == "SUCCEEDED":
        # No errors, mark the devices as OK
        device_list = update_device_list_ok(device_list)
    else:
        print("Unhandled bulk ops status: {}".format(bulk_results_json["status"]))

    save_results(bulk_results_json, err_count, device_list, result_filepath)

    if err_count == 0:
        return ProvisionResult.PERFORMED_SUCCESSFULLY
    else:
        return ProvisionResult.PERFORMED_WITH_ERRORS

def main():

    if not len(sys.argv) > 1:
        raise RuntimeError("No input provided")

    args = parse_args()

    if not len(args.csv):
        raise RuntimeError("Invalid provisioning CSV file")

    do_provisioning(args.apikey, args.csv, args.res, args.chk)

    return

if __name__ == '__main__':
    main()