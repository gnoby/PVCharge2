import configparser, logging, time
import random
import threading

from flask import Flask,request,render_template

from pv import read_pv_voltage
from logging.handlers import RotatingFileHandler
from geopy.geocoders import Nominatim
from teslapy import Tesla

app = Flask(__name__)

def setuplog():
    global logger
    logger = logging.getLogger('pv_charge_logger')
    logger.setLevel(logging.INFO)

    fileHandler = RotatingFileHandler(config.get('charge', 'LOG_FILE_NAME'), mode='a', encoding='utf-8',
                                          maxBytes=config.getint('charge', 'LOG_FILE_MAX_BYTES'), backupCount=5)

    fileHandler.setLevel(logging.INFO)

    sysHandler = logging.StreamHandler()
    sysHandler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(message)s')

    fileHandler.setFormatter(formatter)
    sysHandler.setFormatter(formatter)

    logger.addHandler(fileHandler)
    logger.addHandler(sysHandler)


###############################################################################################################
# Logging-Shortcut
###############################################################################################################
def log(value):
    logger.info(value)

def init_tesla():
    global vehicle_data
    global tesla
    with Tesla(config.get('charge', 'tesla_account'), False, False) as tesla:
        # Token muss in cache.json vorhanden sein. Vorher einfach z.B. gui.py aufrufen und 1x einloggen
        #tesla.fetch_token()
        vehicles = tesla.vehicle_list()
        vehicle_data = vehicles[0].get_vehicle_data()
        return vehicles[int(0)]

def startCharging():
    log("start aktuell nicht")
    #with Tesla(config.get('charge', 'tesla_account'), False, False) as tesla:
    #    vehicles = tesla.vehicle_list()
    #    vehicle_data = vehicles[0].get_vehicle_data()
    #    vehicle = vehicles[0]
    #    if vehicle_data['charge_state']['charging_state'] != 'Charging' and vehicle_data['charge_state']['charging_state'] != 'Complete':
    #        vehicle.command('START_CHARGE')
    #        log("Started Charging!")
    # else:
    # log("Did not start charging because vehicle was already charging!")


def startCharging2():
    with Tesla(config.get('charge', 'tesla_account'), False, False) as tesla:
        vehicles = tesla.vehicle_list()
        vehicle_data = vehicles[0].get_vehicle_data()
        vehicle = vehicles[0]
        if vehicle_data['charge_state']['charging_state'] != 'Charging' and vehicle_data['charge_state']['charging_state'] != 'Complete':
            vehicle.command('START_CHARGE')
            log("Started Charging!")
        else:
            log("Did not start charging because vehicle was already charging!")
def stopCharging():
    with Tesla(config.get('charge', 'tesla_account'), False, False) as tesla:
        vehicles = tesla.vehicle_list()
        vehicle_data = vehicles[0].get_vehicle_data()
        vehicle = vehicles[0]
        if vehicle_data['charge_state']['charging_state'] == 'Charging':
            vehicle.command('STOP_CHARGE')
            log("stop charging")
        else:
            log("Did not stop charging because vehicle was not charging!")

def logStatus():
    data = vehicle_data
    #vehicles = tesla.vehicle_list()
    #data = vehicles[0].get_vehicle_data()
    #data = vehicles[0].get_vehicle_data()
    #data = vehicle.get_vehicle_data()
    log('Online Current Ampere: ' + str(data['charge_state']['charge_current_request'])
        + ', Charge Energy added: ' + str(data['charge_state']['charge_energy_added'])
        + ', Charge Miles ideal: ' + str(data['charge_state']['charge_miles_added_ideal'])
        + ', Charge Limit: ' + str(data['charge_state']['charge_limit_soc'])
        + ', Charge Status: ' + str(data['charge_state']['charging_state'])
        + ', Battery Lvl: ' + str(data['charge_state']['battery_level']))
    return data

def isCarAtHome(vehicle_data):
    # Ist das Auto zu Hause?
    data = vehicle_data
    coords = '%s, %s' % (
        data['drive_state']['latitude'], data['drive_state']['longitude'])
    osm = Nominatim(user_agent='TeslaPy')
    location = osm.reverse(coords).address

    if location != config.get('charge', 'HOME_LOCATION'):
        log('Vehicle not at home. Doing nothing')
        return False
    return True

def setChargingAmps(vehicle_data_param, vehicle_param, amps):
    global vehicle_data
    global vehicle
    with Tesla(config.get('charge', 'tesla_account'), False, False) as tesla:
        vehicles = tesla.vehicle_list()
        vehicle_data = vehicles[0].get_vehicle_data()
        vehicle = vehicles[0]
        if vehicle_data['charge_state']['charge_current_request'] != amps:
            amps = min([amps,16])
            log("Set Charging Amps: " + str(amps))
            vehicles[0].command('CHARGING_AMPS', charging_amps=amps)
            if amps < 5:
                vehicles[0].command('CHARGING_AMPS', charging_amps=amps)
        else:
            log("Did not set Charging Amps, weil keine Veraenderung: " + str(amps))
def tesla_pv_charge_control():

    # Auto schläft, kann nicht geladen werden
    if vehicle['state'] == "asleep":
        log('Sleeping, can not set charge!')
        return
    # Auto wach
    # Status ausgeben
    vehicle_data = logStatus()

    # Auto nicht angesteckt, kann nicht geladen werden
    if vehicle_data['charge_state']['charging_state'] == 'Disconnected':
        log('Charger disconnected, can not set charge!')
        return

    # Ist das Auto zu Hause?
    if not isCarAtHome(vehicle_data):
        return

    # Overwrite-Modus: Laden unabhängig von der PV-Leistung
    if config.get('charge', 'OVERWRITE_MODE') == 'TRUE':
        log("Overwrite Modus = true.")
        startCharging(vehicle_data, vehicle)
        setChargingAmps(vehicle_data, vehicle, config.getint('charge', 'OVERWRITE_AMPERE'))
        return

    # Hier wird über ein Modul die aktuelle Leistung der PV-Anlage ausgelesen. Bei mir über das Web-Interface Kostal Pico. Dies muss spezifisch angepasst werden.
    pv_voltage = read_pv_voltage()
    kilowatts = pv_voltage / 1000

    ampere_rounded = round(
        kilowatts * config.getint('charge', 'AMPERE_FACTOR1') / config.getint('charge', 'AMPERE_FACTOR2'))

    # Setzen einer minimal Ampere Leistung zu der immer geladen wird, auch wenn nicht genügend Sonne ist.
    if config.getint('charge', 'fixed_minimum_ampere') > 0:
        if config.getint('charge', 'fixed_minimum_ampere') > ampere_rounded:
            log("fixed_minimum_ampere set! setting: " + config.get('charge',
                                                                   'fixed_minimum_ampere') + " instead of: " + str(
                ampere_rounded))
        ampere_rounded = max(ampere_rounded, config.getint('charge', 'fixed_minimum_ampere'))

    log('Kilowatt PV-Anlage: ' + str(kilowatts) + ' -> Ampere Roundend: ' + str(ampere_rounded) + ', Approx KW:' + str(
        ampere_rounded * (11 / 16)))
    # > 1 Ampere -> Laden
    if ampere_rounded > config.getint('charge', 'MINIMUM_AMPERE_LEVEL'):
        startCharging(vehicle_data, vehicle)
        setChargingAmps(vehicle_data, vehicle, ampere_rounded)

    # <= 1 Ampere -> Lohnt sich nicht (ca. 300 W Grundlast), laden stoppen und etwas warten, damit nicht ständig das Laden gestart und gestoppt wird
    #else:
    #    log("Low PV-Power....")
    #    setChargingAmps(vehicle_data, vehicle, 1)
    #    time.sleep(config.getint('charge', 'WAIT_SECONDS_AFTER_CHARGE_STOP'))
    #    pv_voltage = read_pv_voltage()
    #    ampere_rounded = round(
    #        kilowatts * config.getint('charge', 'AMPERE_FACTOR1') / config.getint('charge', 'AMPERE_FACTOR2'))
        # Nur wenn nach Wartezeit immer noch unter 1
    #    if ampere_rounded <= config.getint('charge', 'MINIMUM_AMPERE_LEVEL'):
    #        stopCharging(vehicle_data, vehicle)
    #        log("sleeping after stopcharge " + str(config.getint('charge', 'WAIT_SECONDS_AFTER_CHARGE_STOP')))
    #        time.sleep(config.getint('charge', 'WAIT_SECONDS_AFTER_CHARGE_STOP'))
    #    else:
    #        log("PV-Voltage higher. continue: " + str(pv_voltage))
    print('')



def background_schleife():
    global config
    global vehicle
    print("Hello World!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
    config = configparser.ConfigParser()
    config.read('constants_pv_charging.ini', encoding='utf-8')

    # Log initialisieren
    setuplog()

    log("start schleife")

    # Fahrzeug aus API lesen
    vehicle = init_tesla()

    i = 0
    while True:
        try:
            time.sleep(config.getint('charge', 'SLEEP_BETWEEN_CALLS'))
            log("next iteration!")
            i = i + 1
            # Jedes Mal die Config einlesen, da sich etwas verändert haben könnte
            config = configparser.ConfigParser()
            config.read('constants_pv_charging.ini', encoding='utf-8')

            if config.get('charge', 'pause') == 'FALSE':
                tesla_pv_charge_control()
            else:
                log('Pausiert.')
            # Jedes 30. Mal init_tesla aufrufen, da scheinbar irgendwann der token abläuft
            if i > 10:
                vehicle = init_tesla()
                i = 0
                log("reinit tesla")

        except Exception as exception:
            log(exception)
            try:
                if i > 10:
                    vehicle = init_tesla()
                    i = 0
                    log("reinit tesla")
            except Exception as exception:
                log(exception)

def getVehicle():
    tesla = Tesla(config.get('charge', 'tesla_account'), False, False)
    vehicles = tesla.vehicle_list()
    vehicle = vehicles[0]
    return vehicle

def setup_app(app):

    # Endlosschleife Aufruf pv_charge_control mit x Sekunden Pause
    download_thread = threading.Thread(target=background_schleife, name="background_schleife")
    download_thread.start()


setup_app(app)

@app.route("/", methods=["GET", "POST"])
def home():
    if request.method == "POST":
        print(request.form["name"])
        print(request.form["email"])

    data = [
        {
            'name': 'Audrin',
            'place': 'kaka',
            'mob': '7736'
        }
    ]
    return render_template("home.html" , data=data)

@app.route('/displaylog')
def fps():
    logfilename = config.get('charge', 'LOG_FILE_NAME')
    resultstring = ""
    for line in reversed(open(logfilename, 'rb').readlines()):
        resultstring += line.rstrip().decode("utf-8") +"'<br/>'"

    return resultstring

@app.route('/buttonstopcharge')
def buttonstopcharge():
    stopCharging()
    return ("Laden Beenden")

@app.route('/buttonstartcharge')
def buttonstartcharge():
    startCharging()
    return ("Laden Starten")


if __name__ == '__main__':
    print("Hello")
    app.run(port=5000)
