#!/usr/bin/env python3
# vim: set encoding=utf-8 tabstop=4 softtabstop=4 shiftwidth=4 expandtab
#########################################################################
#  Copyright 2014 Dominik Lott          dominik.lott@tresch-automation.de
#########################################################################
#  This file is part of smartopenHMI https://github.com/dolo280/smartopenHMI
#
#  smartopenHMI is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  smartopenHMI is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with SmartHome.py. If not, see <http://www.gnu.org/licenses/>.
#########################################################################

import logging
import threading
import struct
import binascii
import re

import snap7
from snap7.snap7exceptions import Snap7Exception
from snap7.snap7types import S7AreaDB, S7WLByte, S7DataItem
from snap7.util import *

import lib.connection
from . import dpts

tcpport = 102
db_number = 42
rack = 0
slot = 2

logger = logging.getLogger('')


class S7(lib.connection.Client):

    def __init__(self, smarthome, time_ga=None, date_ga=None, send_time=1, busmonitor=False, host='127.0.0.1', port=6720):
        self.client = snap7.client.Client()
        self.client.connect(host, rack, slot, tcpport)
        lib.connection.Client.__init__(self, host, port, monitor=False)
        self._sh = smarthome
        self.gal = {}
        self.gar = {}
        self._init_ga = []
        self._cache_ga = []
        self.time_ga = time_ga
        self.date_ga = date_ga
        self._lock = threading.Lock()
        if send_time:
            self._sh.scheduler.add('S7 time', self._refresh_time, prio=5, cycle=int(send_time))

    def _send(self, data):
        if len(data) < 2 or len(data) > 0xffff:
            logger.debug('KNX: Illegal data size: {}'.format(repr(data)))
            return False
        # prepend data length
        send = bytearray(len(data).to_bytes(2, byteorder='big'))
        send.extend(data)
        self.send(send)

    # ------------------------
    #Mehrere Daten als "Datenpaket" vorbereiten
    # ------------------------
    def groupwrite(self, ga, payload, dpt, flag='write'):
        print("GA: " +  ga)
        print("payload: " +  str(payload))
        print("dpt: " +  dpt)
        print("flag: " +  flag)
        if ga.find("X") >= 0:
            test_value_1 = [int('00000000', 2)]
            test_bytes_1 = bytearray(test_value_1)
            if dpt == '1':
                #Toogle Bit
                #print("Toogle!")
                test_bytes_1 = self.client.db_read(41, 0, 1)
                value = snap7.util.get_bool(test_bytes_1, 0, 2)
                if value == 1:
                    #print ("Value = 1")
                    writevalue = 0
                else:
                    #print ("Value = 0")
                    writevalue = 1
                snap7.util.set_bool(test_bytes_1, 0, 2, writevalue)
                self.client.db_write(41, 0, test_bytes_1)
        else:
             print("Kein Bool")

        if dpt == '6':
        # Schreibe Gleitzahl auf DB41.DBW4
            test_value_2 = 123.45
            test_bytes_2 = bytearray(struct.pack('>f', test_value_2))
            self.client.db_write(41, 4, test_bytes_2)

        elif dpt == '5':
        # Schreibe Dezimal auf DB41.DBW8
            print("Dez")
            test_value_3 = payload
            test_bytes_3 = bytearray(struct.pack('>h', test_value_3))
            self.client.db_write(41, 8, test_bytes_3)


    # ------------------------
    #Mehrere Datenpunkte Lesen
    # ------------------------
    def groupread(self, ga):
         print(ga)
    #    pkt = bytearray([0, 39])
    #    pkt.extend(ga)
    #    pkt.extend([0, KNXREAD])
    #    self._send(pkt)

    def _refresh_time(self):
        for ga in self._init_ga:
            val = 0 #Item-Value
            src = ga
            dst = ga #Ziel-Item(Adresse)
            for item in self.gal[dst]['items']:
                ret_s7_num = re.findall(r'\d+', dst) #
                var_typ = len(ret_s7_num)
                if var_typ == 2:
                    #print("Real, Word oder Byte")
                    #ret_val = self.client.db_read(int(ret_s7_num[0]), int(ret_s7_num[1]), 2) #Lade DB41 / Ab 0 / 1.Byte    
                    
                    result = self.client.db_read(int(ret_s7_num[0]), int(ret_s7_num[1]), 2) #Lade DB41 / Ab 0 / 1.Byte    
                    bytes = ''.join([chr(x) for x in result]).encode('utf-8')
                    int_num = struct.unpack('>h', bytes)
                    int_num2 = re.findall(r'\d+', str(int_num))
                    val = int_num2[0]

                else:
                    #print("Bool")
                    ret_val = self.client.db_read(int(ret_s7_num[0]), int(ret_s7_num[1]), 1) #Lade DB41 / Ab 0 / 1.Byte
                    val = snap7.util.get_bool(ret_val, 0, int(ret_s7_num[2])) #Lade Value aus 0.Byte / Adresse 2

                item(val, 'S7', src, ga)
                print(str(val) + ":" + str(val) + ":" + str(src) + ":" + str(ga))

    def handle_connect(self):
        self.discard_buffers()
        enable_cache = bytearray([0, 112])
        self._send(enable_cache)
        init = bytearray([0, 38, 0, 0, 0])
        self._send(init)
        self.terminator = 2
        if self._init_ga != []:
            if self.connected:
                logger.debug('S7: init read')
                for ga in self._init_ga:
                    self.groupread(ga)
                self._init_ga = []

    def run(self):
        self.alive = True

    def stop(self):
        self.alive = False
        self.handle_close()

    def parse_item(self, item):
        if 's7_dtp' in item.conf:
            logger.warning("S7: Ignoring {0}: please change knx_dtp to knx_dpt.".format(item))
            return None
        if 's7_dpt' in item.conf:
            dpt = item.conf['s7_dpt']
            #print("S7-Datentyp: " + dpt)
            if dpt not in dpts.decode:
                logger.warning("S7: Ignoring {0} unknown dpt: {1}".format(item, dpt))
                return None
        else:
            return None

        if 's7_listen' in item.conf:
            knx_listen = item.conf['s7_listen']
            if isinstance(knx_listen, str):
                knx_listen = [knx_listen, ]
            for ga in knx_listen:
                logger.debug("S7: {0} listen on {1}".format(item, ga))
                if not ga in self.gal:
                    self.gal[ga] = {'dpt': dpt, 'items': [item], 'logics': []}
                else:
                    if not item in self.gal[ga]['items']:
                        self.gal[ga]['items'].append(item)

        if 's7_init' in item.conf:
            ga = item.conf['s7_init']
            logger.debug("S7: {0} listen on and init with {1}".format(item, ga))
            if not ga in self.gal:
                self.gal[ga] = {'dpt': dpt, 'items': [item], 'logics': []}
            else:
                if not item in self.gal[ga]['items']:
                    self.gal[ga]['items'].append(item)
            self._init_ga.append(ga)

        #Nicht Notwendig
        if 'S7_cache' in item.conf:
            ga = item.conf['S7_cache']
            logger.debug("S7: {0} listen on and init with cache {1}".format(item, ga))
            if not ga in self.gal:
                self.gal[ga] = {'dpt': dpt, 'items': [item], 'logics': []}
            else:
                if not item in self.gal[ga]['items']:
                    self.gal[ga]['items'].append(item)
            self._cache_ga.append(ga)

        #Nicht Notwendig
        if 'S7_reply' in item.conf:
            knx_reply = item.conf['S7_reply']
            if isinstance(knx_reply, str):
                knx_reply = [knx_reply, ]
            for ga in knx_reply:
                logger.debug("S7: {0} reply to {1}".format(item, ga))
                if ga not in self.gar:
                    self.gar[ga] = {'dpt': dpt, 'item': item, 'logic': None}
                else:
                    logger.warning("S7: {0} knx_reply ({1}) already defined for {2}".format(item, ga, self.gar[ga]['item']))

        if 's7_send' in item.conf:
            if isinstance(item.conf['s7_send'], str):
                item.conf['s7_send'] = [item.conf['s7_send'], ]
            return self.update_item

        #Nicht Notwendig
        elif 's7_status' in item.conf:
            if isinstance(item.conf['knx_status'], str):
                item.conf['knx_status'] = [item.conf['knx_status'], ]
            return self.update_item
        else:
            return None


    def update_item(self, item, caller=None, source=None, dest=None):
        if 's7_send' in item.conf:
            if caller != 'S7':
                for ga in item.conf['s7_send']:
                    self.groupwrite(ga, item(), item.conf['s7_dpt'])
        if 's7_status' in item.conf:
            for ga in item.conf['s7_status']:  # send status update
                if ga != dest:
                    self.groupwrite(ga, item(), item.conf['s7_dpt'])
