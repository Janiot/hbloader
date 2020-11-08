#! /usr/bin/env python3

import sys
import asyncio
import aiohttp
import json
import re
import pathlib
from getpass import getpass

from lib.hbclient import HBClient
from lib.ddi.client import DDIClient
from lib.ddi.client import (ConfigStatusExecution, ConfigStatusResult)

import logging

HBLCFG = 'hblcfg.json'

def result_callback(result):
    print("Result:   {}".format('SUCCESSFUL' if result == 0 else 'FAILED' ))

def step_callback(percentage, message):
    print("Progress: {:>3}% - {}".format(percentage, message))


async def main():

    config = load_config()

    logfmt= '%(asctime)s %(levelname)-8s [%(filename)s:%(lineno)d-%(funcName)s] %(message)s'
    datefmt= '%Y-%m-%d %H:%M:%S'

    logging.basicConfig(level=logging.DEBUG, format=logfmt, datefmt=datefmt)

    async with aiohttp.ClientSession() as session:
        client = HBClient(session, result_callback, step_callback, **config)

        await client.run_ddi()

        await client.start_polling()

def ask_parameters(config):
    '''
    Running first time
    '''

    ''' get host ip '''
    ip = input('Enter IP address (default 127.0.0.1): ')

    if not ip:
        ip = '127.0.0.1'

    config['ip'] = ip

    ''' get host port '''
    while True:
        port = input ('Enter port (default 443): ')
            
        if not port:
            port = '443'

        if port.isdecimal():
            p = int(port)
            if (p in range(1023, 65535)) or (p in (80, 443)):
                break 

        print('Invalid port number')

    config['port'] = port

    ''' target name '''
    while True:
        target_name = input('Enter device name (for humans): ')
        if target_name:
            break

    config['target_name'] = target_name

    ''' controller_id  '''
    while True:
        controller_id = input('Enter controller ID (for computers): ')
        if controller_id:
            break

    config['controller_id'] = controller_id

    ''' get tenant id '''
    tenant_id = input('Enter tenant id: ')

    if not tenant_id:
        tenant_id = 'default'

    config['tenant_id'] = tenant_id

    ''' management login '''
    login = input('Login: ')
    if not login:
        login = 'admin'

    config['login'] = login

    config['password'] = getpass('Password: ')

    ''' SSH mode '''
    while True:
        yn = input('SSL mode (y/n): ')

        if yn in ('y', 'Y', ''):
            ssl  = 'True'
            break

        if yn in ('n', 'N'):
            ssl = 'False'
            break

        print('Wrong input')

    config['ssl'] = ssl
    
    '''run_as_service'''
    while True:
        yn = input('Run installed as service ? (Yes/No/Ask)')

        if yn in ('y', 'Y', ''):
            run_as_service  = 'yes'
            break

        if yn in ('n', 'N'):
            run_as_service = 'no'
            break

        if yn in ('a', 'A'):
            run_as_service = 'ask'
            break

        print('Wrong input')

    config['run_as_service'] = run_as_service


def load_config():
    '''
    Load configuration params
    If file exists load it as params,
    if not create it with default parameters
    '''
    config = {
    "ssl" : False,
    "host" :"127.0.0.1",
    "tenant_id" : "default",
    "target_name" : "",
    "login" : "admin",
    "password" : "admin",
    "auth_token" : "",
    "attributes" : {"MAC": ""},
    "loglevel" : "DEBUG",
    "run_as_service" : "yes",
    "port" :  "443"
    }

    ''' 
    if config file exist and contains host ip 
    return this config 
    '''
    if pathlib.Path(HBLCFG).exists():
        with open(HBLCFG, "r") as config_file:
            config = json.load(config_file)

        if config["ip"]:
            return config

    '''
    else ask to input parameters manually
    save and rerun updated config
    '''

    ask_parameters(config)

    with open(HBLCFG, "w") as config_file:
            json.dump(config, config_file, indent=4)

    return config


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
