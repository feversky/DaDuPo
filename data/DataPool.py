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

import collections
import json
from datetime import datetime
from threading import Lock
from typing import Union, Dict
import numpy as np
import marshmallow_dataclass
from pathlib import Path

from data.Asap2Database import Asap2Parameter, Asap2Signal, Asap2Database, CompuMethod, CompuMethodType, DBType
from data.Asap2DatabaseUtil import process_asap2_database, find_asap2_object


SignalConfig = collections.namedtuple('SignalConfig', ['sid', 'channel', 'rate', 'enabled'])


class DataPool(object):
    _instance = None
    _signal_buffer = {}
    _signals = []
    _signal_config: Dict[str, SignalConfig] = {}
    _databases = {}
    _start_time = None
    _lock = Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DataPool, cls).__new__(cls)
        return cls._instance

    def load_db(self, db_path) -> Union[Asap2Database]:
        content = Path(db_path).read_text()
        j = json.loads(content)
        if j['db_type'] == DBType.ASAP2.value:
            asap2_schema = marshmallow_dataclass.class_schema(Asap2Database)()
            db = asap2_schema.load(j)
            process_asap2_database(db)
            self._databases[db.name] = db
            return db

    @property
    def databases(self):
        return self._databases.values()

    @property
    def signal_config(self):
        return self._signal_config

    @signal_config.setter
    def signal_config(self, value):
        self._signal_config = value
        self._signals = [k for k, v in self._signal_config.items() if v.enabled]

    def get_obj_by_sid(self, sid) -> Union[Asap2Parameter, Asap2Signal]:
        db_name = sid.split('/')[0]
        if db_name in self._databases.keys():
            sig_name = sid.split('/')[-1]
            db = self._databases[db_name]
            if db.db_type == DBType.ASAP2:
                return find_asap2_object(db, sig_name)

    def get_db_by_sid(self, sid: str) -> Union[Asap2Database]:
        db_name = sid.split('/')[0]
        if db_name in self._databases.keys():
            return self._databases[db_name]

    def get_value_table_by_sid(self, sid):
        db = self.get_db_by_sid(sid)
        obj = self.get_obj_by_sid(sid)
        if not obj or not db:
            return
        if db.db_type == DBType.ASAP2:
            cm: CompuMethod = obj.compu_method_ref
            if cm.compu_method_type == CompuMethodType.DICT:
                return cm.dictionary

    def on_new_xcp_signal(self, sid, raw_val, phy_val, timestamp):
        self._lock.acquire()
        new_x = (timestamp - self._start_time).total_seconds()
        self._signal_buffer[sid] = np.append(self._signal_buffer[sid], [[new_x, phy_val]], axis=0)
        if (new_x - float(self._signal_buffer[sid][0][0])) > 120:
            self._signal_buffer[sid] = np.delete(self._signal_buffer[sid], 0, axis=0)
        self._lock.release()

    def measure_signal(self, sid: str):
        if sid in self._signals:
            return
        self._signals.append(sid)
        obj = self.get_obj_by_sid(sid)
        if sid not in self._signal_config.keys() and type(obj) in [Asap2Parameter, Asap2Signal]:
            self._signal_config[sid] = SignalConfig(sid, 'polling', 100, True)

    def remove_signal(self, sid: str):
        self._signals.remove(sid)
        self._signal_buffer.pop(sid)

    @property
    def start_time(self):
        return self._start_time

    @property
    def signal_buffer(self):
        return self._signal_buffer

    def on_start_measurement(self):
        self._signal_buffer = {}
        for sid in self._signals:
            self._signal_buffer[sid] = np.stack([[], []], axis=1)
        self._start_time = datetime.now()

    def on_stop_measurement(self):
        self._start_time = None
