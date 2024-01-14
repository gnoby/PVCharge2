import configparser
import logging
import math
import threading
import time
from logging.handlers import RotatingFileHandler
import locale
from flask import Flask, request, render_template
from geopy.geocoders import Nominatim
from teslapy import Tesla
#from werkzeug.middleware.proxy_fix import ProxyFix

from power import read_haus_stromverbrauch
from pv import read_pv_voltage

# from flask_reverse_proxy_fix.middleware import ReverseProxyPrefixFix
def main():
    print("Hello World!")
    tesla = Tesla("norbert.ganslmeier@gmail.com", False, False)
    vehicles = tesla.vehicle_list()
    vehdata = vehicles[0].get_vehicle_data()


    locale.setlocale(locale.LC_ALL, 'de')
    print(locale.format_string('%10.0f', 1374 , grouping=True))

    while True:
            print(vehdata['charge_state']['charge_current_request'])
            time.sleep(10)

if __name__ == "__main__":
    main()

