import logging
import hashlib
import hmac
import os
import azure.functions as func
import json
import re
import base64
import requests
import datetime

SysdigAppSecret = os.environ['SysdigAppSecret']
customer_id = os.environ['WorkspaceID']
shared_key = os.environ['WorkspaceKey']
logAnalyticsUri = os.environ.get('logAnalyticsUri')
log_type = 'SysdigSecure'

if ((logAnalyticsUri in (None, '') or str(logAnalyticsUri).isspace())):
    logAnalyticsUri = 'https://' + customer_id + '.ods.opinsights.azure.com'
pattern = r'https:\/\/([\w\-]+)\.ods\.opinsights\.azure.([a-zA-Z\.]+)$'
match = re.match(pattern,str(logAnalyticsUri))
if(not match):
    raise Exception("SysdigFunctionApp: Invalid Log Analytics Uri.")


def hmac_sha1(message, secret):
    message = bytes(message, 'utf-8')
    secret = bytes(secret, 'utf-8')
    hash = hmac.new(secret, message, hashlib.sha1)
    return hash.hexdigest()


def parse_signature(value):
    parts = value.split('&')
    ret = {}
    for kv in parts:
        (k, v) = kv.split('=')
        ret[k] = v
    return ret


def build_signature(customer_id, shared_key, date, content_length, method, content_type, resource):
    x_headers = 'x-ms-date:' + date
    string_to_hash = method + "\n" + str(content_length) + "\n" + content_type + "\n" + x_headers + "\n" + resource
    bytes_to_hash = bytes(string_to_hash, encoding="utf-8")
    decoded_key = base64.b64decode(shared_key)
    encoded_hash = base64.b64encode(hmac.new(decoded_key, bytes_to_hash, digestmod=hashlib.sha256).digest()).decode()
    authorization = "SharedKey {}:{}".format(customer_id,encoded_hash)
    return authorization


def post_data_to_sentinel(body):
    method = 'POST'
    content_type = 'application/json'
    resource = '/api/logs'
    rfc1123date = datetime.datetime.utcnow().strftime('%a, %d %b %Y %H:%M:%S GMT')
    content_length = len(body)
    signature = build_signature(customer_id, shared_key, rfc1123date, content_length, method, content_type, resource)
    uri = 'https://' + customer_id + '.ods.opinsights.azure.com' + resource + '?api-version=2016-04-01'
    headers = {
        'content-type': content_type,
        'Authorization': signature,
        'Log-Type': log_type,
        'x-ms-date': rfc1123date
    }
    response = requests.post(uri,data=body, headers=headers)
    if (response.status_code >= 200 and response.status_code <= 299):
        return response.status_code
    else:
        logging.warn("Events are not processed into Azure. Response code: {}".format(response.status_code))
        return None


def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processed a request. Start of processing.')
    method = req.method
    if method == 'POST':
        post_req_data = req.get_body()
        signature_header = req.headers.get('Authorization')
        if signature_header == 'Bearer ' + SysdigAppSecret:
            message = post_req_data.decode('utf-8')
            message = json.loads(message)
            post_data_to_sentinel(json.dumps(message))
            logging.info("200 OK HTTPS")
            return func.HttpResponse("200 OK HTTPS", status_code=200)
        else:            
            logging.error("Request signature invalid. Error code: 400.")
            return func.HttpResponse("Request signature invalid!", status_code=400)
    logging.error("HTTP method not supported. Error code: 405.")
    return func.HttpResponse("HTTP method not supported", status_code=405)