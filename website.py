#!/usr/bin/env python 
# imports for pubnub
import cgitb
from typing import Collection ; cgitb.enable() 
from pubnub.pnconfiguration import PNConfiguration 
from pubnub.pubnub import PubNub 

# imports for mysql/mariadb
from datetime import datetime
import MySQLdb

# imports for testing with random data
import random
from random import randrange
import datetime


# pubnub configuration
pnconfig = PNConfiguration() 
pnconfig.subscribe_key = 'sub-c-874b9c7a-22a6-11ec-8587-faf056e3304c' 
pnconfig.publish_key = 'pub-c-37ee94e1-4340-4b02-864e-62686f330699' 
pubnub = PubNub(pnconfig) 
channel = 'projectGarage' 

# database configuration
database = MySQLdb.connect(host="localhost", user="pi", passwd="raspberry",db="garageDummy")
cursor = database.cursor()

# Example messages (random)
def randomSpot(i):
    occupied = random.randint(0,1) == 1
    occupiedSince = "not occupied"
    licensePlate = "not occupied"

    if occupied:
        occupiedSince = (datetime.datetime(2013, 9, 20,13,00) + datetime.timedelta(minutes=randrange(60)))\
            .strftime("%d/%m/%Y %H:%M")
        licensePlate = random.randint(999,10000)        
    return [i, occupied, occupiedSince, licensePlate]

def randomGarage():
    message = []
    for i in range(1, 5):
        parkingSpot = randomSpot(i)
        message.append(parkingSpot)
    return message


# Send data to pubnub
def sendData(channel, message):
    pubnub.subscribe().channels(channel).execute() 
    pubnub.publish().channel(channel).message(message).sync()
    # cleanup
    pubnub.unsubscribe().channels(channel).execute()


# extract data from MariaDB database
def getDatabaseData():
    # the expected columns: [time of upload, parking spot (1-4), occupied (0/1), occupied since (datetime), license plate]
    cursor.execute("SELECT * FROM parking ORDER BY 1 DESC")  # may result in a very large database pull
    
    # store last 4 occurences of every parking spot
    currentGarageData = {}  # stored in dictionary for easier checking if present
    for entry in cursor:
        if entry[1] not in currentGarageData:
            currentGarageData[entry[1]] = entry[1:5]
    
    # convert dictionary to list to ensure order of items
    listCurrentGarageData = []
    for i in range(1, 5):
        listCurrentGarageData.append(currentGarageData[i])
    
    return listCurrentGarageData


# send the message to pubnub
message = getDatabaseData()
sendData(channel, message)
