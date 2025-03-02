#!/usr/bin/env python3
# -*- coding: utf-8 -*-


# Author: MrErwan,
# Version:    0.0.1: alpha...


"""
<plugin key="RL-SOLARPV" name="Ronelabs - Solar PV Control plugin" author="Ronelabs" version="0.0.2" externallink="https://ronelabs.com">
    <description>
        <h2>PV Prod Controler</h2><br/>
        Easily implement in Domoticz a Solar PV control<br/>
        <h3>Set-up and Configuration</h3>
    </description>
    <params>
        <param field="Username" label="Energy Cons Meter idx" width="200px" required="true" default=""/>
        <param field="Password" label="Solar PV prod meter idx" width="200px" required="true" default=""/>
        <param field="Mode6" label="Logging Level" width="200px">
            <options>
                <option label="Normal" value="Normal"  default="true"/>
                <option label="Verbose" value="Verbose"/>
                <option label="Debug - Python Only" value="2"/>
                <option label="Debug - Basic" value="62"/>
                <option label="Debug - Basic+Messages" value="126"/>
                <option label="Debug - Connections Only" value="16"/>
                <option label="Debug - Connections+Queue" value="144"/>
                <option label="Debug - All" value="-1"/>
            </options>
        </param>
    </params>
</plugin>
"""

import json
import math
import urllib
import urllib.parse as parse
import urllib.request as request
from datetime import datetime, timedelta

import Domoticz
import requests

try:
    from Domoticz import Devices, Images, Parameters, Settings
except ImportError:
    pass



class deviceparam:

    def __init__(self, unit, nvalue, svalue):
        self.unit = unit
        self.nvalue = nvalue
        self.svalue = svalue
        self.debug = False


class BasePlugin:

    def __init__(self):
        self.debug = False
        self.EnergyConsMeter = []
        self.PVProdMeter= []
        self.EnergyCons = 0
        self.EnergyImport= 0
        self.PVProd = 0
        self.PVInject = 0
        self.PVCons = 0
        now = datetime.now()
        self.PLUGINstarteddtime = now

    def onStart(self):
        Domoticz.Log("onStart called")
        # setup the appropriate logging level
        try:
            debuglevel = int(Parameters["Mode6"])
        except ValueError:
            debuglevel = 0
            self.loglevel = Parameters["Mode6"]
        if debuglevel != 0:
            self.debug = True
            Domoticz.Debugging(debuglevel)
            DumpConfigToLog()
            self.loglevel = "Verbose"
        else:
            self.debug = False
            Domoticz.Debugging(0)

        # create the child devices if these do not exist yet
        devicecreated = []
        if 1 not in Devices:
            Domoticz.Device(Name="General Cons", Unit=1, Type=243, Subtype=29, Options={'EnergyMeterMode': '1'}, Used=1).Create()
            devicecreated.append(deviceparam(1, 0, "0"))  # default is 0 Kwh forecast
        if 2 not in Devices:
            Domoticz.Device(Name="Import", Unit=2, Type=243, Subtype=29, Options={'EnergyMeterMode': '1'}, Used=1).Create()
            devicecreated.append(deviceparam(2, 0, "0"))  # default is 0 Kwh forecast
        if 3 not in Devices:
            Domoticz.Device(Name="PV Prod", Unit=3, Type=243, Subtype=29, Options={'EnergyMeterMode': '1'}, Used=1).Create()
            devicecreated.append(deviceparam(3, 0, "0"))  # default is 0 Kwh forecast
        if 4 not in Devices:
            Domoticz.Device(Name="PV Cons", Unit=4, Type=243, Subtype=29, Options={'EnergyMeterMode': '1'}, Used=1).Create()
            devicecreated.append(deviceparam(4, 0, "0"))  # default is 0 Kwh forecast
        if 5 not in Devices:
            Domoticz.Device(Name="PV Inject", Unit=5, Type=243, Subtype=29, Options={'EnergyMeterMode': '1'}, Used=1).Create()
            devicecreated.append(deviceparam(5, 0, "0"))  # default is 0 Kwh forecast
        if 6 not in Devices:
            Domoticz.Device(Name="Autocons", Unit=6, Type=243, Subtype=31, Options={"Custom": "1;%"}, Used=1).Create()
            devicecreated.append(deviceparam(6, 0, "0"))  # default is 0 Kwh forecast
        if 7 not in Devices:
            Domoticz.Device(Name="Co2", Unit=7, Type=243, Subtype=31, Options={"Custom": "1;Kg"}, Used=1).Create()
            devicecreated.append(deviceparam(7, 0, "0"))  # default is 0 Kwh forecast

        # if any device has been created in onStart(), now is time to update its defaults
        for device in devicecreated:
            Devices[device.unit].Update(nValue=device.nvalue, sValue=device.svalue)

        # build lists of idx widget of CAC221
        self.EnergyConsMeter = parseCSV(Parameters["Username"])
        Domoticz.Debug("EnergyConsMeter = {}".format(self.EnergyConsMeter))
        self.PVProdMeter = parseCSV(Parameters["Password"])
        Domoticz.Debug("PVProdMeter = {}".format(self.PVProdMeter))

        # reset time info when starting the plugin.
        self.PLUGINstarteddtime = datetime.now()

        # Set domoticz heartbeat to 20 s (onheattbeat() will be called every 20 )
        Domoticz.Heartbeat(20)

        # update E MEters
        #self.readCons()


    def onStop(self):
        Domoticz.Log("onStop called")
        Domoticz.Debugging(0)

    def onCommand(self, Unit, Command, Level, Color):
        Domoticz.Log(
            "onCommand called for Unit " + str(Unit) + ": Parameter '" + str(Command) + "', Level: " + str(Level))

    def onHeartbeat(self):
        Domoticz.Debug("onHeartbeat called")
        # fool proof checking.... based on users feedback
        if not all(device in Devices for device in (1, 2, 3, 4, 5, 6, 7)):
            Domoticz.Error("one or more devices required by the plugin is/are missing, please check domoticz device creation settings and restart !")
            return

        now = datetime.now()

        # update E MEters
        self.readCons()


        # REPEAT IR ORDER -----------------------------------------------------------------------------------------------------


    # OTHER DEF -----------------------------------------------------------------------------------------------------------

    def readCons(self):
        Domoticz.Debug("readCons called")
        self.nexttemps = datetime.now()
        # fetch all the devices from the API and scan for sensors
        noerror = True
        listintemps = []
        devicesAPI = DomoticzAPI("type=command&param=getdevices&filter=utility&used=true&order=Name")
        if devicesAPI:
            for device in devicesAPI["result"]:  # parse the devices for temperature sensors
                idx = int(device["idx"])
                if idx in self.EnergyConsMeter:
                    if "Usage" in device:
                        Domoticz.Debug("device: {}-{} = {}".format(device["idx"], device["Name"], device["Usage"]))
                        texte = (device["Usage"])
                        valeur = texte.replace("Watt", "").strip()
                        Domoticz.Debug(f"E Meter value: {valeur}")
                        #return int(valeur)
                        listintemps.append(int(valeur))
                    else:
                        Domoticz.Error("device: {}-{} is not a E Meter sensor".format(device["idx"], device["Name"]))

        # calculate the average inside temperature
        nbtemps = len(listintemps)
        if nbtemps > 0:
            self.EnergyCons = round(sum(listintemps) / nbtemps)
            Devices[1].Update(nValue=0,sValue="{};0".format(str(self.EnergyCons)))   # update the dummy device showing the current value
        else:
            Domoticz.Debug("No E Meter found... ")
            noerror = False

        self.WriteLog("E Meter calculated value is = {}".format(self.EnergyCons), "Verbose")
        return noerror

    

    def WriteLog(self, message, level="Normal"):

        if self.loglevel == "Verbose" and level == "Verbose":
            Domoticz.Log(message)
        elif level == "Normal":
            Domoticz.Log(message)


# Plugin functions ---------------------------------------------------

global _plugin
_plugin = BasePlugin()


def onStart():
    global _plugin
    _plugin.onStart()


def onStop():
    global _plugin
    _plugin.onStop()


def onCommand(Unit, Command, Level, Color):
    global _plugin
    _plugin.onCommand(Unit, Command, Level, Color)


def onHeartbeat():
    global _plugin
    _plugin.onHeartbeat()


# Plugin utility functions ---------------------------------------------------


def parseCSV(strCSV):
    listvals = []
    for value in strCSV.split(","):
        try:
            val = int(value)
            listvals.append(val)
        except ValueError:
            try:
                val = float(value)
                listvals.append(val)
            except ValueError:
                Domoticz.Error(f"Skipping non-numeric value: {value}")
    return listvals


def DomoticzAPI(APICall):
    resultJson = None
    url = f"http://127.0.0.1:8080/json.htm?{parse.quote(APICall, safe='&=')}"

    try:
        Domoticz.Debug(f"Domoticz API request: {url}")
        req = request.Request(url)
        response = request.urlopen(req)

        if response.status == 200:
            resultJson = json.loads(response.read().decode('utf-8'))
            if resultJson.get("status") != "OK":
                Domoticz.Error(f"Domoticz API returned an error: status = {resultJson.get('status')}")
                resultJson = None
        else:
            Domoticz.Error(f"Domoticz API: HTTP error = {response.status}")

    except urllib.error.HTTPError as e:
        Domoticz.Error(f"HTTP error calling '{url}': {e}")

    except urllib.error.URLError as e:
        Domoticz.Error(f"URL error calling '{url}': {e}")

    except json.JSONDecodeError as e:
        Domoticz.Error(f"JSON decoding error: {e}")

    except Exception as e:
        Domoticz.Error(f"Error calling '{url}': {e}")

    return resultJson



def CheckParam(name, value, default):
    try:
        param = int(value)
    except ValueError:
        param = default
        Domoticz.Error( f"Parameter '{name}' has an invalid value of '{value}' ! defaut of '{param}' is instead used.")
    return param


# Generic helper functions
def DumpConfigToLog():
    for x in Parameters:
        if Parameters[x] != "":
            Domoticz.Debug("'" + x + "':'" + str(Parameters[x]) + "'")
    Domoticz.Debug("Device count: " + str(len(Devices)))
    for x in Devices:
        Domoticz.Debug("Device:           " + str(x) + " - " + str(Devices[x]))
        Domoticz.Debug("Device ID:       '" + str(Devices[x].ID) + "'")
        Domoticz.Debug("Device Name:     '" + Devices[x].Name + "'")
        Domoticz.Debug("Device nValue:    " + str(Devices[x].nValue))
        Domoticz.Debug("Device sValue:   '" + Devices[x].sValue + "'")
        Domoticz.Debug("Device LastLevel: " + str(Devices[x].LastLevel))
    return
