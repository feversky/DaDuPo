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

from datetime import time
from time import perf_counter

import serial
from pyxcp.transport.base import BaseTransport

# add framing protocol based on https://github.com/christoph2/pyxcp/blob/master/pyxcp/transport/sxi.py
from pyxcp.utils import flatten, hexDump


class XcpOnSxi(BaseTransport):
    PARAMETER_MAP = {
        #      Type    Req'd   Default
        "PORT": (str, False, "COM1"),
        "BITRATE": (int, False, 115200),
        "BYTESIZE": (int, False, 8),
        "PARITY": (str, False, "N"),
        "STOPBITS": (int, False, 1),
    }

    SLIP_SYNC = 0x9A
    SLIP_ESC = 0x9B
    ESC_SYNC = 1
    ESC_ESC = 0

    MAX_DATAGRAM_SIZE = 512
    TIMEOUT = 0.75

    def __init__(self, config=None):
        super(XcpOnSxi, self).__init__(config)
        self.loadConfig(config)
        self.portName = self.config.get("port")
        self.baudrate = self.config.get("bitrate")

    def __del__(self):
        self.closeConnection()

    def _prepare_request(self, cmd, *data):
        """
        Prepares a request to be sent
        """
        if self._debug:
            self.logger.debug(cmd.name)
        self.parent._setService(cmd)
        cmdlen = cmd.bit_length() // 8  # calculate bytes needed for cmd

        frame = bytes(flatten(cmd.to_bytes(cmdlen, 'big'), data))
        if self._debug:
            self.logger.debug("-> {}".format(hexDump(frame)))
        return frame

    def connect(self):
        self.logger.debug("Trying to open serial commPort {}.".format(self.portName))
        try:
            self.commPort = serial.Serial(self.portName, self.baudrate, timeout=XcpOnSxi.TIMEOUT)
        except serial.SerialException as e:
            raise e
        self.logger.info("Serial commPort openend as '{}' @ {} Bits/Sec.".format(self.commPort.portstr, self.baudrate))

        self.startListener()

    def output(self, enable):
        if enable:
            self.commPort.rts = False
            self.commPort.dtr = False
        else:
            self.commPort.rts = True
            self.commPort.dtr = True

    def flush(self):
        self.commPort.flush()

    def listen(self):
        high_resolution_time = self.perf_counter_origin > 0
        timestamp_origin = self.timestamp_origin
        perf_counter_origin = self.perf_counter_origin

        while True:
            if self.closeEvent.isSet():
                return
            if not self.commPort.inWaiting():
                continue
            if high_resolution_time:
                recv_timestamp = time()
            else:
                recv_timestamp = timestamp_origin + perf_counter() - perf_counter_origin
            sync = self.commPort.read(1)[0]
            if sync != self.SLIP_SYNC:
                continue
            length = self.commPort.read(1)[0]
            data = self.commPort.read(length)
            checksum = self.commPort.read(1)[0]
            self.timing.stop()

            if len(data) != length:
                self.logger.error("Size mismatch.")
                continue
            if (sum(data) + length) % 256 != checksum:
                self.logger.error("Checksum mismatch")
                continue
            if self.SLIP_SYNC in data or self.SLIP_ESC == data[-1]:
                self.logger.error("Wrong data format")
                continue

            response = []
            i = 0
            if length == 1:
                response.append(data[0])
            while i < length:
                if data[i] == self.SLIP_ESC:
                    if i == length - 1:
                        self.logger.error("Wrong data format")
                        continue
                    if data[i + 1] == self.ESC_SYNC:
                        response.append(self.SLIP_SYNC)
                    elif data[i + 1] == self.ESC_ESC:
                        response.append(self.SLIP_ESC)
                    else:
                        self.logger.error("Wrong data format")
                        continue
                    i += 1
                else:
                    response.append(data[i])
                i += 1
            # print(bytes(response))
            self.processResponse(bytes(response), length, self.counterReceived + 1, recv_timestamp)

    def send(self, frame):
        packed = []
        for d in frame:
            if d == self.SLIP_SYNC:
                packed.extend([self.SLIP_ESC, self.ESC_SYNC])
            elif d == self.SLIP_ESC:
                packed.extend([self.SLIP_ESC, self.ESC_ESC])
            else:
                packed.append(d)
        length = len(packed)
        checksum = (sum(packed) + length) % 256
        packed = bytes([self.SLIP_SYNC, length] + packed + [checksum])
        if self.perf_counter_origin > 0:
            self.pre_send_timestamp = time()
            self.commPort.write(packed)
            self.post_send_timestamp = time()
        else:
            pre_send_timestamp = perf_counter()
            self.commPort.write(packed)
            post_send_timestamp = perf_counter()
            self.pre_send_timestamp = self.timestamp_origin + pre_send_timestamp - self.perf_counter_origin
            self.post_send_timestamp = self.timestamp_origin + post_send_timestamp - self.perf_counter_origin

    def closeConnection(self):
        if hasattr(self, "commPort") and self.commPort.isOpen():
            self.commPort.close()
