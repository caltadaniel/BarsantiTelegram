from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
import telegram
import paho.mqtt.client as mqtt
import threading
import queue
import time
import logging
import paho.mqtt.publish as publish
import datetime
import matplotlib
matplotlib.use('Pdf')
import matplotlib.pyplot as plt
from logging.handlers import RotatingFileHandler

hostname = "192.168.1.9"

DEBUG = False
logFile = 'mqtt_telegram.log'
log_formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')

log_handler = RotatingFileHandler(logFile, mode='a', maxBytes=5*1024*1024, backupCount=2, encoding=None, delay=0)
log_handler.setFormatter(log_formatter)
log_handler.setLevel(logging.DEBUG)

prog_log = logging.getLogger('root')
prog_log.setLevel(logging.DEBUG)
prog_log.addHandler(log_handler)

prog_log.info("Start")
queueLock = threading.Lock()
queue_to_telegram = queue.Queue(10)
requestLock = threading.Lock()
request_queue = queue.Queue(10)


def build_menu(buttons,
               n_cols,
               header_buttons=None,
               footer_buttons=None):
    menu = [buttons[i:i + n_cols] for i in range(0, len(buttons), n_cols)]
    if header_buttons:
        menu.insert(0, header_buttons)
    if footer_buttons:
        menu.append(footer_buttons)
    return menu


class Request:
    def __init__(self, name, bot, chat_id, args):
        self.name = name
        self.args = args
        self.chat_id = chat_id
        self.bot = bot


class telegram_thread(threading.Thread):
    def __init__(self, queue_to_telegram):
        threading.Thread.__init__(self)
        self.queue_to_telegram = queue_to_telegram
        self.last_temperature_sala = None
        self.last_humidity_sala = None
        self.temp = []
        self.temp_time = []
        self.hum = []
        self.hum_time = []
        self.max_buffer_size = 10000
        self.bot = None
        self.default = 16
        self.actual_setpoint = self.default
        self.heater_enabled = False

    def run(self):
        while True:
            requestLock.acquire()
            if not request_queue.empty():
                #there is a new request from the user
                next_req = request_queue.get()
                requestLock.release()
            else:
                next_req = None
                requestLock.release()

            #handle the next req
            if next_req is not None:
                # if the bot is not defined, use this message to instantiate it
                if self.bot is None:
                    self.bot = next_req.bot
                if next_req.name == "/home/sala/temperature":
                    self.bot.send_message(chat_id=next_req.chat_id, text=r'Temperatura sala: {}, umidita sala: {}'.format(self.last_temperature_sala, self.last_humidity_sala))
                    prog_log.debug('Replying to temperature request to {}'.format(next_req.chat_id))
                if next_req.name == "home/sala/stufa":
                    if float(next_req.args[0]) > 15 and float(next_req.args[0]) < 24:
                        self.actual_setpoint = float(next_req.args[0])
                        self.heater_enabled = True
                        publish.single("home/sala/stufa", "1", hostname=hostname, port=1883)
                    else:
                        self.actual_setpoint = self.default
                        self.heater_enabled = False
                        publish.single("home/sala/stufa", "0", hostname=hostname, port=1883)
                if next_req.name == "home/sala/grafico":
                    fig,ax1 = plt.subplots()
                    ax1.plot(self.temp_time, self.temp, 'b-o')
                    ax1.set_xlabel('time (s)')
                    # Make the y-axis label, ticks and tick labels match the line color.
                    ax1.set_ylabel('Temperatura', color='b')
                    ax1.tick_params('y', colors='b')

                    ax2 = ax1.twinx()
                    ax2.plot(self.hum_time, self.hum, 'r-o')
                    ax2.set_ylabel('Umidita', color='r')
                    ax2.tick_params('y', colors='r')

                    fig.tight_layout()
                    plt.savefig('temp.png')
                    self.bot.send_photo(chat_id=next_req.chat_id, photo=open('temp.png','rb'))
                    prog_log.debug('Replying to plot request to {}'.format(next_req.chat_id))
            queueLock.acquire()
            if not queue_to_telegram.empty():
                # a new message is available on the queue
                msg = queue_to_telegram.get()
                queueLock.release()
                # output = "Received data {} from {}".format(msg.payload.decode('utf-8'), msg.topic)
                # print(output)
                try:
                    val = msg.payload.decode('utf-8')
                    numeric_val = float(val)
                    if msg.topic == 'home/sala/temperature':
                        #temp control
                        if self.heater_enabled:
                            if numeric_val < self.actual_setpoint:
                                # turn on
                                publish.single("home/sala/stufa", "1", hostname=hostname, port=1883)
                            else:
                                # turn off
                                publish.single("home/sala/stufa", "0", hostname=hostname, port=1883)
                        self.last_temperature_sala = numeric_val
                        self.temp.append(numeric_val)
                        self.temp_time.append(datetime.datetime.now())
                        if len(self.temp) >= self.max_buffer_size:
                            self.temp = self.temp[-self.max_buffer_size:]
                            self.temp_time = self.temp_time[-self.max_buffer_size:]
                    elif msg.topic == 'home/sala/humidity':
                        self.last_humidity_sala = numeric_val
                        self.hum.append(numeric_val)
                        self.hum_time.append(datetime.datetime.now())
                        if len(self.hum) >= self.max_buffer_size:
                            self.hum = self.hum[-self.max_buffer_size:]
                            self.hum_time = self.hum_time[-self.max_buffer_size:]
                except:
                    prog_log.critical('Unable to convert to int {}'.format(msg.payload.decode('utf-8')))
                #self.bot.send_message(chat_id=self.chat_id, text=output)
            else:
                queueLock.release()
            time.sleep(0.01)


class mqtt_thread(threading.Thread):
    def __init__(self, queue_to_telegram, queue_to_mqtt):
        threading.Thread.__init__(self)
        self.queue_to_telegram = queue_to_telegram
        self.queue_to_mqtt = queue_to_mqtt

    def on_connect(self,  client, userdata, flags, rc):
        # print("Connected with result code " + str(rc))
        # Subscribing in on_connect() means that if we lose the connection and
        # reconnect then subscriptions will be renewed.
        client.subscribe("home/#")
        prog_log.info('Connected to mqtt server')

    # The callback for when a PUBLISH message is received from the server.
    def on_message(self, client, userdata, msg):
        if DEBUG:
            print(msg.topic + " " + str(msg.payload))
        # prog_log.debug('Received message {} from {}'.format(str(msg.payload), msg.topic))
        queueLock.acquire()
        queue_to_telegram.put(msg)
        queueLock.release()

    def run(self):
        client = mqtt.Client()
        client.on_connect = self.on_connect  # Subscribing in on_connect() means that if we lose the connection and
        # reconnect then subscriptions will be renewed.
        client.on_message = self.on_message
        client.connect(hostname, 1883, 60)

        # Blocking call that processes network traffic, dispatches callbacks and
        # handles reconnecting.
        # Other loop*() functions are available that give a threaded interface and a
        # manual interface.
        client.loop_forever()


class TelegramBarsanti:
    def __init__(self, token, to_telegram_queue):
        self.token = token
        self.to_telegram_queue = to_telegram_queue
        self.updater = Updater(token,use_context=False)
        self.updater.dispatcher.add_handler(CommandHandler('start', self.start))
        self.updater.dispatcher.add_handler(CommandHandler('help', self.help))
        self.updater.dispatcher.add_handler(MessageHandler(Filters.text, self.generic_msg))
        self.tg_thread = telegram_thread(self.to_telegram_queue)
        self.tg_thread.start()

    def keyboard(self, bot, update):
        custom_keyboard = [['Heating on', 'Heating off'], ['Automatic control'], ['Get plot', 'Get actual temperature']]
        reply_markup = telegram.ReplyKeyboardMarkup(custom_keyboard)
        bot.send_message(chat_id=update.message.chat.id, text="Select the option", reply_markup=reply_markup)

    def start(self, bot, update):
        update.message.reply_text('Welcome to Barsanti control center')
        self.keyboard(bot, update)
        prog_log.debug('Received start request from telegram')

    def setpoint(self, bot, update):
        custom_keyboard = [['16', '17', '18', '19'], ['20', '21', '22', '23']]
        reply_markup = telegram.ReplyKeyboardMarkup(custom_keyboard)
        bot.send_message(chat_id=update.message.chat.id, text="Insert desired temperature", reply_markup=reply_markup)
        self.last_chat_id = update.message.chat.id
        self.last_request = "setpoint"
        prog_log.debug('Received new setpoint request')

    def temperature(self, bot, update):
        temp_req = Request("/home/sala/temperature", bot, update.message.chat.id, None)
        requestLock.acquire()
        request_queue.put(temp_req)
        requestLock.release()
        # self.bot.send_message(chat_id=self.chat_id, text="Trying to measure the actual temperature")
        prog_log.debug('Received temperature request from telegram')

    def plot(self, bot, update):
        temp_req = Request("home/sala/grafico", bot, update.message.chat.id, None)
        requestLock.acquire()
        request_queue.put(temp_req)
        requestLock.release()
        # self.bot.send_message(chat_id=self.chat_id, text="Trying to measure the actual temperature")
        prog_log.debug('Received plot request from telegram')

    def turn_on_heater(self, bot, update, val):
        prog_log.debug("Stufa ON")
        update.message.reply_text('Turning on the heater with the following setpoint: {}'.format(val))
        stufa_req = Request("home/sala/stufa", bot, update.message.chat.id, [str(val)])
        requestLock.acquire()
        request_queue.put(stufa_req)
        requestLock.release()

    def turn_off_heater(self, bot, update):
        prog_log.debug("Stufa OFF")
        update.message.reply_text('Turning off the heater')
        stufa_req = Request("home/sala/stufa", bot, update.message.chat.id, ["0.0"])
        requestLock.acquire()
        request_queue.put(stufa_req)
        requestLock.release()


    def help(self, bot, update):
        helpString = 'Benvenuto nel centro di controllo della casa.\n ' \
                     'I comandi disponibili sono: ' \
                     '1)\\stufaON'
        update.message.reply_text(helpString)


    def generic_msg(self,bot, update):
        #bot.send_message(chat_id=update.message.chat_id, text=update.message.text)
        if update.message.text == "Heating on":
            self.setpoint(bot,update)
        elif update.message.text == "Heating off":
            self.turn_off_heater(bot,update)
        elif update.message.text == "Get plot":
            self.plot(bot,update)
        elif update.message.text == "Get actual temperature":
            self.temperature(bot,update)
        elif update.message.chat_id == self.last_chat_id:
            if self.last_request == "setpoint":
                # we have the new setpoint
                self.setpoint_val = float(update.message.text)
                #text_d = "The new setpoint is {}".format(self.setpoint_val)
                #bot.send_message(chat_id=update.message.chat_id, text=text_d)
                self.turn_on_heater(bot, update, self.setpoint_val)
                self.keyboard(bot, update)

    def run(self):
        self.updater.start_polling(timeout=30, read_latency=10)
        self.updater.idle()

def getopts(argv):
    opts = {}  # Empty dictionary to store key-value pairs.
    while argv:  # While there are arguments left to parse...
        if argv[0][0] == '-':  # Found a "-name value" pair.
            opts[argv[0]] = argv[1]  # Add key and value to the dictionary.
        argv = argv[1:]  # Reduce the argument list by copying it starting from index 1.
    return opts

def main():

    from sys import argv
    myargs = getopts(argv)
    if '-t' in myargs:  # Example usage.
        print(myargs['-t'])
        token = myargs['-t']
        to_mqtt_Queue = queue.Queue(10)
        mqtt_thr = mqtt_thread(to_mqtt_Queue, queue_to_telegram)
        mqtt_thr.start()
        myTgBar = TelegramBarsanti(token, queue_to_telegram)
        myTgBar.run()
    else:
        print('Wrong args')



if __name__ == '__main__':
    main()
