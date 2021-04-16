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

gwhead = {'Authorization': f"Api-Key {GHOSTWRITER_API_KEY}", "Content-Type": "application/json"}

while True:
    authheader = {"accept":"text/plain","Content-Type":"application/json-patch+json"}
    authdata = {"userName":f"{COVENANT_USERNAME}","password":f"{COVENANT_PASSWORD}"}
    try:
        r = requests.post(f"{COVENANT_URL}/api/users/login", data=json.dumps(authdata), 
                headers=authheader, verify=False)
        rj = json.loads(r.text)
    
        tokenheader = {"Authorization":"Bearer " + rj["covenantToken"]}
        taskings = requests.get(f"{COVENANT_URL}/api/commands", headers=tokenheader, verify=False)
        tj = json.loads(taskings.text)
    except Exception as e:
        print(e)

    for rec in tj:
        if rec["gruntTasking"]:
            commandid = rec["id"]
            rconn = redis.Redis(host=f"{REDIS_HOSTNAME}", port=6379, db=0)
            entry = rconn.get(str(commandid))
            if entry is None:
                gw_message = {}
                gw_message["oplog_id"] = GHOSTWRITER_OPLOG_ID
                gruntid = rec["gruntId"]
                if rec["gruntTasking"]["taskingTime"] != "0001-01-01T00:00:00":
                    start = datetime.strptime(rec["gruntTasking"]["taskingTime"].split(".")[0], "%Y-%m-%dT%H:%M:%S")
                    gw_message["start_date"] = start.strftime("%Y-%m-%d %H:%M:%S")
                if rec["gruntTasking"]["completionTime"] != "0001-01-01T00:00:00":
                    end = datetime.strptime(rec["gruntTasking"]["completionTime"].split(".")[0], "%Y-%m-%dT%H:%M:%S")
                    gw_message["end_date"] = end.strftime("%Y-%m-%d %H:%M:%S")
                gw_message["description"] = rec["gruntTasking"]["gruntTask"]["description"] if rec["gruntTasking"]["gruntTask"]["description"] is not None else ""
                gw_message["tool"] = "Covenant - " + rec["gruntTasking"]["gruntTask"]["name"] if rec["gruntTasking"]["gruntTask"]["name"] is not None else ""
                gw_message["command"] = rec["command"] if rec["command"] is not None else ""
                gw_message["operator_name"] = rec["user"]["userName"] if rec["user"]["userName"] is not None else ""
                try:
                    grunt = json.loads(requests.get(f"{COVENANT_URL}/api/grunts/"+str(gruntid), 
                        headers=tokenheader, verify=False).text)
                    if grunt is not None:
                        gw_message["user_context"] = grunt["userName"] if grunt["userName"] is not None else ""
                        gw_message["source_ip"] = grunt["hostname"] + " - " + grunt["ipAddress"]
                    cmdout = json.loads(requests.get(f"{COVENANT_URL}/api/commandoutputs/"+str(rec["commandOutputId"]), 
                        headers=tokenheader, verify=False).text)
                    if cmdout is not None:
                        gw_message["output"] = cmdout["output"] if cmdout["output"] is not None else ""
                    gwr = requests.post(f"{GHOSTWRITER_URL}/oplog/api/entries/", 
                            data=json.dumps(gw_message), headers=gwhead, verify=False)
                    if gwr.status_code != 201:
                        print("Error posting to ghostwriter " + str(gwr.status_code))
                    else:
                        rconn.set(str(commandid),gwr.text)
                except Exception as e:
                    print(e)                        
            else:
                gw_message = {}
                redisdata = json.loads(entry.decode())
                if redisdata is not None:
                    if redisdata["output"] == "" and redisdata["id"] != "":
                        entry_id = str(redisdata["id"])
                        try:
                            cmdout = json.loads(requests.get(f"{COVENANT_URL}/api/commandoutputs/"+str(rec["commandOutputId"]), 
                                headers=tokenheader, verify=False).text)
                            if cmdout != None:
                                gw_message["output"] = redisdata["output"] = cmdout["output"] if cmdout["output"] is not None else ""
                                if rec["gruntTasking"]["taskingTime"] != "0001-01-01T00:00:00":
                                    start = datetime.strptime(rec["gruntTasking"]["taskingTime"].split(".")[0], "%Y-%m-%dT%H:%M:%S")
                                    gw_message["start_date"] = redisdata["start_date"] = start.strftime("%Y-%m-%d %H:%M:%S")
                                if rec["gruntTasking"]["completionTime"] != "0001-01-01T00:00:00":
                                    end = datetime.strptime(rec["gruntTasking"]["completionTime"].split(".")[0], "%Y-%m-%dT%H:%M:%S")
                                    gw_message["end_date"] = redisdata["end_date"] = end.strftime("%Y-%m-%d %H:%M:%S")
                            
                                gwr = requests.put(f"{GHOSTWRITER_URL}/oplog/api/entries/"+ entry_id + "/?format=json", 
                                        data=json.dumps(gw_message), headers=gwhead, verify=False)
                                if gwr.status_code != 200:
                                    print("Error posting to ghostwriter " + str(gwr.status_code))
                                else:
                                    rconn.set(str(commandid),json.dumps(redisdata))
                        except Exception as e:
                            print(e)
    time.sleep(30)
