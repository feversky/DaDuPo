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

from enum import Enum
from typing import Dict

from device.DeviceBase import DeviceBase
from device.XcpClient import XcpClient
from data.DataPool import DataPool


class TransportType(Enum):
    XcpOnSxi = "XcpOnSxi"


class DeviceManager(object):
    _instance = None
    _data_pool = DataPool()
    _devices: Dict[str, DeviceBase] = {}
    _connected = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DeviceManager, cls).__new__(cls)
        return cls._instance

    def load_devices(self, config):
        for dev_cfg in config:
            for db_path in dev_cfg['database']:
                db = self._data_pool.load_db(db_path)
                dev = XcpClient(dev_cfg['transport'], dev_cfg, db)
                self._devices[dev_cfg['name']] = dev
                dev.add_event_listener(XcpClient.RECV, self._data_pool.on_new_xcp_signal)

    def get_device_by_db_name(self, db_name):
        for dev in self._devices.values():
            if dev.db.name == db_name:
                return dev

    def download(self, sid, value):
        db_name = sid.split('/')[0]
        for dev in self._devices.values():
            if dev.db.name == db_name:
                dev.download(sid, value)

    def upload(self, sid):
        db_name = sid.split('/')[0]
        for dev in self._devices.values():
            if dev.db.name == db_name:
                return dev.upload(sid)

    def connect(self):
        try:
            for dev in self._devices.values():
                dev.connect()
        except Exception as e:
            print(str(e))
            for dev in self._devices.values():
                dev.disconnect()
                dev.close()
            return
        self._connected = True

    def disconnect(self):
        for dev in self._devices.values():
            dev.disconnect()
        self._connected = False

    def start_measurement(self):
        for dev in self._devices.values():
            dev.setup_measurement()
            dev.start_measurement()

    def stop_measurement(self):
        for dev in self._devices.values():
            dev.stop_measurement()

    def close(self):
        for dev in self._devices.values():
            dev.close()

    @property
    def connected(self):
        return self._connected
