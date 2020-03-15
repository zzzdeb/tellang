#!/usr/bin/env python

import json
import urllib.request

def request(action, **params):
    """
    Request
    """
    return {'action': action, 'params': params, 'version': 6}


def invoke(action, port, **params):
    """
    Docstring
    """
    request_json = json.dumps(request(action, **params)).encode('utf-8')
    response = json.load(urllib.request.urlopen(
        urllib.request.Request('http://localhost:'+port, request_json)))
    if len(response) != 2:
        raise Exception('response has an unexpected number of fields')
    if 'error' not in response:
        raise Exception('response is missing required error field')
    if 'result' not in response:
        raise Exception('response is missing required result field')
    if response['error'] is not None:
        raise Exception('{}{}\n {}'.format(port, request_json, response['error']))
    return response['result']

def echo(context):
    """
    Docstr
    """
    print(context.user_data)

import os
import subprocess
def get_silence(sec):
    """
    gets silence with duration sec

    :sec: TODO
    :returns: TODO

    """
    pre = '/tmp/tellangsilence'
    name = pre+str(sec) + '.mp3'

    if os.path.isfile(name):
        return name
    else:
        subprocess.call('ffmpeg -y -f lavfi -i anullsrc -t {} '.format(sec) +
                        name, shell=True)  # returns the exit code in unix
        return name

