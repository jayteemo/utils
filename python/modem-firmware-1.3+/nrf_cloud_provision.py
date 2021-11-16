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

from modem_credentials_parser import write_file

API_URL = "https://api.dev.nrfcloud.com/v1/"
ERR_FIND_FIRST_STR = "(1-based)]: "
ERR_FIND_END_STR = ".\"}"
DEV_LIST_ID_IDX = 0
DEV_LIST_RES_IDX = 1

def parse_args():
    parser = argparse.ArgumentParser(description="nRF Cloud Device Provisioning",
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--apikey", type=str, help="nRF Cloud API key", default="")
    parser.add_argument("--chk", action='store_true', default=False,
                        help="For single device provisioning, check if device exists before provisioning.")
    parser.add_argument("--csv", type=str, required=True, help="Filepath to (input) provisioning CSV file", default="test_prov.csv")
    parser.add_argument("--res", type=str, help="Filepath where the CSV-formatted provisioning result(s) will be saved", default="")

    args = parser.parse_args()
    return args

def get_bulk_ops_result(api_key, bulk_ops_req_id):
    hdr = {'Authorization': 'Bearer ' + api_key}
    req = API_URL + "bulk-ops-requests/" + bulk_ops_req_id
    return requests.get(req, headers=hdr)

def parse_err_msg(err_str):

    # Until the error msg is fixed by the cloud, we have to do some extra parsing...

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

def update_device_list(dev_list, err_dict):

    list_sz = len(dev_list)

    # Loop through the dictionary of errors
    for err_item in err_dict:

        # The value is a json array (python list) of indicies
        idx_list = err_dict[err_item]

        # Use the indicies to access the device list
        for dev_idx in idx_list:
            i = dev_idx -1
            if i >= list_sz:
                print("Reported device index out of range: {}".format(dev_idx))
                continue

            # Add the error message to the device list
            if len(err_item) == 0 or err_item == ' ':
                dev_list[i][DEV_LIST_RES_IDX] = 'ERROR_UNKNOWN'
            else:
                dev_list[i][DEV_LIST_RES_IDX] = err_item

    # Go through the list and add OK to any devices without an error
    for dev in dev_list:
        if len(dev[DEV_LIST_RES_IDX]) == 0:
            dev[DEV_LIST_RES_IDX] = 'OK'

    return dev_list

def do_provisioning(api_key, csv_in, res_out, do_check):

    if len(api_key) < 1:
        raise RuntimeError("API key must be provided")

    result_filepath=''
    if len(res_out):
        result_filepath = os.path.abspath(res_out)
        if not os.path.exists(os.path.dirname(result_filepath)):
            raise RuntimeError("Path for result file does not exist: " +
                               os.path.dirname(result_filepath))

    csv_filepath = os.path.abspath(csv_in)
    if not os.path.exists(csv_filepath):
        raise RuntimeError("CSV file does not exist: " + csv_filepath)

    device_list = []
    row_count = 0

    with open(csv_filepath) as csvfile:
        prov = csv.reader(csvfile, delimiter=',')
        row_count = sum(1 for row in prov)
        print("Rows in CSV file: " + str(row_count))

        if row_count > 1000:
            print("CSV file contains " + row_count + "rows; must not exceed 1000")
            csvfile.close()
            return

        csvfile.seek(0)
        prov = csv.reader(csvfile, delimiter=',')

        for row in prov:
            # First row is the device ID
            # Add a list to the list [ <device_id>, <result_string> ]
            device_list.append([row[0], ''])

        csvfile.close()

    device_list_len = len(device_list)
    print("Devices to be provisioned: " + str(device_list_len))

    if do_check and device_list_len == 1:
        # Make an FetchDevice call to verify that the device doesn't already exist
        hdr = {'Authorization': 'Bearer ' + api_key}
        # Get the device ID of the first (only) item in the list
        dev_id = device_list[0][DEV_LIST_ID_IDX]
        req = API_URL + "devices/" + dev_id
        api_result = requests.get(req, headers=hdr)

        print("FetchDevice result: " + str(api_result.status_code))

        if api_result.status_code == 422:
            print("API call failed, invalid API key?")
            return
        elif api_result.status_code == 200:
            print("Device {} already provisioned".format(dev_id))
            return
        elif api_result.status_code != 404:
            print("API call failed")
            return

        print("Device {} does not yet exist, provisioning...".format(dev_id))

    elif do_check:
        print("More than one device in CSV file, ignoring chk flag")

    hdr = {'Authorization': 'Bearer ' + api_key,
           'content-type' : 'text/csv',
           'Accept-Encoding' : '*'}

    req = API_URL + "devices"

    with open(csv_filepath,'rb') as payload:
        api_result = requests.post(req, data=payload, headers=hdr)
        payload.close()

    print("ProvisionDevices result: " + str(api_result.status_code))

    if api_result.status_code != 202:
        print("Provisioning failed:\n\t" + api_result.text)
        return

    api_result_json = api_result.json()
    bulk_req_id = api_result_json["bulkOpsRequestId"]
    print("Fetching result for bulkOpsRequestId = " + bulk_req_id)

    while True:
        print("Waiting 5s...")
        time.sleep(5)
        api_result = get_bulk_ops_result(api_key, bulk_req_id)

        if api_result.status_code != 200:
            print("Failed to fetch provisioning result")
            return

        api_result_json = api_result.json()
        status = api_result_json["status"]
        print("Provisioning status: " + status)

        if status == "IN_PROGRESS" or status == "PENDING":
            continue

        break

    err_str = ''
    err_count = 0

    if api_result_json["status"] == "FAILED":
        print("Failure during provisioning...")

        get_error_json = requests.get(api_result_json["errorSummaryUrl"])

        if get_error_json.status_code == 200:
            err_str = get_error_json.text
            err_count, err_json = parse_err_msg(err_str)
            device_list = update_device_list(device_list, err_json)
        else:
            print("Could not access error output: " + get_error_json.text)

    elif api_result_json["status"] != "SUCCEEDED":
        print("Unhandled bulk ops status: " + api_result_json["status"])

    results = io.StringIO()

    # Write the data from the bulk ops status
    for k, v in api_result_json.items():
        results.write(k + ',' + v + '\n')

    results.write('Error count,' + str(err_count) + '\n')
    results.write('\n')
    results.write('Device ID,Result' + '\n')

    # Write the items in the device list
    for dev_entry in device_list:
        results.write(dev_entry[DEV_LIST_ID_IDX] + ',' +
                      dev_entry[DEV_LIST_RES_IDX] + '\n')

    if result_filepath:
        write_file(os.path.dirname(result_filepath),
                   os.path.basename(result_filepath),
                   results.getvalue().encode('utf-8'))
    else:
        print(results.getvalue())

    return

def main():

    if not len(sys.argv) > 1:
        raise RuntimeError("No input provided")

    args = parse_args()

    do_provisioning(args.apikey, args.csv, args.res, args.chk)

    return

if __name__ == '__main__':
    main()
