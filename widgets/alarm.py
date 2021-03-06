import paho.mqtt.client as mqtt
import datetime
import database
import threading
import uuid
import time
from word2number import w2n

def on_connect(client, userdata, flags, rc):
    client.subscribe("openhome/alarm")
    print("Connected and waiting")

def on_disconnect(client, userdata, flags, rc):
    print("client disconnected")
    client.reconnect()

def respond(args):
    strings = ["resp", "alarm", "speak"]
    strings.extend(args)
    resp = '&'.join(strings)
    client.publish("openhome/controller", resp)

def error(message):
    strings = ["resp", "alarm", "err", message]
    resp = '&'.join(strings)
    client.publish("openhome/controller", resp)

def get_datetime_from_time(time):
    hour = w2n.word_to_num(time[0])
    if time[1] == "am" or time[1] == "pm":
        minute = 0
        ampm = time[1]
    else:
        minute = w2n.word_to_num(time[1])
        ampm = time[2]
        
    if ampm == "pm":
        hour += 12
        
    curr_datetime = datetime.datetime.now()
    parsed_datetime = datetime.datetime(year=curr_datetime.year, month=curr_datetime.month, day=curr_datetime.day, minute=minute, hour=hour)
    
    if parsed_datetime < curr_datetime:
        tomorrow_datetime = curr_datetime + datetime.timedelta(days=1)
        parsed_datetime = parsed_datetime.replace(year=tomorrow_datetime.year, month=tomorrow_datetime.month,
                                                  day=tomorrow_datetime.day) 
    return parsed_datetime
    
def set_alarm(args):
    parsed_datetime = get_datetime_from_time(args)
    print(parsed_datetime)
    db_list = database.read("alarm")

    for row in db_list:
        if row[1] == str(parsed_datetime.timestamp()):
            error('There is already an alarm set for that time')
            return

    id = str(uuid.uuid4())
    unix_alarm = parsed_datetime.timestamp()
    database.append("alarm", [[id, str(unix_alarm), 0, 0]])

def stop_alarm(args):
    db_list = database.read("alarm")
    found = False

    alarm = []
    for row in db_list:
        if row[2] == '1':
            database.delete("alarm", row[0])
            found = True

    if not found:
        error('I\'m sorry, there are no alarms to stop')

def snooze_alarm(args):
    db_list = database.read("alarm")
    found = False

    for row in db_list:
        if row[2] == '1':
            row[2] = '0'    # stop running
            row[3] = str(int(row[3])+1)   # snooze
            database.update("alarm", row, row[0])
            found = True

    if not found:
        error('I\'m sorry, there are no alarms to snooze')

def cancel_alarm(args):
    db_list = database.read("alarm")
    print("cancelling alarm at", args)
    uid = ''
    parsed_datetime = get_datetime_from_time(args)

    for row in db_list:
        if row[1] == str(parsed_datetime.timestamp()) or row[1] == str((parsed_datetime - datetime.timedelta(days=1)).timestamp()):
            uid = row[0]
            break

    if uid == '':
        error('I\'m sorry, there is no alarm set for ' + " ".join(args))
        return

    database.delete("alarm", uid)

functions = {"set_alarm": set_alarm,
             "stop_alarm": stop_alarm,
             "snooze_alarm": snooze_alarm,
             "cancel_alarm": cancel_alarm,
             }

def check_time():
    update_read_from_db = 0
        
    db_list = database.read("alarm")

    while True:
        if update_read_from_db >= 20:
            update_read_from_db = 0
            db_list = database.read("alarm")

        curr_timestamp = datetime.datetime.now()
        for row in db_list:
            if len(row) == 0:
                continue
            # row[0] is id
            # row[1] is timestamp
            # row[2] is running
            # row[3] is snooze count
            alarm_timestamp = datetime.datetime.fromtimestamp(int(float(row[1]))) + (int(row[3]) * datetime.timedelta(minutes=8))
            if alarm_timestamp < curr_timestamp and int(row[2]) == 0:
                print("Alarm trigger")
                row[2] = 1
                database.update("alarm", row, row[0])
                
                strings = ["resp", "alarm", "sound"]
                resp = '&'.join(strings)
                client.publish("openhome/controller", resp)
            else:
                continue

        update_read_from_db += 1
        time.sleep(.05)

def handler(client, userdata, message):
    msgSplit = str(message.payload.decode("utf-8")).split("&")
    print(msgSplit)
    if msgSplit[0] == "cmd":        #incoming command from controller
        args = ()
        for arg in msgSplit[3:]:
            args += (arg,)
        functions[msgSplit[2]](args)

    return True


if __name__ == '__main__':
    th = threading.Thread(target=check_time)
    th.start()

    # Create MQTT client and connect to broker
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = handler

    client.connect("localhost", 1883)
    client.loop_forever()
