#!/usr/bin/env python 
import cgitb ; cgitb.enable() 
from pubnub.pnconfiguration import PNConfiguration 
from pubnub.pubnub import PubNub 

# import for testing
import random
from random import randrange
import datetime

pnconfig = PNConfiguration() 
pnconfig.subscribe_key = 'sub-c-874b9c7a-22a6-11ec-8587-faf056e3304c' 
pnconfig.publish_key = 'pub-c-37ee94e1-4340-4b02-864e-62686f330699' 
pubnub = PubNub(pnconfig) 
channel = 'projectGarage' 

# Example messages
def randomDate(start):
    return start + datetime.timedelta(minutes=randrange(60))


startDate = datetime.datetime(2013, 9, 20,13,00)

message = []
for i in range(1, 5):
    occupied = random.randint(0,1)
    occupiedSince = "not occupied"
    licensePlate = "not occupied"

    if occupied == 1:
        occupied = 'yes'
        occupiedSince = randomDate(startDate).strftime("%d/%m/%Y %H:%M")
        licensePlate = random.randint(999,10000)
    else:
        occupied = 'no'
        
    parkingSpot = [i, occupied, occupiedSince, licensePlate]
    message.append(parkingSpot)
print(message)

# send the message to pubnub
pubnub.subscribe().channels(channel).execute() 
pubnub.publish().channel(channel).message(message).sync()
