import requests
import json


def main():
    read_haus_stromverbrauch("http://192.168.178.240/cm?cmnd=status%2010")


def read_haus_stromverbrauch(url):
    resp2 = requests.get(url)
    #print(resp2.content)
    data = json.loads(resp2.content)
    #print(data['StatusSNS']['MT631']['Power_cur'])
    return data['StatusSNS']['MT631']['Power_cur']


if __name__ == "__main__":
    main()