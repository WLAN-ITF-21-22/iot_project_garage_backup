#!/usr/bin/env python
# library import
import RPi.GPIO as GPIO
import time
from datetime import datetime
import MySQLdb
# import for random generation
import random
from random import randrange
import datetime

# connect to database
database = MySQLdb.connect(host="localhost", user="pi", passwd="raspberry",db="garageDummy")
# database select
cursor = database.cursor()


def randomData():
    randomDate = datetime.datetime(2013, 9, 20, 13, 00) + datetime.timedelta(minutes=randrange(60))
    randomSpot = random.randint(1,4)
    occupied = random.randint(0,1) == 1
    occupiedSince = "not occupied"
    licensePlate = "not occupied"

    if occupied:
        occupiedSince = randomDate.strftime("%d/%m/%Y %H:%M")
        licensePlate = random.randint(999,10000)
            
    return [randomSpot, occupied, occupiedSince, licensePlate]
    


for _ in range(10):
    data = randomData()
    # print(data)
    # wegschrijven naar DB
    cursor.execute("INSERT INTO parking(uploadTime, spot, occupied, occupiedSince, licensePlate) VALUES(%s, %s, %s, %s, %s)", \
         (datetime.datetime.now(), data[0], data[1], data[2], data[3]))
    database.commit()
    time.sleep(1)
