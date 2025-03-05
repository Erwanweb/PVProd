import requests
import json
from datetime import datetime, timedelta
import time
import PVPlant #import PV plant setted by domoticz


# PV PLANT
"""
LATITUDE = '41.57387'  # Example latitude
LONGITUDE = '2.48982'  # Example longitude
DECLINATION = '45'  # Example declination
AZIMUTH = '70'  # Example azimuth
KWP = '8'  # Example kWp
"""

# Construct the URL
url = f"https://api.forecast.solar/estimate/{PVPlant.LATITUDE}/{PVPlant.LONGITUDE}/{PVPlant.DECLINATION}/{PVPlant.AZIMUTH}/{PVPlant.KWP}?format=key-value&no_sun=1" # free mode usage

# reset JSON file --------------------------------------------------------------------------
result_data = "error"
with open(f'{PVPlant.FOLDER}solar_forecast.json', 'w') as outfile:
    json.dump(result_data, outfile, indent=4)


# Check API to take forecast --------------------------------------------------------------------------
try:
    #print("Starting to checking solar forecast")
    # Make the GET request to the Forecast.Solar API
    response = requests.get(url)
    response.raise_for_status()  # Raise an exception for bad status codes

    # Parse the JSON response
    data = response.json()

    # Reseting some variables
    forecastreceived = False

    # Dictionary to store structured data
    result_data = {
        "forecast": {
            "summary-wh-day": {},
            "hourly-watts": {
                "today": {},
                "tomorrow": {}
            },
            "hourly-wh-period": {
                "today": {},
                "tomorrow": {}
            },
            "hourly-wh-cumul": {
                "today": {},
                "tomorrow": {}
            }
        }
    }

# Check forecast for total Wh per day ----------------------------------------------------------------------------------
    if 'result' in data and 'watt_hours_day' in data['result']:  # Power per hour part
        forecastreceived = True
        # variable
        for entry in data['result']['watt_hours_day']:
            timestamp = datetime.strptime(entry['timestamp'], "%Y-%m-%d")
            hourly_watts = entry['value']
            # Creating variables
            now = datetime.now()
            Today = now.strftime("%d")
            Timestampday = timestamp.strftime("%d")
            if Today == Timestampday:  # Forecast is for today
                variable_name = f"today"
            else:  # Forecast is for tmr
                variable_name = f"tomorrow"
            # we write directly variable to the file
            result_data['forecast']['summary-wh-day'][variable_name] = hourly_watts
        forecastreceived = False

# Check forecast for watt per hour -------------------------------------------------------------------------------------
    if 'result' in data and 'watts' in data['result']:  # Power per hour part watt_hours_day
        forecastreceived = True
        # Reseting some variables
        firsthourday0 = 0
        lasthourday0 = 0
        firsthourday1 = 0
        lasthourday1 = 0
        forecastreceivedday = 0
        for entry in data['result']['watts']:
            timestamp = datetime.strptime(entry['timestamp'], "%Y-%m-%d %H:%M:%S")
            hourly_watts = entry['value']
            # Creating variables
            now = datetime.now()
            Today = now.strftime("%d")
            Timestampday = timestamp.strftime("%d")
            # Ready for checking forecast and creating lines per hour
            if Today == Timestampday:  # Forecast is for today
                # Creating todays's variables for each hour before first hour of prod
                startprod = int(timestamp.hour)
                while True:
                    if firsthourday0 >= startprod:  # We are in prod period
                        firsthourday0 = 25
                        break
                    else:  # We are in period before first hour of prod
                        variable_name = f"{firsthourday0}"
                        result_data['forecast']['hourly-watts']['today'][variable_name] = 0
                        firsthourday0 += 1
                # Creating today's variables for each hour when prod
                variable_name = f"{timestamp.hour}"
                # we write directly variable to the file
                result_data['forecast']['hourly-watts']['today'][variable_name] = hourly_watts
                # we fix last hour of today's prod
                lasthourday0 = int(timestamp.hour)
                forecastreceivedday = 0

            # elif Tomorrow == Timestampday: # Forecast is for tmr
            else:  # Forecast is for tmr
                # Creating todays's variables for each hour after last hour of prod
                if lasthourday0 < 25:
                    lasthourday0 += 1
                    while True:
                        if lasthourday0 >= 24:
                            lasthourday0 = 25
                            break
                        else:
                            variable_name = f"{lasthourday0}"
                            result_data['forecast']['hourly-watts']['today'][variable_name] = 0
                            lasthourday0 += 1
                # Creating tmr's variables for each hour before first hour of prod
                startprod = int(timestamp.hour)
                while True:
                    if firsthourday1 >= startprod:
                        firsthourday1 = 25
                        break
                    else:
                        variable_name = f"{firsthourday1}"
                        result_data['forecast']['hourly-watts']['tomorrow'][variable_name] = 0
                        firsthourday1 += 1
                # Creating tmr's variables for each hour when prod
                variable_name = f"{timestamp.hour}"
                # we write directly variable to the file
                result_data['forecast']['hourly-watts']['tomorrow'][variable_name] = hourly_watts
                # we fix last hour of tmr's prod
                lasthourday1 = int(timestamp.hour)
                forecastreceivedday = 1

    # Creating tmr's variables for each hour after last hour of prod
    if forecastreceived:
        if forecastreceivedday == 1:
            if lasthourday1 < 25:
                lasthourday1 += 1
                while True:
                    if lasthourday1 >= 24:
                        lasthourday1 = 25
                        forecastreceived = False
                        break
                    else:
                        variable_name = f"{lasthourday1}"
                        result_data['forecast']['hourly-watts']['tomorrow'][variable_name] = 0
                        lasthourday1 += 1

# Check forecast reponse for Wh per hour ------------------------------------------------------------------------------
    if 'result' in data and 'watt_hours_period' in data['result']:  # Power per hour part watt_hours_day
        forecastreceived = True
        # Reseting some variables
        firsthourday0 = 0
        lasthourday0 = 0
        firsthourday1 = 0
        lasthourday1 = 0
        forecastreceivedday = 0
        for entry in data['result']['watt_hours_period']:
            timestamp = datetime.strptime(entry['timestamp'], "%Y-%m-%d %H:%M:%S")
            hourly_watts = entry['value']
            # Creating variables
            now = datetime.now()
            Today = now.strftime("%d")
            Timestampday = timestamp.strftime("%d")
            # Ready for checking forecast and creating lines per hour
            if Today == Timestampday:  # Forecast is for today
                # Creating todays's variables for each hour before first hour of prod
                startprod = int(timestamp.hour)
                while True:
                    if firsthourday0 >= startprod:  # We are in prod period
                        firsthourday0 = 25
                        break
                    else:  # We are in period before first hour of prod
                        variable_name = f"{firsthourday0}"
                        result_data['forecast']['hourly-wh-period']['today'][variable_name] = 0
                        firsthourday0 += 1
                # Creating today's variables for each hour when prod
                variable_name = f"{timestamp.hour}"
                # we write directly variable to the file
                result_data['forecast']['hourly-wh-period']['today'][variable_name] = hourly_watts
                # we fix last hour of today's prod
                lasthourday0 = int(timestamp.hour)
                forecastreceivedday = 0

            # elif Tomorrow == Timestampday: # Forecast is for tmr
            else:  # Forecast is for tmr
                # Creating todays's variables for each hour after last hour of prod
                if lasthourday0 < 25:
                    lasthourday0 += 1
                    while True:
                        if lasthourday0 >= 24:
                            lasthourday0 = 25
                            break
                        else:
                            variable_name = f"{lasthourday0}"
                            result_data['forecast']['hourly-wh-period']['today'][variable_name] = 0
                            lasthourday0 += 1
                # Creating tmr's variables for each hour before first hour of prod
                startprod = int(timestamp.hour)
                while True:
                    if firsthourday1 >= startprod:
                        firsthourday1 = 25
                        break
                    else:
                        variable_name = f"{firsthourday1}"
                        result_data['forecast']['hourly-wh-period']['tomorrow'][variable_name] = 0
                        firsthourday1 += 1
                # Creating tmr's variables for each hour when prod
                variable_name = f"{timestamp.hour}"
                # we write directly variable to the file
                result_data['forecast']['hourly-wh-period']['tomorrow'][variable_name] = hourly_watts
                # we fix last hour of tmr's prod
                lasthourday1 = int(timestamp.hour)
                forecastreceivedday = 1

    # Creating tmr's variables for each hour after last hour of prod
    if forecastreceived:
        if forecastreceivedday == 1:
            if lasthourday1 < 25:
                lasthourday1 += 1
                while True:
                    if lasthourday1 >= 24:
                        lasthourday1 = 25
                        forecastreceived = False
                        break
                    else:
                        variable_name = f"{lasthourday1}"
                        result_data['forecast']['hourly-wh-period']['tomorrow'][variable_name] = 0
                        lasthourday1 += 1

# Check forecast reponse for Wh cumul per hour -------------------------------------------------------------------------
    if 'result' in data and 'watt_hours' in data['result']:  # Power per hour part watt_hours_day
        forecastreceived = True
        # Reseting some variables
        firsthourday0 = 0
        lasthourday0 = 0
        firsthourday1 = 0
        lasthourday1 = 0
        forecastreceivedday = 0
        for entry in data['result']['watt_hours']:
            timestamp = datetime.strptime(entry['timestamp'], "%Y-%m-%d %H:%M:%S")
            hourly_watts = entry['value']
            # Creating variables
            now = datetime.now()
            Today = now.strftime("%d")
            Timestampday = timestamp.strftime("%d")
            # Ready for checking forecast and creating lines per hour
            if Today == Timestampday:  # Forecast is for today
                # Creating todays's variables for each hour before first hour of prod
                startprod = int(timestamp.hour)
                while True:
                    if firsthourday0 >= startprod:  # We are in prod period
                        firsthourday0 = 25
                        break
                    else:  # We are in period before first hour of prod
                        variable_name = f"{firsthourday0}"
                        result_data['forecast']['hourly-wh-cumul']['today'][variable_name] = 0
                        firsthourday0 += 1
                # Creating today's variables for each hour when prod
                variable_name = f"{timestamp.hour}"
                # we write directly variable to the file
                result_data['forecast']['hourly-wh-cumul']['today'][variable_name] = hourly_watts
                # we fix last hour of today's prod
                lasthourday0 = int(timestamp.hour)
                forecastreceivedday = 0

            # elif Tomorrow == Timestampday: # Forecast is for tmr
            else:  # Forecast is for tmr
                # Creating todays's variables for each hour after last hour of prod
                if lasthourday0 < 25:
                    lasthourday0 += 1
                    while True:
                        if lasthourday0 >= 24:
                            lasthourday0 = 25
                            break
                        else:
                            variable_name = f"{lasthourday0}"
                            result_data['forecast']['hourly-wh-cumul']['today'][variable_name] = 0
                            lasthourday0 += 1
                # Creating tmr's variables for each hour before first hour of prod
                startprod = int(timestamp.hour)
                while True:
                    if firsthourday1 >= startprod:
                        firsthourday1 = 25
                        break
                    else:
                        variable_name = f"{firsthourday1}"
                        result_data['forecast']['hourly-wh-cumul']['tomorrow'][variable_name] = 0
                        firsthourday1 += 1
                # Creating tmr's variables for each hour when prod
                variable_name = f"{timestamp.hour}"
                # we write directly variable to the file
                result_data['forecast']['hourly-wh-cumul']['tomorrow'][variable_name] = hourly_watts
                # we fix last hour of tmr's prod
                lasthourday1 = int(timestamp.hour)
                forecastreceivedday = 1

    # Creating tmr's variables for each hour after last hour of prod
    if forecastreceived:
        if forecastreceivedday == 1:
            if lasthourday1 < 25:
                lasthourday1 += 1
                while True:
                    if lasthourday1 >= 24:
                        lasthourday1 = 25
                        #forecastreceived = False
                        break
                    else:
                        variable_name = f"{lasthourday1}"
                        result_data['forecast']['hourly-wh-cumul']['tomorrow'][variable_name] = 0
                        lasthourday1 += 1

    # Writing the hourly data to a new JSON file --------------------------------------------------------------------------
    if forecastreceived :
        with open(f'{PVPlant.FOLDER}solar_forecast.json', 'w') as outfile:
            json.dump(result_data, outfile, indent=4)
            print("Forecast received - datas saved")
    else :
        print("Forecast Not received - Server or API Error")

# If API Error---------------------------------------------------------------------------------------------------------

except requests.RequestException as e:
    print(f"Forecast - API request failed: {e}")
except ValueError as ve:
    print(f"Forecast - Failed to decode JSON response: {ve}")

# End -----------------------------------------------------------------------------------------------------------------
#print("Script execution completed.")