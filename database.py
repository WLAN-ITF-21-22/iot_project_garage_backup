"""
Database: Parking - utfmb4_unicode_ci
    Table 1: inside
        spot (int 1 - 4)
        occupied (int 0 - 1)
        occupied_or_free_since (varchar 255)
        license_plate (varchar 10)
    Table 2: log
        timestamp (datetime)
        spot (int 1 - 4)
        occupied (boolean 0 - 1)
        occupied_or_free_since (varchar 255)
        license_plate (varchar 10)
    Table 3: allowed
        license_plate (varchar 10)
        first_name (varchar 255)
        last_name (varchar 255)
        allowed_since (datetime)
        allowed_until (datetime)
"""

#!/usr/bin/env python
# library import
import os, time
from datetime import datetime
import MySQLdb
# import for random generation
import random
from random import randrange
from datetime import datetime

from pubnub.utils import datetime_now

# set up the timezone
os.environ['TZ'] = 'Europe/Brussels'
time.tzset()

# database information
db_host = "localhost"
db_user = "pi"
db_passwd = "raspberry"
db_name = "Parking"
# set up database
database = MySQLdb.connect(host=db_host, user=db_user, passwd=db_passwd, db=db_name)
cursor = database.cursor()

# functions

# create table
def create_tables():
    cursor.execute("DROP TABLE if exists Parking.inside")
    cursor.execute("DROP TABLE if exists Parking.log")
    cursor.execute("DROP TABLE if exists Parking.allowed")

    cursor.execute("CREATE TABLE inside(\
        spot int(11),\
        occupied tinyint(1),\
        occupied_or_free_since varchar(255),\
        license_plate varchar(10))")
    
    cursor.execute("CREATE TABLE log(\
        timestamp datetime,\
        spot int(11),\
        occupied tinyint(1),\
        occupied_or_free_since varchar(255),\
        license_plate varchar(10))")
    
    cursor.execute("CREATE TABLE allowed(\
        license_plate varchar(10),\
        first_name varchar(255),\
        last_name varchar(255),\
        allowed_since datetime,\
        allowed_until datetime)")
    
    database.commit()

# write 4 spots, where the data is unknown
def database_inside_initialize():
    # empty table
    cursor.execute("TRUNCATE TABLE inside")
    # insert data
    for i in range(1,5):
        cursor.execute("INSERT INTO inside(spot, occupied, occupied_or_free_since, license_plate) \
            VALUES(%s, %s, %s, %s)", \
            (i, False, "unknown", "unknown"))
    database.commit()

# function for writing to all tables
def database_write(table_name, information_list):
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
        cursor.execute("INSERT INTO allowed(license_plate, first_name, last_name, allowed_since, allowed_until) \
            VALUES(%s, %s, %s, %s, %s)", \
            (information_list[0], information_list[1], information_list[2], information_list[3], information_list[4]))
    database.commit()


create_tables()
database_inside_initialize()

# testing
# database_write("inside", [1, False, datetime.now(), "1-A23-666"])
# database_write("log", [datetime.now(), 1, False, datetime.now(), "1-A23-666"])
# database_write("allowed", ["1-AEN-165", "Lander", "Wuyts", datetime.now(), datetime.now()])
# database_write("inside", [1, False, datetime.now(), "1-A23-666"])



