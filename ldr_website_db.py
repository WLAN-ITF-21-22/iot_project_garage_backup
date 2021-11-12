#!/usr/bin/env python3
# LDR imports
import cgitb ; cgitb.enable()
import os, time
import busio
import digitalio
import board
import RPi.GPIO as GPIO
from adafruit_bus_device.spi_device import SPIDevice
import paho.mqtt.client as mqtt
from datetime import datetime

# database imports
import MySQLdb

# imports for pubnub
from pubnub.pnconfiguration import PNConfiguration 
from pubnub.pubnub import PubNub 

### VARIABLES ###

# pins for LEDs, correspond to Raspberry Pi GPIO pins
LEDs = [18, 23, 24, 25]  # [Spot 1 LED, spot 2 LED, spot 3 LED, spot 4 LED]

# LDR configuration
sleepTime = 2 # in seconds
lightTreshhold = 0.5  # how much light is required for the LEDs to switch color (between 0 and 1).

# pins for LDRs, correspond to MCP3000 pins (0 - 7)
LDRpins = [0]  # [LDR 1, LDR 2, ...]

# how long can a parking spot be dark before it is seen as occupied?
timeBeforeOccupied = 6  # in seconds

# database information
dbHost = "localhost"
dbUser = "pi"
dbPasswd = "raspberry"
dbName = "garageDummy"


### FUNCTIONS ###

# Set up all LEDs that will be used
def initializeLEDs(LEDlist):
    for pin in LEDlist:
        GPIO.setup(pin, GPIO.OUT)
        GPIO.setup(pin, GPIO.LOW)
      

# read SPI data 8 possible adc's (0 thru 7)
def readadc(adcnum):
    if ((adcnum > 7) or (adcnum < 0)):
        return -1
    with adc:
        r = bytearray(3)
        spi.write_readinto([1, (8+adcnum)<<4,0], r)
        time.sleep(0.000005)
        adcout = ((r[1]&3) << 8) + r[2]
        return adcout
                       

# use readadc to read all LDR outputs, round them off (between 0.00 and 1.00) and put them in a list
def readLDR(LDRpinList):
    for LDRpin in LDRpinList:
        LDRvalue = round(readadc(LDRpin) / 1023,2)
        toggleState(LDRvalue, LDRpinList.index(LDRpin))
        printLDRdata(LDRvalue, LDRpinList.index(LDRpin))


# adjust the state if a specific time has passed
def toggleState(LDRvalue, index):
    if LDRvalue >= lightTreshhold:  
        # a light is shinging on the LDR, so it is probably not occupied
        lightCounterList[index] += 1
        if lightCounterList[index] >= maxCounter and currentState[index] == "occupied":
            changeState(index, "free")
    else:  
        # the light is not shinging on the LDR, so it is probably occupied
        darkCounterList[index] += 1
        if darkCounterList[index] >= maxCounter and currentState[index] == "free":
            changeState(index, "occupied")


# reset counters, note the time of chaning state (free/occupied) and udpate current occupation state
def changeState(index, occupationState):
    # reset counters
    lightCounterList[index] = 0
    darkCounterList[index] = 0
    # set new time since change
    timeSinceChange[index] = datetime.now()
    # change to...
    currentState[index] = occupationState
    # dim the LED if occupied
    if occupationState == "occupied":
        GPIO.output(LEDs[index], GPIO.LOW)
    # send data to database
    data = formatData(index)
    cursor.execute("INSERT INTO parking(uploadTime, spot, occupied, occupiedSince, licensePlate) VALUES(%s, %s, %s, %s, %s)", \
         (datetime.now(), data[0], data[1], data[2], data[3]))
    database.commit()
    # retreive data from database and send to webserver
    message = getDatabaseData()
    sendData(channel, message)


# when someone enters the parking, a certain spot will light up until they park there
def markParkingSpot():
    # search for first non-occupied spot in currentState list
    try:
        freeSpot = currentState.index("free")
    except ValueError:
        freeSpot = -1
    # light up the LED of the corresponding spot
    if freeSpot != -1:
        GPIO.output(LEDs[freeSpot], GPIO.HIGH)
    else:
        print("No free spaces!")


# display information on the time and light intensity
def printLDRdata(LDRvalue, index):
    # information
    now = datetime.now().strftime("%d/%m/%Y - %H:%M:%S")
    LDRvaluePercentage = int(LDRvalue * 100)
    lastChange = timeSinceChange[index].strftime("%d/%m/%Y - %H:%M:%S")

    # print information
    print("{}\tLight levels in parking spot {}: {}%".format(now, index, LDRvaluePercentage))
    print("This spot is {} since {}".format(currentState[index], lastChange))
    print("Light counter: {} - Dark counter: {}\n".format(lightCounterList[index], darkCounterList[index]))
    
    # (sending information is part of the chaneState() function)

# format data for db
def formatData(index):
    spot = index + 1
    occupied = (currentState[index] == 'occupied')  # true/false
    if occupied:
        occupiedSince = timeSinceChange[index].strftime("%d/%m/%Y %H:%M")
        licensePlate = "DUMMY PLATE"
    else:
        occupiedSince = "not occupied"
        licensePlate = "not occupied"
    return [spot, occupied, occupiedSince, licensePlate]


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


### INITIALIZATION ###

# Initialize SPI bus & GPIO
spi = busio.SPI(board.SCK, MOSI=board.MOSI, MISO=board.MISO)
GPIO.setmode(GPIO.BCM)

# Initialize control pins for adc
cs0 = digitalio.DigitalInOut(board.CE0)  # chip select
adc = SPIDevice(spi, cs0, baudrate= 1000000)

# Initizalize leds
initializeLEDs(LEDs)

# set up the timezone
os.environ['TZ'] = 'Europe/Brussels'
time.tzset()

# set up a counter, how many times the program has to see an LDR as "dark" before seeing it as "occupied"
maxCounter = timeBeforeOccupied / sleepTime
lightCounterList = []  # how many times the LDR has registered light
darkCounterList = []  # how many times the LDR has registered darkness
timeSinceChange = []  # mark time since last change
currentState = []  # whether the position is currently occupied or not
for l in LEDs:
    lightCounterList.append(0)
    darkCounterList.append(0)
    timeSinceChange.append(datetime.now())
    currentState.append("occupied") # initial value

# set up database
database = MySQLdb.connect(host=dbHost, user=dbUser, passwd=dbPasswd, db=dbName)
cursor = database.cursor()

# set up pubnub
pnconfig = PNConfiguration() 
pnconfig.subscribe_key = 'sub-c-874b9c7a-22a6-11ec-8587-faf056e3304c' 
pnconfig.publish_key = 'pub-c-37ee94e1-4340-4b02-864e-62686f330699' 
pubnub = PubNub(pnconfig) 
channel = 'projectGarage' 

### PROGRAM ###

try:
    while True:
        readLDR(LDRpins)
        time.sleep(sleepTime)
except KeyboardInterrupt:
    initializeLEDs(LEDs) # set all LEDs to low
    GPIO.cleanup()
    print("Program terminated succesfully")