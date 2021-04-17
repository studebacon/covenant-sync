#!/usr/bin/env python3
#This tool was inspired by https://github.com/hotnops/mythic-sync

import json
import requests
import redis
import time
import urllib3
import os
from datetime import datetime
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

COVENANT_USERNAME = os.environ["COVENANT_USERNAME"]
COVENANT_PASSWORD = os.environ["COVENANT_PASSWORD"]
COVENANT_URL = os.environ["COVENANT_URL"]
GHOSTWRITER_API_KEY = os.environ["GHOSTWRITER_API_KEY"]
GHOSTWRITER_URL = os.environ["GHOSTWRITER_URL"]
GHOSTWRITER_OPLOG_ID = os.environ["GHOSTWRITER_OPLOG_ID"]
REDIS_HOSTNAME =os.environ["REDIS_HOSTNAME"]

SLEEP_TIME = 30

rconn = redis.Redis(host=f"{REDIS_HOSTNAME}", port=6379, db=0)
gw_header = {'Authorization': f"Api-Key {GHOSTWRITER_API_KEY}", "Content-Type": "application/json"}
cov_authheader = {"accept":"text/plain","Content-Type":"application/json-patch+json"}
cov_authdata = {"userName":f"{COVENANT_USERNAME}","password":f"{COVENANT_PASSWORD}"}
cmds={}

def getCovToken():
    cov_token = {}
    try:
        cov_authresp = json.loads(requests.post(f"{COVENANT_URL}/api/users/login", 
            data=json.dumps(cov_authdata), headers=cov_authheader, verify=False).text)
        cov_token = {"Authorization":"Bearer " + cov_authresp["covenantToken"]}
    except Exception as e:
        print(e)
    return cov_token

def newOpFromCmd(cmd):
    op_data = {}
    op_data["oplog_id"] = GHOSTWRITER_OPLOG_ID

    if cmd["gruntTasking"]["taskingTime"] != "0001-01-01T00:00:00":
        start = datetime.strptime(cmd["gruntTasking"]["taskingTime"].split(".")[0], "%Y-%m-%dT%H:%M:%S")
        op_data["start_date"] = start.strftime("%Y-%m-%d %H:%M:%S")
    if cmd["gruntTasking"]["completionTime"] != "0001-01-01T00:00:00":
        end = datetime.strptime(cmd["gruntTasking"]["completionTime"].split(".")[0], "%Y-%m-%dT%H:%M:%S")
        op_data["end_date"] = end.strftime("%Y-%m-%d %H:%M:%S")

    op_data["description"] = cmd["gruntTasking"]["gruntTask"]["description"] if cmd["gruntTasking"]["gruntTask"]["description"] is not None else ""
    op_data["tool"] = "Covenant - " + cmd["gruntTasking"]["gruntTask"]["name"] if cmd["gruntTasking"]["gruntTask"]["name"] is not None else ""
    op_data["command"] = cmd["command"] if cmd["command"] is not None else ""
    op_data["operator_name"] = cmd["user"]["userName"] if cmd["user"]["userName"] is not None else ""

    try:
        auth_token = getCovToken()
        gruntid = cmd["gruntId"] if cmd["gruntId"] is not None else ""
        grunt = json.loads(requests.get(f"{COVENANT_URL}/api/grunts/{gruntid}", headers=auth_token, verify=False).text)

        if grunt:
            op_data["user_context"] = grunt["userName"] if grunt["userName"] is not None else ""
            op_data["source_ip"] = grunt["hostname"] + " - " + grunt["ipAddress"]

        cmdid = str(cmd["commandOutputId"]) if cmd["commandOutputId"] is not None else ""
        cmdout = json.loads(requests.get(f"{COVENANT_URL}/api/commandoutputs/{cmdid}", headers=auth_token, verify=False).text)
        if cmdout:
            op_data["output"] = cmdout["output"] if cmdout["output"] is not None else ""
    except Exception as e:
        print(e)                        

    return op_data

def updateOpFromCmd(cmd):
    op_data = {}
    
    try:
        auth_token = getCovToken()
        cmdid = str(cmd["commandOutputId"]) if cmd["commandOutputId"] is not None else ""
        cmdout = json.loads(requests.get(f"{COVENANT_URL}/api/commandoutputs/{cmdid}", headers=auth_token, verify=False).text)
        if cmdout:
            if cmdout["output"] != "": 
                if cmd["gruntTasking"]["taskingTime"] != "0001-01-01T00:00:00":
                    start = datetime.strptime(cmd["gruntTasking"]["taskingTime"].split(".")[0], "%Y-%m-%dT%H:%M:%S")
                    if cmd["gruntTasking"]["completionTime"] != "0001-01-01T00:00:00":
                        end = datetime.strptime(cmd["gruntTasking"]["completionTime"].split(".")[0], "%Y-%m-%dT%H:%M:%S")
                        #only set values if we have all of them
                        op_data["output"] = cmdout["output"]
                        op_data["end_date"] = end.strftime("%Y-%m-%d %H:%M:%S")
                        op_data["start_date"] = start.strftime("%Y-%m-%d %H:%M:%S")
    except Exception as e:
        print(e)
    return op_data


#main loop
while True:
    try:
        auth_token = getCovToken()
        cmds = json.loads(requests.get(f"{COVENANT_URL}/api/commands", headers=auth_token, verify=False).text)
    except Exception as e:
        print(e)

    if cmds is not None:
        for cmd in cmds:
            if cmd["id"]:
                gw_message = {}
                commandid = cmd["id"]
                entry = rconn.get(str(commandid))
                if not entry:
                    #create new oplog entry
                    try:
                        gw_message = newOpFromCmd(cmd) 
                        gwr = requests.post(f"{GHOSTWRITER_URL}/oplog/api/entries/", 
                                data=json.dumps(gw_message), headers=gw_header, verify=False)
                        if gwr.status_code != 201:
                            print("Error posting to ghostwriter " + str(gwr.status_code))
                        else:
                            rconn.set(str(commandid),gwr.text)
                    except Exception as e:
                        print(e)                        
                else:
                    #update existing oplog
                    redisdata = json.loads(entry.decode())
                    if redisdata:
                        #only update if previous output value was empty
                        if redisdata["output"] == "" and redisdata["id"] != "":
                            op_id = str(redisdata["id"])
                            gw_message = updateOpFromCmd(cmd)
                            if gw_message:
                                try:
                                    gwr = requests.put(f"{GHOSTWRITER_URL}/oplog/api/entries/{op_id}/?format=json", 
                                            data=json.dumps(gw_message), headers=gw_header, verify=False)
                                    if gwr.status_code != 200:
                                        print("Error posting to ghostwriter " + str(gwr.status_code))
                                    else:
                                        #update the date and output values in redis
                                        redisdata["output"] = gw_message["output"]
                                        redisdata["start_date"] = gw_message["start_date"]
                                        redisdata["end_date"] = gw_message["end_date"]
                                        rconn.set(str(commandid),json.dumps(redisdata))
                                except Exception as e:
                                    print(e)
    time.sleep(SLEEP_TIME)
