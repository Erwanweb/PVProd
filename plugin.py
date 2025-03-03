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
import time
from datetime import datetime, timedelta

import Domoticz
import requests
from distutils.version import LooseVersion

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
        self.TodayEnergyCons = 0
        self.EnergyImport= 0
        self.TodayEnergyImport = 0
        self.PVProd = 0
        self.TodayPVProd = 0
        self.TodayPVProdCO2 = 0
        self.PVInject = 0
        self.TodayPVInject = 0
        self.PVCons = 0
        self.TodayPVCons = 0
        self.TodayPVAutoCons = 0
        self.C02 = 0
        self.AutoCons = 0
        self.LastTime = time.time()
        self.lastTimeReset = datetime.now() - timedelta(days=1)
        self.PLUGINstarteddtime = datetime.now()
        self.InternalsDefaults = {
            'V_EnergyImport': 0,  # defaut
            'V_TodayEnergyImport': 0,  # defaut
            'V_PVInject': 0,  # defaut
            'V_TodayPVInject': 0,  # defaut
            'V_PVCons': 0,  # defaut
            'V_TodayPVCons': 0,  # defaut
            'V_TodayPVAutoCons': 0,  # defaut
            'V_CO2': 0,  # defaut
            'V_AutoCons': 0, # defaut
            'V_lastTimeReset' : datetime.now() - timedelta(days=1)}  # defaut
        self.Internals = self.InternalsDefaults.copy()

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
            Domoticz.Device(Name="Total Cons", Unit=1, Type=243, Subtype=29, Used=1).Create()
            devicecreated.append(deviceparam(1, 0, "0"))  # default is 0 Kwh forecast
        if 2 not in Devices:
            Domoticz.Device(Name="Import", Unit=2, Type=243, Subtype=29, Used=1).Create()
            devicecreated.append(deviceparam(2, 0, "0"))  # default is 0 Kwh forecast
        if 3 not in Devices:
            Domoticz.Device(Name="PV Prod", Unit=3, Type=243, Subtype=29, Used=1).Create()
            devicecreated.append(deviceparam(3, 0, "0"))  # default is 0 Kwh forecast
        if 4 not in Devices:
            Domoticz.Device(Name="PV Cons", Unit=4, Type=243, Subtype=29, Used=1).Create()
            devicecreated.append(deviceparam(4, 0, "0"))  # default is 0 Kwh forecast
        if 5 not in Devices:
            Domoticz.Device(Name="PV Inject", Unit=5, Type=243, Subtype=29, Used=1).Create()
            devicecreated.append(deviceparam(5, 0, "0"))  # default is 0 Kwh forecast
        if 6 not in Devices:
            Domoticz.Device(Name="Autocons", Unit=6, Type=243, Subtype=31, Options={"Custom": "1;%"},Used=1).Create()
            devicecreated.append(deviceparam(6, 0, "0"))  # default is 0 Kwh forecast
        if 7 not in Devices:
            Domoticz.Device(Name="Co2", Unit=7, Type=243, Subtype=31, Options={"Custom": "1;Kg"},Used=1).Create()
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
        self.readCons()
        self.readPVProd()

        # creating user variable if doesn't exist or update it
        self.getUserVar()


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

        # Recup user variables
        self.EnergyImport = self.Internals['V_EnergyImport']
        self.TodayEnergyImport = self.Internals['V_TodayEnergyImport']
        self.PVInject = self.Internals['V_PVInject']
        self.TodayPVInject = self.Internals['V_TodayPVInject']
        self.PVCons = self.Internals['V_PVCons']
        self.TodayPVCons = self.Internals['V_TodayPVCons']
        self.TodayPVAutoCons = self.Internals['V_TodayPVAutoCons']
        self.CO2 = self.Internals['V_CO2']
        self.AutoCons = self.Internals['V_AutoCons']
        self.lastTimeReset = self.Internals['V_lastTimeReset']

        # check for new day counter reset
        LastReset = self.lastTimeReset
        if now.date() > LastReset.date():
            self.lastTimeReset = now
            self.TodayPVAutoCons = 0
            self.WriteLog("Reset Today Counter value", "Verbose")

        # check for time inverval between 2 mesurements for kwh
        NowTime = time.time()
        Timer = NowTime - self.LastTime
        self.LastTime = NowTime
        hours = Timer / 3600

        # update E Meters
        self.readCons()
        self.readPVProd()

        # Make the calc for other devices
        self.EnergyImport = (self.EnergyCons - self.PVProd)
        if self.EnergyImport <= 0:
            self.EnergyImport = 0
        self.TodayEnergyImport = round(self.TodayEnergyImport + (self.EnergyImport * hours))
        strValue2 = str(self.EnergyImport) + ";" + str(self.TodayEnergyImport)

        self.PVInject = (self.PVProd - self.EnergyCons)
        if self.PVInject <= 0:
            self.PVInject = 0
            self.PVCons = self.PVProd
        else :
            self.PVCons = (self.PVProd - self.PVInject)
        self.TodayPVCons = round(self.TodayPVCons + (self.PVCons * hours))
        self.TodayPVAutocons = round(self.TodayPVAutoCons + (self.PVCons * hours))
        strValue4 = str(self.PVCons) + ";" + str(self.TodayPVCons)
        self.TodayPVInject = round(self.TodayPVInject + (self.PVInject * hours))
        strValue5 = str(self.PVInject) + ";" + str(self.TodayPVInject)

    # CALC CO & %  ------------------------------------------------------------------------------------------------

        if self.TodayPVProdCO2 > 0:
            self.AutoCons = round(((self.TodayPVAutocons / self.TodayPVProdCO2)*100))
            self.C02 = round((0 - ((self.TodayPVProdCO2 / 1000) * 0.06)), 2)
        else :
            self.AutoCons = 0
            self.C02 = 0

    # UPDATING DEVICES ------------------------------------------------------------------------------------------------

        strValue1 = str(self.EnergyCons) + ";" + str(self.TodayEnergyCons)
        Devices[1].Update(nValue=0, sValue=strValue1, TimedOut=0)  # update the dummy device showing the current value
        Domoticz.Debug("Total Cons value is = {}".format(strValue1))
        strValue3 = str(self.PVProd) + ";" + str(self.TodayPVProd)
        Devices[3].Update(nValue=0, sValue=strValue3, TimedOut=0)  # update the dummy device showing the current value
        Domoticz.Debug("PVProd value is = {}".format(strValue3))
        Devices[2].Update(nValue=0, sValue=strValue2)  # update the dummy device showing the current value
        Domoticz.Debug("EnergyImport value is = {}".format(strValue2))
        Devices[4].Update(nValue=0, sValue=strValue4)  # update the dummy device showing the current value
        Domoticz.Debug("PVCons value is = {}".format(strValue4))
        Devices[5].Update(nValue=0, sValue=strValue5)  # update the dummy device showing the current value
        Domoticz.Debug("PVInject value is = {}".format(strValue5))
        Devices[6].Update(nValue=0, sValue="{}".format(str(self.AutoCons)))  # update the dummy device showing the current value
        Domoticz.Debug("Autocons value is = {} %".format(str(self.AutoCons)))
        Domoticz.Debug("Today PV Cons is  = {} KwH".format(str(self.TodayPVAutoCons)))
        Domoticz.Debug("Today PV Prod is = {} KwH".format(str(self.TodayPVProdCO2)))
        Devices[7].Update(nValue=0, sValue="{}".format(str(self.C02)))  # update the dummy device showing the current value
        Domoticz.Debug("Free Co2 value is = {} Kg".format(str(self.C02)))
        self.WriteLog("Updating widget : Total Cons. {}, PVProd {}, Import {}, PVCons {}, Inject {}, AutoCons {}, Co2 {}".format(strValue1, strValue3, strValue2, strValue4, strValue5, self.AutoCons, self.C02), "Verbose")

        # modif des users variable
        self.Internals['V_EnergyImport'] = self.EnergyImport
        self.Internals['V_TodayEnergyImport'] = self.TodayEnergyImport
        self.Internals['V_PVInject'] = self.PVInject
        self.Internals['V_TodayPVInject'] = self.TodayPVInject
        self.Internals['V_PVCons'] = self.PVCons
        self.Internals['V_TodayPVCons'] = self.TodayPVCons
        self.Internals['V_TodayPVAutoCons'] = self.TodayPVAutoCons
        self.Internals['V_CO2'] = self.CO2
        self.Internals['V_AutoCons'] = self.AutoCons
        self.Internals['V_lastTimeReset'] = self.lastTimeReset
        self.saveUserVar()  # update user variables with latest values

    # OTHER DEF -------------------------------------------------------------------------------------------------------

    def readCons(self):
        Domoticz.Debug("readCons called")
        # fetch all the devices from the API and scan for sensors
        noerror = True
        listinWatt = []
        listinwH = []
        devicesAPI = DomoticzAPI("type=command&param=getdevices&filter=utility&used=true&order=Name")
        if devicesAPI:
            for device in devicesAPI["result"]:  # parse the devices for temperature sensors
                idx = int(device["idx"])
                if idx in self.EnergyConsMeter:
                    if "Usage" in device:
                        Domoticz.Debug("device: {}-{} = {}".format(device["idx"], device["Name"], device["Usage"]))
                        texte = (device["Usage"])
                        valeur = texte.replace("Watt", "").strip()
                        listinWatt.append(int(valeur))
                        texte2 = (device["Data"])
                        valeur2 = texte2.replace("kWh", "").strip()
                        listinwH.append(int(float(valeur2)*1000))
                    else:
                        Domoticz.Error("device: {}-{} is not a E Meter sensor".format(device["idx"], device["Name"]))

        # calculate the total instant power
        nbWatt = len(listinWatt)
        if nbWatt > 0:
            self.EnergyCons = round(sum(listinWatt))
        else:
            Domoticz.Debug("No E Meter General cons found... ")
            noerror = False
        # calculate the total power
        nbKwh = len(listinwH)
        if nbKwh > 0:
            self.TodayEnergyCons = round(sum(listinwH))
        else:
            Domoticz.Debug("No E Meter General cons found... ")
            noerror = False

        Domoticz.Debug("E Meter General cons calculated value is = {}w, and {}wh".format(self.EnergyCons,self.TodayEnergyCons))
        return noerror

    def readPVProd(self):
        Domoticz.Debug("readPVProd called")
        # fetch all the devices from the API and scan for sensors
        noerror = True
        listinWatt = []
        listinwH = []
        listinwHCO2 = []
        devicesAPI = DomoticzAPI("type=command&param=getdevices&filter=utility&used=true&order=Name")
        if devicesAPI:
            for device in devicesAPI["result"]:  # parse the devices for temperature sensors
                idx = int(device["idx"])
                if idx in self.PVProdMeter:
                    if "Usage" in device:
                        Domoticz.Debug("device: {}-{} = {}".format(device["idx"], device["Name"], device["Usage"]))
                        texte = (device["Usage"])
                        valeur = texte.replace("Watt", "").strip()
                        listinWatt.append(int(valeur))
                        texte2 = (device["Data"])
                        valeur2 = texte2.replace("kWh", "").strip()
                        listinwH.append(int(float(valeur2) * 1000))
                        texte3 = (device["CounterToday"])
                        valeur3 = texte3.replace("kWh", "").strip()
                        listinwHCO2.append(int(float(valeur3) * 1000))
                    else:
                        Domoticz.Error("device: {}-{} is not a E Meter sensor".format(device["idx"], device["Name"]))

        # calculate the total instant power
        nbWatt = len(listinWatt)
        if nbWatt > 0:
            self.PVProd = round(sum(listinWatt))
        else:
            Domoticz.Debug("No E Meter PVProd found... ")
            noerror = False
        # calculate the total day power
        nbKwh = len(listinwH)
        if nbKwh > 0:
            self.TodayPVProd = round(sum(listinwH))
        else:
            Domoticz.Debug("No E Meter PVProd found... ")
            noerror = False
        # calculate the total day power
        nbKwhCO2 = len(listinwHCO2)
        if nbKwhCO2 > 0:
            self.TodayPVProdCO2 = round(sum(listinwHCO2))
        else:
            Domoticz.Debug("No E Meter PVProd found... ")
            noerror = False

        Domoticz.Debug("E Meter PVProd calculated value is = {}w, and {}wh".format(self.PVProd, self.TodayPVProd))
        return noerror

# User variable  ---------------------------------------------------

    def getUserVar(self):
        variables = DomoticzAPI("type=command&param=getuservariables")
        if variables:
            # there is a valid response from the API but we do not know if our variable exists yet
            novar = True
            varname = Parameters["Name"] + "-InternalVariables"
            valuestring = ""
            if "result" in variables:
                for variable in variables["result"]:
                    if variable["Name"] == varname:
                        valuestring = variable["Value"]
                        novar = False
                        break
            if novar:
                # create user variable since it does not exist
                Domoticz.Debug("User Variable {} does not exist. Creation requested".format(varname), "Verbose")

                # check for Domoticz version:
                # there is a breaking change on dzvents_version 2.4.9, API was changed from 'saveuservariable' to 'adduservariable'
                # using 'saveuservariable' on latest versions returns a "status = 'ERR'" error

                # get a status of the actual running Domoticz instance, set the parameter accordigly
                parameter = "saveuservariable"
                domoticzInfo = DomoticzAPI("type=command&param=getversion")
                if domoticzInfo is None:
                    Domoticz.Error("Unable to fetch Domoticz info... unable to determine version")
                else:
                    if domoticzInfo and LooseVersion(domoticzInfo["dzvents_version"]) >= LooseVersion("2.4.9"):
                        Domoticz.Debug("Use 'adduservariable' instead of 'saveuservariable'", "Verbose")
                        parameter = "adduservariable"

                # actually calling Domoticz API
                DomoticzAPI("type=command&param={}&vname={}&vtype=2&vvalue={}".format(parameter, varname, str(self.InternalsDefaults)))
                self.Internals = self.InternalsDefaults.copy()  # we re-initialize the internal variables
            else:
                try:
                    self.Internals.update(eval(valuestring))
                except:
                    self.Internals = self.InternalsDefaults.copy()
                return
        else:
            Domoticz.Error("Cannot read the uservariable holding the persistent variables")
            self.Internals = self.InternalsDefaults.copy()

    def saveUserVar(self):
        varname = Parameters["Name"] + "-InternalVariables"
        DomoticzAPI("type=command&param=updateuservariable&vname={}&vtype=2&vvalue={}".format(varname, str(self.Internals)))

# Write Log  ---------------------------------------------------

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
