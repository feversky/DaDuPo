__copyright__ = """
    DaDuPo - An online calibration and measurement tool using XCP protocol

    (C) 2021 by Jun Yang <fever_sky@qq.com>

    All Rights Reserved

    This file is part of DaDuPo.

    DaDuPo is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

import binascii
import collections
import logging
import math
import struct
import threading
from collections import OrderedDict
from datetime import datetime
from threading import Thread

import typing
from pyxcp import types
from pyxcp.config import Configuration
from pyxcp.dllif import SeedNKeyResult
from pyxcp.master import Master
import time

from pyxcp.master.base import MasterBaseType
from pyxcp.transport.base import BaseTransport, createTransport
from pyxcp.types import GetDaqResolutionInfoResponse

from pprint import pprint
from typing import Dict, List, Tuple, Union

from data import Asap2DatabaseUtil
from data.Asap2Database import Asap2Database
from data.Asap2DatabaseUtil import size_of_asap2_object
from data.DataPool import DataPool, SignalConfig
from device.DeviceBase import DeviceBase
from device.transport import *


class MyMaster(Master):


    @staticmethod
    def seed2key(seed):
        return SeedNKeyResult.ACK, seed[:4] + bytes([0] * 5)

    def cond_unlock(self, resources=None):
        """Conditionally unlock resources, i.e. only unlock locked resources.

        Precondition: Must assign :attr:`seedNKeyDLL`, e.g. ``master.seedNKeyDLL = "SeedNKeyXcp.dll"``

        Parameters
        ----------
        resources: str
            Comma or space separated list of resources, e.g. "DAQ, CALPAG".
            The names are not case-sensitive.
            Valid identifiers are: "calpag", "daq", "dbg", "pgm", "stim".

            If omitted, try to unlock every available resource.

        Raises
        ------
        ValueError
            Invalid resource name.

        `dllif.SeedNKeyError`
            In case of DLL related issues.
        """
        import re
        from pyxcp.dllif import SeedNKeyResult, SeedNKeyError

        MAX_PAYLOAD = self.slaveProperties["maxCto"] - 2

        if resources is None:
            result = []
            if self.slaveProperties['supportsCalpag']:
                result.append("calpag")
            if self.slaveProperties['supportsDaq']:
                result.append("daq")
            if self.slaveProperties['supportsStim']:
                result.append("stim")
            if self.slaveProperties['supportsPgm']:
                result.append("pgm")
            resources = ",".join(result)
        protection_status = self.getCurrentProtectionStatus()
        resource_names = [r.lower() for r in re.split(r"[ ,]", resources) if r]
        for name in resource_names:
            if name not in types.RESOURCE_VALUES:
                raise ValueError("Invalid resource name '{}'.".format(name))
            if not protection_status[name]:
                continue
            resource_value = types.RESOURCE_VALUES[name]
            result = self.getSeed(types.XcpGetSeedMode.FIRST_PART, resource_value)
            seed = list(result.seed)
            length = result.length
            if length == 0:
                continue
            if length > MAX_PAYLOAD:
                remaining = length - len(seed)
                while remaining > 0:
                    result = self.getSeed(types.XcpGetSeedMode.REMAINING, resource_value)
                    seed.extend(list(result.seed))
                    remaining = result.length
            result, key = self.seed2key(bytes(seed))
            # print(binascii.hexlify(key))
            if result == SeedNKeyResult.ACK:
                key = list(key)
                total_length = len(key)
                offset = 0
                while offset < total_length:
                    data = key[offset: offset + MAX_PAYLOAD]
                    key_length = len(data)
                    offset += key_length
                    res = self.unlock(key_length, bytes(data))
            else:
                raise SeedNKeyError("SeedAndKey DLL returned: {}".format(SeedNKeyResult(result).name))


class BinPacker(object):
    def __init__(self):
        pass

    @staticmethod
    def pack(items: Dict[str, int], bin_size: int):
        # sorted by value in descending order
        bins: List[typing.OrderedDict[str, int]] = []
        bins_storage: List[int] = []
        sorted_items = dict(sorted(items.items(), key=lambda pair: pair[1], reverse=True))
        for var_name, var_size in sorted_items.items():
            c_storage = []
            c_index = []
            filtered = [(i, b) for i, b in enumerate(bins_storage) if b + var_size <= bin_size]
            if filtered:
                c_index, c_storage = zip(*filtered)
            if c_storage:
                selected_index = c_index[c_storage.index(max(c_storage))]
                bins_storage[selected_index] += var_size
                bins[selected_index][var_name] = var_size
            else:
                # no bin found, open a new bin
                bins_storage.append(var_size)
                new_bin = OrderedDict()
                new_bin[var_name] = var_size
                bins.append(new_bin)
        return bins


EventChannel = collections.namedtuple('EventChannel', 'name info channel_number')


class XcpClient(DeviceBase):
    START_MEASUREMENT = 'start_measurement'
    STOP_MEASUREMENT = 'stop_measurement'
    RECV = 'recv'
    ERROR = 'error'

    def __init__(self, transport, config, db):
        import os
        os.environ["PYXCP_HANDLE_ERRORS"] = 'false'
        self.transport = transport
        self.config = config
        self.db: Asap2Database = db
        self.data_pool = DataPool()
        self.started = False
        self.connected = False
        self.event_channels: Dict[str, EventChannel] = {}
        self.daq_list = OrderedDict()
        self.daq_resolution_info: Union[None, GetDaqResolutionInfoResponse] = None
        self.polling_thread = None
        self.daq_thread = None
        self.run_measurement = False
        self.polling_signals = {}  # key: interval, value: [sid]
        self.daq_signals = {}      # key: channel name, value: [sid]
        self.asap2_objs = {}
        self.daq_processor_info = None
        self.daq_list_pid = {}
        self.event_listeners = {self.RECV: [], self.ERROR: [], self.START_MEASUREMENT: [], self.STOP_MEASUREMENT: []}
        self.lock = threading.Lock()

    def connect(self):
        ecu = MyMaster(self.transport, self.config)
        self.ecu = ecu
        ecu.connect()
        self.connected = True
        if ecu.slaveProperties.optionalCommMode:
            ecu.getCommModeInfo()
        if ecu.slaveProperties.addressGranularity != types.AddressGranularity.BYTE:
            raise Exception('only AddressGranularity.BYTE is supported!')
        if not ecu.slaveProperties.supportsDaq:
            raise Exception("daq is not supported by slave")
        ecu.getStatus()
        protection_status = ecu.getCurrentProtectionStatus()
        if protection_status['daq']:
            ecu.cond_unlock('daq')
        if protection_status['calpag']:
            ecu.cond_unlock('calpag')
        # gid = ecu.getId(0x1)
        # result = ecu.fetch(gid.length)
        daq_processor_info = ecu.getDaqProcessorInfo()
        self.daq_processor_info = daq_processor_info
        # pprint(daq_processor_info)
        if daq_processor_info.daqProperties.daqConfigType == 'STATIC':
            raise Exception("static daq is not implemented")
        # todo: overload indication
        self.daq_resolution_info = ecu.getDaqResolutionInfo()

        for ecn in range(daq_processor_info.maxEventChannel):
            eci = ecu.getDaqEventInfo(ecn)
            data = ecu.upload(eci.eventChannelNameLength)
            name = data.rstrip(b'\x00').decode("latin1")
            self.event_channels[name] = EventChannel(name, eci, ecn)

    def get_daq_event_channels(self):
        res = {}
        for channel, e in self.event_channels.items():
            unit = e.info.eventChannelTimeUnit.split('_')[-1]
            cycle = e.info.eventChannelTimeCycle
            unit = unit.strip('1').strip('0')
            res[channel] = f'{cycle}{unit}'
        return res

    def setup_measurement(self):
        self.asap2_objs = {}
        self.polling_signals = {}
        self.daq_signals = {}
        self.daq_list = OrderedDict()
        self.daq_list_pid = {}
        signal_addrs = {}
        signal_sizes = {}
        odt_size = self.daq_resolution_info.maxOdtEntrySizeDaq
        granularity_size = self.daq_resolution_info.granularityOdtEntrySizeDaq
        for sid, sc in self.data_pool.signal_config.items():
            db_name = sid.split('/')[0]
            if not sc.enabled or db_name != self.db.name:
                continue
            addr, size, obj = self.get_addr_size_by_name(sid.split('/')[-1])
            if size > odt_size:
                raise Exception(f'size of {sid} is too large')
            if addr % granularity_size != 0 or size % granularity_size != 0:
                raise Exception(f'{sid} has wrong granularity size')
            self.asap2_objs[sid] = obj
            signal_addrs[sid] = addr
            signal_sizes[sid] = size
            if sc.channel == 'polling':
                if sc.rate not in self.polling_signals.keys():
                    self.polling_signals[sc.rate] = []
                self.polling_signals[sc.rate].append((sid, addr, size, obj))
            elif not self.event_channels[sc.channel].info.daqEventProperties.daq:
                raise Exception(f'{sc.channel} does not support daq')
            else:
                if sc.channel not in self.daq_signals.keys():
                    self.daq_signals[sc.channel] = []
                self.daq_signals[sc.channel].append(sid)

        for channel, lst in self.daq_signals.items():
            signals_to_pack = {}
            for sid in lst:
                signals_to_pack[sid] = signal_sizes[sid]
            self.daq_list[channel] = BinPacker.pack(signals_to_pack, odt_size)

        if self.daq_list:
            ecu = self.ecu
            if self.daq_processor_info.daqProperties.daqConfigType == 'STATIC':
                ecu.clearDaqList()
            else:
                ecu.freeDaq()
                ecu.allocDaq(len(self.daq_list))
                for daq_list_no, odts in enumerate(self.daq_list.values()):
                    ecu.allocOdt(daq_list_no, len(odts))
                for daq_list_no, odts in enumerate(self.daq_list.values()):
                    for odt_number, odt_entries in enumerate(odts):
                        ecu.allocOdtEntry(daq_list_no, odt_number, len(odt_entries))
                for daq_list_no, odt_list in enumerate(self.daq_list.values()):
                    for odt_no, odt_entries in enumerate(odt_list):
                        for entry_no, (entry_name, entry_size) in enumerate(odt_entries.items()):
                            ecu.setDaqPtr(daq_list_no, odt_no, entry_no)
                            ecu.writeDaq(0xFF, entry_size, 0x00, signal_addrs[entry_name])
                for daq_list_no, (channel_name, odts) in enumerate(self.daq_list.items()):
                    ecu.setDaqListMode(0, daq_list_no, self.event_channels[channel_name].channel_number, 1, 0)

    def start_measurement(self):
        self.run_measurement = True
        ecu = self.ecu
        if self.daq_list:
            if self.daq_processor_info.daqProperties.daqConfigType == 'STATIC':
                ecu.clearDaqList()
            else:
                for daq_list_no, channel_name in enumerate(self.daq_list.keys()):
                    response = ecu.startStopDaqList(2, daq_list_no)
                    self.daq_list_pid[channel_name] = response.firstPid
                    ecu.startStopSynch(1)
            self.daq_thread = Thread(target=self._daq_thread)
            self.daq_thread.start()
        if self.polling_signals:
            self.polling_thread = Thread(target=self._polling_thread)
            self.polling_thread.start()

    def get_addr_size_by_name(self, s_name):
        var = next((c for c in self.db.asap2_parameters if c.name == s_name), None)
        if not var:
            var = next((s for s in self.db.asap2_signals if s.name == s_name), None)
            if not var:
                raise Exception(f'{s_name} not found in a2l')
            else:
                addr, size = int(var.address, 0), size_of_asap2_object(var)
        else:
            addr, size = int(var.address, 0), size_of_asap2_object(var)
        return addr, size, var

    def stop_measurement(self):
        self.run_measurement = False
        self.ecu.startStopSynch(0)

    def _polling_thread(self):
        while self.run_measurement:
            for interval, lst in self.polling_signals.items():
                for sid, addr, size, obj in lst:
                    self.lock.acquire()
                    try:
                        raw_bytes = self.ecu.shortUpload(size, addr)
                        raw_val, phy_val = Asap2DatabaseUtil.bytes_to_phy_value(raw_bytes, obj)
                        for f in self.event_listeners[self.RECV]:
                            f(sid, raw_val, phy_val, datetime.now())
                    except:
                        pass
                    self.lock.release()
                    # time.sleep(0.001)
                time.sleep(interval / 1000)

    def _daq_thread(self):
        data_start_index = {
            'IDF_ABS_ODT_NUMBER': 1,
            'IDF_REL_ODT_NUMBER_ABS_DAQ_LIST_NUMBER_BYTE': 2,
            'IDF_REL_ODT_NUMBER_ABS_DAQ_LIST_NUMBER_WORD': 3,
            'IDF_REL_ODT_NUMBER_ABS_DAQ_LIST_NUMBER_WORD_ALIGNED': 4
        }[self.daq_processor_info.daqKeyByte.Identification_Field]
        while self.run_measurement:
            for _ in range(len(self.ecu.transport.daqQueue)):
                response, counter, length, timestamp = self.ecu.transport.daqQueue.popleft()
                timestamp = datetime.now() if timestamp == 0 else datetime.fromtimestamp(timestamp)
                odt = {}
                if data_start_index == 1:
                    pid = response[0]
                    for channel, odts in self.daq_list.items():
                        if self.daq_list_pid[channel] <= pid < self.daq_list_pid[channel] + len(odts):
                            odt = odts[pid - self.daq_list_pid[channel]]
                            break
                else:
                    odt_index = response[0]
                    if data_start_index == 2:
                        daq_list_number = response[1]
                    else:
                        daq_list_number = self.ecu.WORD_unpack(response[data_start_index - 2:data_start_index - 1])
                    for no, odts in enumerate(self.daq_list.values()):
                        if no == daq_list_number:
                            odt = odts[odt_index]
                            break
                size_offset = 0
                for sid, size in odt.items():
                    raw_bytes = response[data_start_index + size_offset:][:size]
                    size_offset += size
                    obj = self.data_pool.get_obj_by_sid(sid)
                    raw_val, phy_val = Asap2DatabaseUtil.bytes_to_phy_value(raw_bytes, obj)
                    for f in self.event_listeners[self.RECV]:
                        f(sid, raw_val, phy_val, timestamp)

            time.sleep(0.001)

    def set_cal_page(self, page):
        self.ecu.setCalPage(0x83, 0, page)

    def get_cal_page(self):
        return self.ecu.getCalPage(0x83, 0)

    def granularity_size(self):
        return {
            types.AddressGranularity.BYTE: 1,
            types.AddressGranularity.WORD: 2,
            types.AddressGranularity.DWORD: 4,
        }[self.ecu.slaveProperties.addressGranularity]

    def upload(self, sid):
        db_name, name = sid.split('/')
        addr, size, var = self.get_addr_size_by_name(name)
        granularity_size = self.granularity_size()
        max_cto = self.ecu.slaveProperties.maxCto
        min_size = int(min(size, int(int(max_cto - 1) / granularity_size)) * granularity_size)
        if size > min_size:
            self.ecu.setMta(addr)
            raw_bytes = bytes()
            remaining_size = size
            self.lock.acquire()
            while remaining_size > 0:
                min_size = min(remaining_size, math.floor((max_cto - 1) / granularity_size) * granularity_size)
                upload_size = math.ceil(min_size / granularity_size) * granularity_size
                raw_bytes += self.ecu.upload(upload_size)
                remaining_size -= upload_size
            self.lock.release()
            return Asap2DatabaseUtil.bytes_to_phy_value(raw_bytes, var)
        else:
            self.lock.acquire()
            raw_bytes = self.ecu.shortUpload(min_size, addr)
            self.lock.release()
            return Asap2DatabaseUtil.bytes_to_phy_value(raw_bytes, var)

    def download(self, sid, value):
        db_name, name = sid.split('/')
        addr, size, var = self.get_addr_size_by_name(name)
        granularity_size = self.granularity_size()
        if granularity_size == 1:
            max_cto = self.ecu.slaveProperties.maxCto
            max_elements = math.floor((max_cto - 2) / granularity_size)
            remaining_elements = size
            current_addr = addr
            data = Asap2DatabaseUtil.phy_value_to_bytes(value, var)
            self.lock.acquire()
            while remaining_elements > 0:
                self.ecu.setMta(current_addr)
                self.ecu.download(data[:max_elements])
                remaining_elements -= max_elements
                current_addr += max_elements
            self.lock.release()

    def download_bytes(self, addr, byts):
        granularity_size = self.granularity_size()
        if granularity_size == 1:
            max_cto = self.ecu.slaveProperties.maxCto
            max_elements = math.floor((max_cto - 2) / granularity_size)
            if max_elements < len(byts):
                raise Exception("length of raw bytes shall be less than maxCTO-2")
            self.lock.acquire()
            self.ecu.setMta(addr)
            self.ecu.download(byts)
            self.lock.release()

    def disconnect(self):
        self.ecu.disconnect()
        self.ecu.transport.close()
        self.connected = False

    def close(self):
        if hasattr(self, 'ecu'):
            self.ecu.transport.closeConnection()

    def add_event_listener(self, event, listener):
        self.event_listeners[event].append(listener)

    def remove_event_listener(self, event, listener):
        if listener in self.event_listeners[event]:
            self.event_listeners[event].remove(listener)
