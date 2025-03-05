#!/usr/bin/env python3
# -*- coding: utf-8 -*-


# Author: MrErwan,
# Version:    0.0.1: alpha...


"""
<plugin key="RL-SOLARPV" name="Ronelabs - Solar PV Control plugin" author="Ronelabs" version="0.0.2" externallink="https://ronelabs.com">
    <description>
        <h2>PV Prod Controler</h2><br/>
        Easily implement in Domoticz a Solar PV Monitoring with 2 days forecast<br/>
        <h3>Set-up and Configuration</h3>
    </description>
    <params>
        <param field="Username" label="Total Energy Cons E-Meter (CSV List of idx)" width="200px" required="true" default=""/>
        <param field="Password" label="Solar PV prod E-Meter (CSV List of idx)" width="200px" required="true" default=""/>
        <param field="Mode1" label="PV Plant Param (CSV List) : Declinaison (ex:0 is horizontal), Azimut (-90=E,0=S,90=W), System lost in % " width="200px" required="true" default="0,0,5"/>
        <param field="Mode2" label="PV Plant Power in Kwc (ex: 6.350)" width="50px" required="true" default="3"/>
        <param field="Mode5" label="Spec. folder (expert only - keep blank for ronelabs's standard) " width="800px" required="false" default=""/>
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
import math
import base64
import itertools
import subprocess
import os
import subprocess as sp
from typing import Any

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
        self.DayEnergyCons = 0
        self.PVPart = 0
        self.LastTime = time.time()
        self.lastTimeReset = 9
        self.PLUGINstarteddtime = datetime.now()
        self.InternalsDefaults = {
            'V_TodayEnergyImport': 0,  # defaut
            'V_TodayPVInject': 0,  # defaut
            'V_TodayPVCons': 0,  # defaut
            'V_TodayPVAutoCons': 0,  # defaut
            #'V_lastTimeReset' : datetime.now() - timedelta(days=1)}  # defaut
            'V_lastTimeReset': 9}  # defaut
        self.Internals = self.InternalsDefaults.copy()
        self.ForecastRequest = datetime.now()
        self.SpecFolder = ""
        self.lat = "0"
        self.lon = "0"
        self.decli = 0
        self.azimut = 0
        self.pvpower = 0
        self.pvlost = 0
        self.J0TotalValue = 0
        self.J1TotalValue = 0
        self.J0WperHRaw = "waiting for datas"
        self.J1WperHRaw = "waiting for datas"
        self.SFDatavalue = ""
        return

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
        # PVProd devices
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
            Domoticz.Device(Name="PV Part", Unit=7, Type=243, Subtype=31, Options={"Custom": "1;%"},Used=1).Create()
            devicecreated.append(deviceparam(7, 0, "0"))  # default is 0 Kwh forecast
        if 8 not in Devices:
            Domoticz.Device(Name="Co2", Unit=8, Type=243, Subtype=31, Options={"Custom": "1;Kg"},Used=1).Create()
            devicecreated.append(deviceparam(8, 0, "0"))  # default is 0 Kwh forecast

        #Forecast devices
        if 9 not in Devices:
            Domoticz.Device(Name="Today", Unit=9, Type=243, Subtype=31, Options={"Custom": "1;Kwh"}, Used=1).Create()
            devicecreated.append(deviceparam(9, 0, "0"))  # default is 0 Kwh forecast
        if 10 not in Devices:
            Domoticz.Device(Name="Tomorrow", Unit=10, Type=243, Subtype=31, Options={"Custom": "1;Kwh"}, Used=1).Create()
            devicecreated.append(deviceparam(10, 0, "0"))  # default is 0 Kwh forecast
        if 11 not in Devices:
            Domoticz.Device(Name="D0-W/H-Raw", Unit=11, Type=243, Subtype=19, Used=1).Create()
            devicecreated.append(deviceparam(11, 0, "waiting for datas"))
        if 12 not in Devices:
            Domoticz.Device(Name="D1-W/H-Raw", Unit=12, Type=243, Subtype=19, Used=1).Create()
            devicecreated.append(deviceparam(12, 0, "waiting for datas"))

        # if any device has been created in onStart(), now is time to update its defaults
        for device in devicecreated:
            Devices[device.unit].Update(nValue=device.nvalue, sValue=device.svalue)

        # build lists of idx widget of CAC221
        self.EnergyConsMeter = parseCSV(Parameters["Username"])
        Domoticz.Debug("EnergyConsMeter = {}".format(self.EnergyConsMeter))
        self.PVProdMeter = parseCSV(Parameters["Password"])
        Domoticz.Debug("PVProdMeter = {}".format(self.PVProdMeter))

        # build PV Plant params
        self.pvpower = Parameters["Mode2"]
        self.SpecFolder = Parameters["Mode5"]

        # splits additional parameters
        params = parseCSV(Parameters["Mode1"])
        if len(params) == 3:
            self.decli = CheckParam("Declinaison", params[0], 0)
            self.azimut = CheckParam("Azimut", params[1], 0)
            self.pvlost = CheckParam("System lost", params[2], 5)
        else:
            Domoticz.Error("Error reading PV Plant (Mode1) parameters")

        # reset time info when starting the plugin.
        self.PLUGINstarteddtime = datetime.now()

        # Set domoticz heartbeat to 20 s (onheattbeat() will be called every 20 )
        Domoticz.Heartbeat(20)

        # update E MEters
        self.readCons()
        self.readPVProd()

        # creating user variable if doesn't exist or update it
        self.getUserVar()

        # Updating Forecat devices values
        Devices[9].Update(nValue=0, sValue="{}".format(str(self.J0TotalValue)))
        Devices[10].Update(nValue=0, sValue="{}".format(str(self.J1TotalValue)))
        Devices[11].Update(nValue=0, sValue="{}".format(str(self.J0WperHRaw)))
        Devices[12].Update(nValue=0, sValue="{}".format(str(self.J1WperHRaw)))

    def onStop(self):
        Domoticz.Log("onStop called")
        Domoticz.Debugging(0)

    def onCommand(self, Unit, Command, Level, Color):
        Domoticz.Log( "onCommand called for Unit " + str(Unit) + ": Parameter '" + str(Command) + "', Level: " + str(Level))

    def onHeartbeat(self):
        Domoticz.Debug("onHeartbeat called")
        # fool proof checking.... based on users feedback
        if not all(device in Devices for device in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12)):
            Domoticz.Error("one or more devices required by the plugin is/are missing, please check domoticz device creation settings and restart !")
            return

        now = datetime.now()

        # HEARTBEAT PVProd PART  ---------------------------------------------------

        # Recup user variables
        self.TodayEnergyImport = self.Internals['V_TodayEnergyImport']
        self.TodayPVInject = self.Internals['V_TodayPVInject']
        self.TodayPVCons = self.Internals['V_TodayPVCons']
        self.TodayPVAutoCons = self.Internals['V_TodayPVAutoCons']
        self.lastTimeReset = self.Internals['V_lastTimeReset']

        # check for new day counter reset
        LastReset = self.lastTimeReset
        #if now.date() > LastReset.date():
        if now.isoweekday() != self.lastTimeReset :
            self.lastTimeReset = now.isoweekday()
            self.TodayPVAutoCons = 0
            self.WriteLog("Reset Today Counter value", "Verbose")
            Domoticz.Status("Reset dayly Counters value")

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
        self.TodayPVAutoCons = round(self.TodayPVAutoCons + (self.PVCons * hours))
        strValue4 = str(self.PVCons) + ";" + str(self.TodayPVCons)
        self.TodayPVInject = round(self.TodayPVInject + (self.PVInject * hours))
        strValue5 = str(self.PVInject) + ";" + str(self.TodayPVInject)

    # CALC CO & %  ------------------------------------------------------------------------------------------------

        if self.TodayPVProdCO2 > 0:
            self.AutoCons = round(((self.TodayPVAutoCons / self.TodayPVProdCO2)*100))
            if self.AutoCons > 100 :
                self.AutoCons = 100
            self.PVPart = round(((self.TodayPVAutoCons / self.DayEnergyCons)*100))
            if self.PVPart > 100 :
                self.PVPart = 100
            self.C02 = round((0 - ((self.TodayPVProdCO2 / 1000) * 0.06)), 2)
        else :
            self.AutoCons = 0
            self.C02 = 0
            self.PVPart = 0

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
        Domoticz.Debug("Today PV Cons is  = {} wH".format(str(self.TodayPVAutoCons)))
        Domoticz.Debug("Today PV Prod is = {} wH".format(str(self.TodayPVProdCO2)))
        Devices[7].Update(nValue=0, sValue="{}".format(str(self.PVPart)))  # update the dummy device showing the current value
        Domoticz.Debug("PV Part of total Cons is = {} %".format(str(self.PVPart)))
        Devices[8].Update(nValue=0, sValue="{}".format(str(self.C02)))  # update the dummy device showing the current value
        Domoticz.Debug("Free Co2 value is = {} Kg".format(str(self.C02)))
        Domoticz.Debug("Updating widget : Total Cons. {}, PVProd {}, Import {}, PVCons {}, Inject {}, AutoCons {}, Co2 {}, PV Part {}".format(strValue1, strValue3, strValue2, strValue4, strValue5, self.AutoCons, self.C02, self.PVPart), "Verbose")
        self.WriteLog("Updating widget and user variables")
        # modif des users variable
        self.Internals['V_TodayEnergyImport'] = self.TodayEnergyImport
        self.Internals['V_TodayPVInject'] = self.TodayPVInject
        self.Internals['V_TodayPVCons'] = self.TodayPVCons
        self.Internals['V_TodayPVAutoCons'] = self.TodayPVAutoCons
        self.Internals['V_lastTimeReset'] = self.lastTimeReset
        self.saveUserVar()  # update user variables with latest values

    # HEARTBEAT FORECAST PART  ---------------------------------------------------

        if self.ForecastRequest <= now:
            self.ForecastRequest = datetime.now() + timedelta(minutes=15)  # make a Call every 15 minutes max

            # Set location using domoticz param
            latlon = DomoticzAPI("type=command&param=getsettings")
            if latlon:
                self.lat = str(latlon['Location']['Latitude'])
                self.lon = str(latlon['Location']['Longitude'])
                Domoticz.Debug("Setting lat {} at and lon at {}".format(str(self.lat), str(self.lon)))

                # Set PVPlant
                self.PVPlant()
                # Check new forecast
                self.CheckForecast()
                Domoticz.Debug("Checking fo Solar Forecast datas")
                SFDatas = SolarForecatAPI("")
                if SFDatas:
                    self.SFDatavalue = str(SFDatas)
                if self.SFDatavalue == "error":
                    Domoticz.Error("jsonFile datas not updated - Value = {}".format(SFDatas))
                    self.ForecastRequest = datetime.now() + timedelta(minutes=30)
                else:
                    # json filde was updated
                    Domoticz.Debug("jsonFile datas = {}".format(SFDatas))
                    # Total wh forecast
                    self.J0TotalValue = float(SFDatas['forecast']['summary-wh-day']['today'])
                    self.J0TotalValue = round(float((self.J0TotalValue / 1000)), 3)
                    self.J1TotalValue = float(SFDatas['forecast']['summary-wh-day']['tomorrow'])
                    self.J1TotalValue = round(float((self.J1TotalValue / 1000)), 3)
                    # Watts per hour in Raw
                    # today
                    D0H0 = str(SFDatas['forecast']['hourly-watts']['today']["0"])
                    D0H1 = str(SFDatas['forecast']['hourly-watts']['today']["1"])
                    D0H2 = str(SFDatas['forecast']['hourly-watts']['today']["2"])
                    D0H3 = str(SFDatas['forecast']['hourly-watts']['today']["3"])
                    D0H4 = str(SFDatas['forecast']['hourly-watts']['today']["4"])
                    D0H5 = str(SFDatas['forecast']['hourly-watts']['today']["5"])
                    D0H6 = str(SFDatas['forecast']['hourly-watts']['today']["6"])
                    D0H7 = str(SFDatas['forecast']['hourly-watts']['today']["7"])
                    D0H8 = str(SFDatas['forecast']['hourly-watts']['today']["8"])
                    D0H9 = str(SFDatas['forecast']['hourly-watts']['today']["9"])
                    D0H10 = str(SFDatas['forecast']['hourly-watts']['today']["10"])
                    D0H11 = str(SFDatas['forecast']['hourly-watts']['today']["11"])
                    D0H12 = str(SFDatas['forecast']['hourly-watts']['today']["12"])
                    D0H13 = str(SFDatas['forecast']['hourly-watts']['today']["13"])
                    D0H14 = str(SFDatas['forecast']['hourly-watts']['today']["14"])
                    D0H15 = str(SFDatas['forecast']['hourly-watts']['today']["15"])
                    D0H16 = str(SFDatas['forecast']['hourly-watts']['today']["16"])
                    D0H17 = str(SFDatas['forecast']['hourly-watts']['today']["17"])
                    D0H18 = str(SFDatas['forecast']['hourly-watts']['today']["18"])
                    D0H19 = str(SFDatas['forecast']['hourly-watts']['today']["19"])
                    D0H20 = str(SFDatas['forecast']['hourly-watts']['today']["20"])
                    D0H21 = str(SFDatas['forecast']['hourly-watts']['today']["21"])
                    D0H22 = str(SFDatas['forecast']['hourly-watts']['today']["22"])
                    D0H23 = str(SFDatas['forecast']['hourly-watts']['today']["23"])
                    # creating raw data list of value
                    self.J0WperHRaw = f"{D0H0},{D0H1},{D0H2},{D0H3},{D0H4},{D0H5},{D0H6},{D0H7},{D0H8},{D0H9},{D0H10},{D0H11},{D0H12},{D0H13},{D0H14},{D0H15},{D0H16},{D0H17},{D0H18},{D0H19},{D0H20},{D0H21},{D0H22},{D0H23}"
                    # tmr
                    D1H0 = str(SFDatas['forecast']['hourly-watts']['tomorrow']["0"])
                    D1H1 = str(SFDatas['forecast']['hourly-watts']['tomorrow']["1"])
                    D1H2 = str(SFDatas['forecast']['hourly-watts']['tomorrow']["2"])
                    D1H3 = str(SFDatas['forecast']['hourly-watts']['tomorrow']["3"])
                    D1H4 = str(SFDatas['forecast']['hourly-watts']['tomorrow']["4"])
                    D1H5 = str(SFDatas['forecast']['hourly-watts']['tomorrow']["5"])
                    D1H6 = str(SFDatas['forecast']['hourly-watts']['tomorrow']["6"])
                    D1H7 = str(SFDatas['forecast']['hourly-watts']['tomorrow']["7"])
                    D1H8 = str(SFDatas['forecast']['hourly-watts']['tomorrow']["8"])
                    D1H9 = str(SFDatas['forecast']['hourly-watts']['tomorrow']["9"])
                    D1H10 = str(SFDatas['forecast']['hourly-watts']['tomorrow']["10"])
                    D1H11 = str(SFDatas['forecast']['hourly-watts']['tomorrow']["11"])
                    D1H12 = str(SFDatas['forecast']['hourly-watts']['tomorrow']["12"])
                    D1H13 = str(SFDatas['forecast']['hourly-watts']['tomorrow']["13"])
                    D1H14 = str(SFDatas['forecast']['hourly-watts']['tomorrow']["14"])
                    D1H15 = str(SFDatas['forecast']['hourly-watts']['tomorrow']["15"])
                    D1H16 = str(SFDatas['forecast']['hourly-watts']['tomorrow']["16"])
                    D1H17 = str(SFDatas['forecast']['hourly-watts']['tomorrow']["17"])
                    D1H18 = str(SFDatas['forecast']['hourly-watts']['tomorrow']["18"])
                    D1H19 = str(SFDatas['forecast']['hourly-watts']['tomorrow']["19"])
                    D1H20 = str(SFDatas['forecast']['hourly-watts']['tomorrow']["20"])
                    D1H21 = str(SFDatas['forecast']['hourly-watts']['tomorrow']["21"])
                    D1H22 = str(SFDatas['forecast']['hourly-watts']['tomorrow']["22"])
                    D1H23 = str(SFDatas['forecast']['hourly-watts']['tomorrow']["23"])
                    # creating raw data list of value
                    self.J1WperHRaw = f"{D1H0},{D1H1},{D1H2},{D1H3},{D1H4},{D1H5},{D1H6},{D1H7},{D1H8},{D1H9},{D1H10},{D1H11},{D1H12},{D1H13},{D1H14},{D1H15},{D1H16},{D1H17},{D1H18},{D1H19},{D1H20},{D1H21},{D1H22},{D1H23}"

                # Updating devices values
                self.WriteLog("Updating Devices from Solar Forecast datas")
                Devices[9].Update(nValue=0, sValue="{}".format(str(self.J0TotalValue)))
                Devices[10].Update(nValue=0, sValue="{}".format(str(self.J1TotalValue)))
                Devices[11].Update(nValue=0, sValue="{}".format(str(self.J0WperHRaw)))
                Devices[12].Update(nValue=0, sValue="{}".format(str(self.J1WperHRaw)))

    # OTHER DEF -------------------------------------------------------------------------------------------------------

    def readCons(self):
        Domoticz.Debug("readCons called")
        # fetch all the devices from the API and scan for sensors
        noerror = True
        listinWatt = []
        listinwH = []
        listinTodaywH = []
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
                        texte3 = (device["CounterToday"])
                        valeur3 = texte3.replace("kWh", "").strip()
                        listinTodaywH.append(int(float(valeur3) * 1000))
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
        # calculate the total power cons for today
        nbKwhT = len(listinTodaywH)
        if nbKwhT > 0:
            self.DayEnergyCons = round(sum(listinTodaywH))
        else:
            Domoticz.Debug("No E Meter General cons found... ")
            noerror = False

        Domoticz.Debug("E Meter General cons calculated value is = {}w, and {}wh, and {}".format(self.EnergyCons,self.TodayEnergyCons,self.DayEnergyCons))
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

        Domoticz.Debug("E Meter PVProd calculated value is = {}w, and {}wh, and {}".format(self.PVProd, self.TodayPVProd,self.TodayPVProdCO2))
        return noerror

# PV Plant variables  ---------------------------------------------------

    def PVPlant(self):

        # LATITUDE = '41.57387'  # Example latitude
        LATITUDE = str(self.lat)
        # LONGITUDE = '2.48982'  # Example longitude
        LONGITUDE = str(self.lon)
        # DECLINATION = '45'  # Example declination
        DECLINATION = str(self.decli)
        # AZIMUTH = '70'  # Example azimuth
        AZIMUTH = str(self.azimut)
        # KWP = '8.480'  # Example kWp
        KWP = str(self.pvpower)
        FOLDER = str(self.SpecFolder)
        Domoticz.Debug(f"Setting PV PLANT at {LATITUDE} - {LONGITUDE} - {DECLINATION} - {AZIMUTH} - {KWP}")

        if self.SpecFolder == "":
            Domoticz.Debug("Using standard Plugin Folder for Setting PV PLANT")
            with open('/home/domoticz/plugins/PVProd/PVPlant.py', 'w') as f:
                f.write(f"# PV Plant variables\n")
                f.write(f"#\n")
                f.write(f"LATITUDE = '{LATITUDE}'\n")
                f.write(f"LONGITUDE = '{LONGITUDE}'\n")
                f.write(f"DECLINATION = '{DECLINATION}'\n")
                f.write(f"AZIMUTH = '{AZIMUTH}'\n")
                f.write(f"KWP = '{KWP}'\n")
                f.write(f"FOLDER = '/home/domoticz/plugins/PVProd/'\n")
                f.write(f"#---- END\n")
            Domoticz.Debug("PV Plant Setted")
        else:
            PluginFolder = str(self.SpecFolder)
            Domoticz.Debug(f"Using special Folder for Setting PV PLANT : {PluginFolder}")
            with open(f'{PluginFolder}PVPlant.py', 'w') as f:
                f.write(f"# PV Plant variables\n")
                f.write(f"#\n")
                f.write(f"LATITUDE = '{LATITUDE}'\n")
                f.write(f"LONGITUDE = '{LONGITUDE}'\n")
                f.write(f"DECLINATION = '{DECLINATION}'\n")
                f.write(f"AZIMUTH = '{AZIMUTH}'\n")
                f.write(f"KWP = '{KWP}'\n")
                f.write(f"FOLDER = '{FOLDER}'\n")
                f.write(f"#---- END\n")
            Domoticz.Debug("PV Plant Setted")

# Check Forecast  ---------------------------------------------------

    def CheckForecast(self):

        if self.SpecFolder == "":
            Domoticz.Debug("Using standard Plugin Folder for json Forecast file")
            cmd = 'sudo python3 /home/domoticz/plugins/PVProd/forecastsolar.py'
            output = sp.getoutput(cmd)
        else:
            PluginFolder = str(self.SpecFolder)
            Domoticz.Debug(f"Using special Folder json Forecast file : {PluginFolder}")
            cmd = f'sudo python3 {PluginFolder}forecastsolar.py'
            output = sp.getoutput(cmd)
        # cmd = 'sudo python3 /home/domoticz/plugins/solarforecast/forecastsolar.py'
        # output = sp.getoutput(cmd)
        if output == "Forecast received - datas saved":
            Domoticz.Debug("Check for forecast : {}".format(output))
        else:
            Domoticz.Error("{}".format(output))


# User variable  ---------------------------------------------------

    def getUserVar(self):
        Domoticz.Debug("Get UserVariable called")
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
                        Domoticz.Status("UserVariable found and loaded")
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
                Domoticz.Status("UserVariable Created !!!")
            else:
                try:
                    self.Internals.update(eval(valuestring))
                    Domoticz.Status("UserVariable updated")
                except:
                    self.Internals = self.InternalsDefaults.copy()
                    Domoticz.Status("UserVariable are corrupted - reset")
                return
        else:
            Domoticz.Error("Cannot read the uservariable holding the persistent variables")
            self.Internals = self.InternalsDefaults.copy()

    def saveUserVar(self):
        Domoticz.Debug("Save UserVariable called")
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

def SolarForecatAPI(APICall):

    Domoticz.Debug("Solar Forecast local API Called...")
    SFjsonData = None
    PluginFolder = Parameters["Mode5"]
    if PluginFolder == "":
        Domoticz.Debug("Local API : Using standard Plugin Folder for json Forecast file")
        jsonFile = "/home/domoticz/plugins/solarforecast/solar_forecast.json"
    else:
        Domoticz.Debug(f"Local API : Using special Folder json Forecast file : {PluginFolder}")
        jsonFile = f"{PluginFolder}solar_forecast.json"
    # Check for ecowatt datas file
    if not os.path.isfile(jsonFile):
        Domoticz.Error(f"Can't find {jsonFile} file!")
        return
    else:
        Domoticz.Debug(f"Solar Forcast json Solar Forecast file found")
    # Check for ecowatt datas
    with open(jsonFile) as SFStream:
        try:
            SFjsonData = json.load(SFStream)
        except:
            Domoticz.Error(f"Error opening json Solar Forecast file !")
    return SFjsonData

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
