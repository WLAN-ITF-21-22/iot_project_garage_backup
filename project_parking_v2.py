"""
How it works:
    There exist three tables in the "Parking" database:
        Table 1: inside
            spot (int 1 - 4)
            occupied (int 0 - 1)
            occupied_or_free_since (varchar 255)
            license_plate (varchar 255)
        Table 2: log
            timestamp (datetime)
            spot (int 1 - 4)
            occupied (boolean 0 - 1)
            occupied_or_free_since (varchar 255)
            license_plate (varchar 255)
        Table 3: allowed
            license_plate (varchar 255)
            first_name (varchar 255)
            last_name (varchar 255)
    Once a car stands in front of the sonar for x seconds, a picture is taken of the license plate
        If the license plate is in the "allowed" table:
            the name is displaded on the screen with a welcome message
            the barrier opens
            the license plate is recorded for the database
        If the license plate is not in the "allowed" table:
            a message is displayed that that car is not allowed
            the barrier does not open
            no record is kept in the database
    Once a car parks in a certain spot for more than y seconds:
        a record is send to the database, stating which spot is occupied by which car since when
        this record is also sent when the car leaves
    
    HOW DO WE DO LEAVING THE PARKING? SECOND CAMERA, SONAR, ...?
    
    A traffic light at the entrance signals:
        red: no free spaces
        orange: the barrier is down, please wait
        green: the barrier is up, please enter
    A display at the entrance signals:
        the number of free spaces
        messages when a car stops in front of the barrier (Welcome, no free spots)
    A website signals:
        the current state of the parking
    An application signals:
        a push message when the parking is full
NOTE: everything that still requires attention has a comment starting with NOTE
"""


#!/usr/bin/env python3

### IMPORTS ####

# LDR imports
import cgitb ; cgitb.enable()
import os, time
import busio
import digitalio
import board
import RPi.GPIO as GPIO
from adafruit_bus_device.spi_device import SPIDevice
#import paho.mqtt.client as mqtt
from datetime import datetime
import _thread
import http.client, urllib

# database imports
import MySQLdb

# imports for pubnub
from pubnub.pnconfiguration import PNConfiguration 
from pubnub.pubnub import PubNub 

# imports for the barrier and the traffic light
from rpi_lcd import LCD
from time import sleep, thread_time_ns

# imports for the USB camera
import cv2
import imutils
import numpy as np
import pytesseract


### VARIABLES ###

# pins for LEDs, correspond to Raspberry Pi GPIO pins
pin_dictionary_output = {
    "barrier": 12,
    "traffic_green": 21,
    "traffic_orange": 20,
    "traffic_red": 16,
    "sonar_trigger": 23
}

pin_dictionary_input = {
    "sonar_echo": 24
}


# LDR configuration
sleep_time = 2 # in seconds
light_treshhold = 0.5  # how much light is required for the LEDs to switch color (between 0 and 1).

# pins for LDRs, correspond to MCP3000 pins (0 - 7)
LDR_pins = (0,1,2,3)

# how long can a parking spot be dark before it is seen as occupied?
time_before_occupied = 6  # in seconds

# how long until the Ultrasound module registers a car
time_before_sonar = 4  # in seconds

# how close can the sonar measure something for it to be within the allowed distance
distance_min = 0.5
distance_max = 10

# database information
db_host = "localhost"
db_user = "pi"
db_passwd = "raspberry"
db_name = "Parking"


### FUNCTIONS ###

# Initialization: set up all LEDs that will be used from dictionary
def LED_initialize(LED_dictionary, input):
    for key in LED_dictionary:
        if input:
            GPIO.setup(LED_dictionary[key], GPIO.IN)
        else:
            GPIO.setup(LED_dictionary[key], GPIO.OUT)
            GPIO.setup(LED_dictionary[key], GPIO.LOW)


# Read data: measure the distance with the ultrasonic module
def sonar_measure_distance():
    # make sure the trigger is low
    GPIO.output(pin_dictionary_output["sonar_trigger"],0)
    time.sleep(0.2)
    # send puls
    GPIO.output(pin_dictionary_output["sonar_trigger"],1)
    time.sleep(0.00001)
    GPIO.output(pin_dictionary_output["sonar_trigger"],0)
    # start timer
    pulse_start = time.time()
    while GPIO.input(pin_dictionary_input["sonar_echo"])==0:
        pulse_start = time.time()
    # end timer
    while GPIO.input(pin_dictionary_input["sonar_echo"])==1:
        pulse_end = time.time()
    # calculate distance
    pulse_duration = pulse_end - pulse_start
    pulse_distance = (pulse_duration * 17150) / 2
    # print and return distance
    print ("Distance : %.1f" % pulse_distance)
    return pulse_distance


# Read data: USB camera capture
def capture_license_plate():
    # read USB camera
    frame = camera.read()
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)  # convert to grayscale
    gray = cv2.bilateralFilter(gray, 11, 17, 17)  # blur to reduce noise
    edged = cv2.Canny(gray, 30, 200)  # perform Edge detection
    # find contours of license plate
    cnts = cv2.findContours(edged.copy(), cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    cnts = imutils.grab_contours(cnts)
    cnts = sorted(cnts, key = cv2.contourArea, reverse = True)[:10]
    screenCnt = None
    # draw rectangle around license plate
    for c in cnts:
      peri = cv2.arcLength(c, True)
      approx = cv2.approxPolyDP(c, 0.018 * peri, True)
      if len(approx) == 4:
        screenCnt = approx
        break  # exit for-loop if full rectangle is drawn
    # make sure the contour is properly detected
    if screenCnt is None:
      detected = 0
      return "No contour detected"
    else:
      detected = 1
    # draw the actual rectangle
    if detected == 1:
      cv2.drawContours(frame, [screenCnt], -1, (0, 255, 0), 3)
    # cut out license plate
    mask = np.zeros(gray.shape,np.uint8)
    new_image = cv2.drawContours(mask,[screenCnt],0,255,-1,)
    new_image = cv2.bitwise_and(frame,frame,mask=mask)
    (x, y) = np.where(mask == 255)
    (topx, topy) = (np.min(x), np.min(y))
    (bottomx, bottomy) = (np.max(x), np.max(y))
    Cropped = gray[topx:bottomx+1, topy:bottomy+1]
    # read license plate
    text = pytesseract.image_to_string(Cropped, config='--psm 6')
    return text


# Read data: check if the license plate is in the allowed list.
def license_plate_allowed(license_plate):
    # get a list of allowed license plates
    allowed_database_list = db_read("allowed")
    allowed_license_plates = []
    for entry in allowed_database_list:
        allowed_license_plates.append(entry[0])
    # check if the license plate is allowed
    return license_plate in allowed_license_plates  # True or False


# Write data: set the barrier angle
def barrier_set_angle(angle):
    duty = angle / 18 + 2
    GPIO.output(pin_dictionary_output["barrier"], 1)
    pwm.ChangeDutyCycle(duty)
    sleep(0.5)
    GPIO.output(pin_dictionary_output["barrier"], 0)
    pwm.ChangeDutyCycle(0)


# Write data: set the barrer mode
def barrier_check(distance):
    if distance <= distance_max and distance >= distance_min:
        # wait a number of seconds to make sure there is something in front of the sensor
        distance_counter[0] += 1
        if distance_counter[0] < distance_max_counter:  # NOTE: does resetting the counter to 0 not result in this message appearing too quickly?
            return "Even geduld alstublieft"
        else:
            distance_counter[0] = 0
            # check if the license plate is allowed
            license_plate = capture_license_plate()
            if license_plate_allowed(license_plate):
                # the barrier opens
                traffic_ligth("green")
                is_green[0] = True
                pwm.start(0)
                barrier_set_angle(145)
                # save the license plate for later database assignment
                license_plates_inside_not_parked.append(license_plate)
                # return text to display on the screen
                # return text to display on the screen
                name = db_read("allowed", license_plate, "license_plate", "first_name")[0] \
                    + " " \
                    + db_read("allowed", license_plate, "license_plate", "last_name") 
                return "Welkom {}".format(name)  # NOTE: this needs to be tested properly might give errors
            else:
                return "Not on the list: {}".format(license_plate.capitalize())
    else:
        # the barrier closes
        is_green[0] = False
        pwm.start(0)
        barrier_set_angle(75)
        # return text to display on the screen
        return ""


# Reading data: read SPI data 8 possible adc's (0 thru 7)
def LDR_read_adc(adcnum):
    if ((adcnum > 7) or (adcnum < 0)):
        return -1
    with adc:
        r = bytearray(3)
        spi.write_readinto([1, (8+adcnum)<<4,0], r)
        time.sleep(0.000005)
        adcout = ((r[1]&3) << 8) + r[2]
        return adcout
                       

# Reading & writing data: use LDR_read_adc to read all LDR outputs, round them off (between 0.00 and 1.00) and put them in a list
def LDR_execute():
    for LDR_pin in range(0,4):
        LDR_value = round(LDR_read_adc(LDR_pin) / 1023,2)
        LDR_check_state(LDR_value, LDR_pin)
        LDR_print_data(LDR_value, LDR_pin)


# Writing data: adjust the state if a specific time has passed
def LDR_check_state(LDR_value, index):
    if LDR_value >= light_treshhold:  
        # a light is shinging on the LDR, so it is probably not occupied
        light_counter_list[index] += 1
        if light_counter_list[index] >= max_counter and current_state[index] == "occupied":
            LDR_change_state(index, "free")
    else:  
        # the light is not shinging on the LDR, so it is probably occupied
        dark_counter_list[index] += 1
        if dark_counter_list[index] >= max_counter and current_state[index] == "free":
            LDR_change_state(index, "occupied")


# Writing data: reset counters, read the time of chaning state (free/occupied) and update current occupation state
def LDR_change_state(index, occupation_state):
    # reset counters
    light_counter_list[index] = 0
    dark_counter_list[index] = 0
    # set new time since change
    time_since_change[index] = datetime.now()
    # change to...
    current_state[index] = occupation_state
    # send data to database
    db_write("log", db_format(True, index, occupation_state))
    db_write("inside", db_format(False, index, occupation_state))
    # retreive data from database and send to webserver
    message = db_read("inside")
    webserver_send_data(channel, message)


# Writing data: display information on the time and light intensity
def LDR_print_data(LDR_value, index):
    # information
    now = datetime.now().strftime("%d/%m/%Y - %H:%M:%S")
    LDR_value_percentage = int(LDR_value * 100)
    last_change = time_since_change[index].strftime("%d/%m/%Y - %H:%M:%S")

    # print information
    print("{}\tLight levels in parking spot {}: {}%".format(now, index, LDR_value_percentage))
    print("This spot is {} since {}".format(current_state[index], last_change))
    print("Light counter: {} - Dark counter: {}\n".format(light_counter_list[index], dark_counter_list[index]))
    
    # (sending information is part of the chaneState() function)


def parking_count_free_spaces():
    free_spaces = 0
    for spot in current_state:
        if spot == "free":
            free_spaces += 1
    return free_spaces


# Writing data: when someone enters the parking, a certain spot will light up until they park there
def parking_check_spaces():
    if not is_green[0]:
        # the ligth can only go orange or red when it is not green, when the barrier is not open
        if parking_count_free_spaces() != 0:
            # free spaces
            is_full[0] = False
            traffic_ligth("orange")
        else:
            # no free spaces
            if not is_full[0]:
                app_send_push()
                is_full[0] = True
            traffic_ligth("red")  # NOTE: the default color seems to be red. Why?


# Write data: control traffic light
def traffic_ligth(red_orange_green):
    for pin in pin_dictionary_output:
        # only select 'traffic_' pins
        if pin.startswith("traffic_"):
            # only light the pin that corrensponds to the entered color
            if pin.endswith(red_orange_green):
                GPIO.output(pin_dictionary_output[pin], 1)
            else:
                GPIO.output(pin_dictionary_output[pin], 0)
    # return message
    if red_orange_green == "red":
        return "geen plaatsen meer vrij"
    if red_orange_green == "orange":
        return "even gedult alstublieft"
    else:
        return "welkom, Bart"


# format data for sending to database
def db_format(log, index, occupation_state):
    information_list = []
    if log:
        information_list.append(datetime.now())
    information_list.append(index)
    information_list.append(occupation_state == "occupied")  # 0 if free, 1 if occupied
    information_list.append(time_since_change[index])
    if occupation_state == "free":
        information_list.append("Not occupied")
    else:
        information_list.append(license_plates_inside_not_parked[0])
        # remove said license plate: that car has parked
        license_plates_inside_not_parked.pop(0)
    return information_list


# Write data: writing to all tables
def db_write(table_name, information_list):
    if table_name == "inside":
        cursor.execute("UPDATE inside \
            SET occupied = %s, occupied_or_free_since = %s, license_plate = %s \
            WHERE spot = %s", \
            (information_list[1], information_list[2], information_list[3], information_list[0]))
    elif table_name == "log":
        cursor.execute("INSERT INTO log(timestamp, spot, occupied, occupied_or_free_since, license_plate) \
            VALUES(%s, %s, %s, %s, %s)", \
            (information_list[0], information_list[1], information_list[2], information_list[3], information_list[4]))
    else:
        cursor.execute("INSERT INTO allowed(license_plate, first_name, last_name) \
            VALUES(%s, %s, %s)", \
            (information_list[0], information_list[1], information_list[2]))
    database.commit()


# Read data: return database data as a list
def db_read(table_name, criterium=False, criterium_row=None, select_row=None):
    # table_name = inside, log or allowed
    if criterium:
        # select specific item
        cursor.execute("SELECT %s FROM %s WHERE %s = %s", (select_row, table_name, criterium_row, criterium))
    else:
        # just select whole database
        cursor.execute("SELECT * FROM %s", (table_name))  # may result in a very large database pull
    return cursor


# Write data: message to pubnub
def webserver_send_data(channel, message):
    pubnub.subscribe().channels(channel).execute() 
    pubnub.publish().channel(channel).message(message).sync()
    # cleanup
    pubnub.unsubscribe().channels(channel).execute()


# Write data: push to application
def app_send_push():
    conn = http.client.HTTPSConnection("api.pushover.net:443")
    conn.request("POST", "/1/messages.json",
    urllib.parse.urlencode({
        "token": "aihasrdogan6j9xbjh6rz4odfo8o6r",
        "user": "upp199kgzkpesfxici95q1kpdnpa5b",
        "message": "parking vol",
    }), { "Content-type": "application/x-www-form-urlencoded" })
    conn.getresponse()


# Write data: display the text on the LCD
def LCD_write_display(line3, line4):
    # first line: general information
    lcd.text("Private tractor parking", 1)
    # second line: how many free spaces
    lcd.text("There is/are {} free spot(s)".format(parking_count_free_spaces()), 2)
    # third line: free
    # fourth line: messages
    lcd.text(line3, 3)
    lcd.text(line4, 4)


### INITIALIZATION AND CONFIGURATION ###

# Initialize SPI bus & GPIO
spi = busio.SPI(board.SCK, MOSI=board.MOSI, MISO=board.MISO)
GPIO.setmode(GPIO.BCM)

# Initialize control pins for adc
cs0 = digitalio.DigitalInOut(board.CE0)  # chip select
adc = SPIDevice(spi, cs0, baudrate= 1000000)

# Initizalize leds
LED_initialize(pin_dictionary_input, True)
LED_initialize(pin_dictionary_output, False)

# initialize barrier
pwm = GPIO.PWM(pin_dictionary_output["barrier"], 50)

# set up the timezone
os.environ['TZ'] = 'Europe/Brussels'
time.tzset()

# set up database
database = MySQLdb.connect(host=db_host, user=db_user, passwd=db_passwd, db=db_name)
cursor = database.cursor()

# set up pubnub
pnconfig = PNConfiguration() 
pnconfig.subscribe_key = 'sub-c-874b9c7a-22a6-11ec-8587-faf056e3304c' 
pnconfig.publish_key = 'pub-c-37ee94e1-4340-4b02-864e-62686f330699' 
pubnub = PubNub(pnconfig) 
channel = 'projectGarage' 

# LCD
lcd = LCD()

# USB camera
camera = cv2.VideoCapture(0)

# count how long something is in front of the barrier
distance_counter = [0]
distance_max_counter = time_before_sonar / sleep_time

# set up a counter, how many times the program has to see an LDR as "dark" before seeing it as "occupied"
max_counter = time_before_occupied / sleep_time
light_counter_list = []  # how many times the LDR has registered light
dark_counter_list = []  # how many times the LDR has registered darkness
time_since_change = []  # mark time since last change
current_state = []  # whether the position is currently occupied or not
for l in LDR_pins:
    light_counter_list.append(0)
    dark_counter_list.append(0)
    time_since_change.append(datetime.now())
    current_state.append("occupied") # initial value

# set up a dataset which remembers which cars are inside before they've chosen a parkingspot
license_plates_inside_not_parked = []

# push melding
is_full = [False]

# traffic ligth, switch back to orange,
is_green = [False]

### PROGRAM ###

try:
    while True:
        # thread 1: LDR reading, sending data to database
        _thread.start_new_thread( LDR_execute, () )
        # thread 2: Ultrasound distance measuring
        distance = _thread.start_new_thread( sonar_measure_distance, ())
        distance = tuple([distance])
        # thread 3: moving the barrier
        barrier_text = _thread.start_new_thread( barrier_check, (distance) )
        # thread 4: set the LCD display
        _thread.start_new_thread( LCD_write_display, ('lijn1','lijn2','lijn3',"barrier_text"))

        # wait and clear
        time.sleep(sleep_time)
        lcd.clear()
except KeyboardInterrupt:
    lcd.clear()  # empty the screen
    barrier_set_angle(75)  # barrier down again
    LED_initialize(pin_dictionary_output, False) # set all LEDs to low
    GPIO.cleanup()
    print("Program terminated succesfully")
