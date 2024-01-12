import configparser, logging, time
import random
import threading

from flask import Flask,request,render_template

from pv import read_pv_voltage
from power import read_haus_stromverbrauch
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
    global glob_tesla
    global glob_vehicle
    tesla = Tesla(config.get('charge', 'tesla_account'), False, False)
    vehicles = tesla.vehicle_list()
    glob_vehicle = vehicles[0]


def startCharging():
        vehicle = getVehicle()
        vehicle_data = vehicle.get_vehicle_data()
        if vehicle_data['charge_state']['charging_state'] != 'Charging' and vehicle_data['charge_state']['charging_state'] != 'Complete':
            vehicle.command('START_CHARGE')
            log("Started Charging!")
        else:
            log("Did not start charging because vehicle was already charging!")
def stopCharging():

        vehicle = getVehicle()
        vehicle_data = vehicle.get_vehicle_data()
        if vehicle_data['charge_state']['charging_state'] == 'Charging':
            vehicle.command('STOP_CHARGE')
            log("stop charging")
        else:
            log("Did not stop charging because vehicle was not charging!")

def logStatus():
    data = getVehicle().get_vehicle_data()
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

def setChargingAmps(amps):
        vehicle = getVehicle()
        vehicle_data = vehicle.get_vehicle_data()
        if vehicle_data['charge_state']['charge_current_request'] != amps:
            amps = min([amps,16])
            log("Set Charging Amps: " + str(amps))
            vehicle.command('CHARGING_AMPS', charging_amps=amps)
            if amps < 5:
                vehicle.command('CHARGING_AMPS', charging_amps=amps)
        else:
            log("Did not set Charging Amps, weil keine Veraenderung: " + str(amps))
def tesla_pv_charge_control():

    vehicle = getVehicle()
    # Auto schläft, kann nicht geladen werden
    if vehicle['state'] == "asleep":
        log('Sleeping, can not set charge!')
        return
    # Auto wach
    # Status ausgeben
    logStatus()

    vehicle_data = vehicle.get_vehicle_data();
    # Auto nicht angesteckt, kann nicht geladen werden
    if vehicle_data['charge_state']['charging_state'] == 'Disconnected':
        log('Charger disconnected, can not set charge!')
        return

    # Ist das Auto zu Hause?
    if not isCarAtHome(vehicle_data):
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
    #if ampere_rounded > config.getint('charge', 'MINIMUM_AMPERE_LEVEL'):
    #    startCharging()
    setChargingAmps(ampere_rounded)
    print('')



def background_schleife():
    global config
    print("Hello World!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
    config = configparser.ConfigParser()
    config.read('constants_pv_charging.ini', encoding='utf-8')

    # Log initialisieren
    setuplog()

    log("start schleife")

    # Fahrzeug aus API lesen
    init_tesla()

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
            if i > 30:
                init_tesla()
                i = 0
                log("reinit tesla")

        except Exception as exception:
            log(exception)
            try:
                if i > 10:
                    init_tesla()
                    i = 0
                    log("reinit tesla")
            except Exception as exception:
                log(exception)

def getVehicle():
    return glob_vehicle

def setChargeMaxPercent(percent):
    getVehicle().command('CHANGE_CHARGE_LIMIT', percent=percent)

def setup_app(app):

    # Endlosschleife Aufruf pv_charge_control mit x Sekunden Pause
    download_thread = threading.Thread(target=background_schleife, name="background_schleife")
    download_thread.start()


setup_app(app)

def writeToIniFile(id, value):
    config.set('charge', id, value)
    with open('constants_pv_charging.ini', 'w', encoding="utf-8") as configfile:
        config.write(configfile)


@app.route("/", methods=["GET", "POST"])
@app.route("/pvcharge2", methods=["GET", "POST"])
def home():
    if request.method == "POST":
        print(request.form["name"])
        print(request.form["email"])


    max_charge = getVehicle().get_vehicle_data()['charge_state']['charge_limit_soc']
    minimum_ampere = config.getint('charge', 'fixed_minimum_ampere')

    data = [
        {
            'name': 'Audrin',
            'place': 'kaka',
            'mob': '7736'
        }
    ]
    return render_template("home.html" , max_charge=max_charge, minimum_ampere=minimum_ampere, data=data)

@app.route('/displaylog')
def displaylog():
    logfilename = config.get('charge', 'LOG_FILE_NAME')
    resultstring = ""
    for line in reversed(open(logfilename, 'rb').readlines()):
        resultstring += line.rstrip().decode("utf-8") +"'<br/>'"

    return resultstring

@app.route('/displaystatus')
def displaystatus():
    status = "Status"
    vehicle = getVehicle()
    vehicle_data = getVehicle().get_vehicle_data()
    if vehicle['state'] == "asleep":
        status = "Auto schläft"
        return status
    status = ("Ladezustand: " +vehicle_data['charge_state']['charging_state'] +"<br/>" +
              "Ladestand: " +str(vehicle_data['charge_state']['battery_level']) +" %<br/>"+
              "Energie hinzu: " + str(vehicle_data['charge_state']['charge_energy_added']) + " kwh<br/>"+
              "Leistung PV: " +str(read_pv_voltage()) + " watt<br/>"+
              "Haus Stromverbrauch: " +str(read_haus_stromverbrauch("http://192.168.178.240/cm?cmnd=status%2010")) +" watt"
              )
    return status

@app.route('/buttonstopcharge', methods=["GET", "POST"])
def buttonstopcharge():
    print(request)
    stopCharging()
    return ""

@app.route('/buttonstartcharge', methods=["GET", "POST"])
def buttonstartcharge():
    startCharging()
    return ""


@app.route('/setmaxcharge', methods=["GET", "POST"])
def setmaxcharge():
    print(request.form)
    setChargeMaxPercent(int(request.form['max_charge']))
    return ""

@app.route('/setampere', methods=["GET", "POST"])
def setampere():
    print(request.form)
    writeToIniFile("fixed_minimum_ampere", request.form['ampere'])
    return ""

if __name__ == '__main__':
    app.run(port=5000)
    #from waitress import serve
    #serve(app, host="0.0.0.0", port=5000)
