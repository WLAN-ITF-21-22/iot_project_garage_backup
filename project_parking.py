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
from datetime import datetime

# database imports
import MySQLdb

# imports for pubnub
from pubnub.pnconfiguration import PNConfiguration 
from pubnub.pubnub import PubNub 

# imports for the barrier and the traffic light
from rpi_lcd import LCD
from time import sleep

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
LDR_pins = [0]  # [LDR 1, LDR 2, ...]

# how long can a parking spot be dark before it is seen as occupied?
time_before_occupied = 6  # in seconds

# database information
db_host = "localhost"
db_user = "pi"
db_passwd = "raspberry"
db_name = "garageDummy"


### FUNCTIONS ###

# Initialization: set up all LEDs that will be used from dictionary
def initialize_pins(LED_dictionary, input):
    for key in LED_dictionary:
        if input:
            GPIO.setup(LED_dictionary[key], GPIO.IN)
        else:
            GPIO.setup(LED_dictionary[key], GPIO.OUT)
            GPIO.setup(LED_dictionary[key], GPIO.LOW)

      

# Reading data: read SPI data 8 possible adc's (0 thru 7)
def readadc(adcnum):
    if ((adcnum > 7) or (adcnum < 0)):
        return -1
    with adc:
        r = bytearray(3)
        spi.write_readinto([1, (8+adcnum)<<4,0], r)
        time.sleep(0.000005)
        adcout = ((r[1]&3) << 8) + r[2]
        return adcout
                       

# Reading & writing data: use readadc to read all LDR outputs, round them off (between 0.00 and 1.00) and put them in a list
def read_LDR(LDR_pin_list):
    for LDR_pin in LDR_pin_list:
        LDR_value = round(readadc(LDR_pin) / 1023,2)
        toggle_state(LDR_value, LDR_pin_list.index(LDR_pin))
        print_LDR_data(LDR_value, LDR_pin_list.index(LDR_pin))


# Writing data: adjust the state if a specific time has passed
def toggle_state(LDR_value, index):
    if LDR_value >= light_treshhold:  
        # a light is shinging on the LDR, so it is probably not occupied
        light_counter_list[index] += 1
        if light_counter_list[index] >= max_counter and current_state[index] == "occupied":
            change_state(index, "free")
    else:  
        # the light is not shinging on the LDR, so it is probably occupied
        dark_counter_list[index] += 1
        if dark_counter_list[index] >= max_counter and current_state[index] == "free":
            change_state(index, "occupied")


# Writing data: reset counters, note the time of chaning state (free/occupied) and udpate current occupation state
def change_state(index, occupation_state):
    # reset counters
    light_counter_list[index] = 0
    dark_counter_list[index] = 0
    # set new time since change
    time_since_change[index] = datetime.now()
    # change to...
    current_state[index] = occupation_state
    # send data to database
    data = format_data(index)
    cursor.execute("INSERT INTO parking(upload_time, spot, occupied, occupied_since, licence_plate) VALUES(%s, %s, %s, %s, %s)", \
         (datetime.now(), data[0], data[1], data[2], data[3]))
    database.commit()
    # retreive data from database and send to webserver
    message = get_database_data()
    send_data_pubnub(channel, message)


# Writing data: when someone enters the parking, a certain spot will light up until they park there
def traffic_light_control():
    # search for first non-occupied spot in current_state list
    try:
        free_spot = current_state.index("free")
    except ValueError:
        free_spot = -1
    # what to do with free spots
    if free_spot != -1:
        print("A free space!")
    else:
        print("No free spaces!")


# Writing data: display information on the time and light intensity
def print_LDR_data(LDR_value, index):
    # information
    now = datetime.now().strftime("%d/%m/%Y - %H:%M:%S")
    LDR_value_percentage = int(LDR_value * 100)
    last_change = time_since_change[index].strftime("%d/%m/%Y - %H:%M:%S")

    # print information
    print("{}\tLight levels in parking spot {}: {}%".format(now, index, LDR_value_percentage))
    print("This spot is {} since {}".format(current_state[index], last_change))
    print("Light counter: {} - Dark counter: {}\n".format(light_counter_list[index], dark_counter_list[index]))
    
    # (sending information is part of the chaneState() function)

# Formatting data: for the database
def format_data(index):
    spot = index + 1
    occupied = (current_state[index] == 'occupied')  # true/false
    if occupied:
        occupied_since = time_since_change[index].strftime("%d/%m/%Y %H:%M")
        licence_plate = "DUMMY PLATE"
    else:
        occupied_since = "not occupied"
        licence_plate = "not occupied"
    return [spot, occupied, occupied_since, licence_plate]


# Sending data: to pubnub
def send_data_pubnub(channel, message):
    pubnub.subscribe().channels(channel).execute() 
    pubnub.publish().channel(channel).message(message).sync()
    # cleanup
    pubnub.unsubscribe().channels(channel).execute()


# Retreiving data: extract data from MariaDB database
def get_database_data():
    # the expected columns: [time of upload, parking spot (1-4), occupied (0/1), occupied since (datetime), license plate]
    cursor.execute("SELECT * FROM parking ORDER BY 1 DESC")  # may result in a very large database pull
    
    # store last 4 occurences of every parking spot
    current_garage_data = {}  # stored in dictionary for easier checking if present
    for entry in cursor:
        if entry[1] not in current_garage_data:
            current_garage_data[entry[1]] = entry[1:5]
    
    # convert dictionary to list to ensure order of items
    list_current_garage_data = []
    for i in range(1, 5):
        list_current_garage_data.append(current_garage_data[i])
    
    return list_current_garage_data


# Read data: measure the distance with the ultrasonic module
## NOTE: THE MORE TIMERS, THE SLOWER OUR PROGRAM
def measure_distance():
    # make sure the trigger is low
    GPIO.output(pin_dictionary_output["sonar_trigger"],0)
    time.sleep(0.2)
    # send puls
    GPIO.output(pin_dictionary_output["sonar_trigger"],1)
    time.sleep(0.00001)
    GPIO.output(pin_dictionary_output["sonar_trigger"],0)
    # start timer
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


# Write data: set the barrier angle
## NOTE: THE MORE TIMERS, THE SLOWER OUR PROGRAM
def set_angle(angle):
    duty = angle / 18 + 2
    GPIO.output(pin_dictionary_output["barrier"], 1)
    pwm.ChangeDutyCycle(duty)
    sleep(0.5)
    GPIO.output(pin_dictionary_output["barrier"], 0)
    pwm.ChangeDutyCycle(0)


# Write data: set the barrer mode
def set_barrier(distance):
    if distance < 10:
        # the barrier opens
        pwm.start(0)
        set_angle(145)
        # return text to display on the screen
        return "welkom"
    else:
        # the barrier closes
        pwm.start(0)
        set_angle(75)
        # return text to display on the screen
        return "even geduld"


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
        return "even geduld alstublieft"
    else:
        return "welkom, Bart"


# Write data: display the text on the LCD
def lcd_display(line1, line2, line3, line4):
    lcd.text(line1, 1)
    lcd.text(line2, 2)
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
initialize_pins(pin_dictionary_input, True)
initialize_pins(pin_dictionary_output, False)

# initialize barrier
pwm = GPIO.PWM(pin_dictionary_output["barrier"], 50)

# set up the timezone
os.environ['TZ'] = 'Europe/Brussels'
time.tzset()

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











### PROGRAM ###

try:
    while True:
        read_LDR(LDR_pins)
        time.sleep(sleep_time)
        lcd.clear()
except KeyboardInterrupt:
    lcd.clear()  # empty the screen
    set_angle(75)  # barrier down again
    initialize_pins(pin_dictionary_output, False) # set all LEDs to low
    GPIO.cleanup()
    print("Program terminated succesfully")