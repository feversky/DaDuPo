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

import struct
from typing import Union, Tuple, List, Dict
import json

from data.Asap2Database import Asap2Parameter, Asap2Signal, Datatype, Asap2Database, ByteOrder, CompuMethod, \
    CompuMethodType, Alignment, ParameterType


def _gen_asap2_objects(o: Dict, parent_name: str):
    name = '.'.join([parent_name, o['name']])
    if 'attributes' in o.keys():
        for a in o['attributes']:
            yield from _gen_asap2_objects(a, name)
    else:
        ret = o.copy()
        ret['name'] = name
        yield ret


def process_asap2_database(db: Asap2Database):
    if db.db_desc:
        from pathlib import Path
        contents = Path(db.db_desc).read_text()
        desc = json.loads(contents)
        objs = []
        for s in db.asap2_parameters + db.asap2_signals:
            if s.db_desc:
                objs.append(s)
        for o in objs:
            if o in db.asap2_parameters:
                db.asap2_parameters.remove(o)
            elif o in db.asap2_signals:
                db.asap2_signals.remove(o)
            for n in _gen_asap2_objects(desc[o.db_desc], o.name):
                addr = hex(int(o.address, 0) + n['offset'])
                name_splits = n['name'].split('.')
                n_name = '.'.join(name_splits[:1] + name_splits[2:])
                if n['type'] == 'parameter':
                    p = Asap2Parameter(addr, None, n['compu_method'], 1, Datatype[n['datatype']],
                                       '', '', n_name, ParameterType.VALUE, None, None, n['unit'], '')
                    db.asap2_parameters.append(p)
                if n['type'] == 'signal':
                    s = Asap2Signal(addr, None, n['compu_method'], 1, Datatype[n['datatype']],
                                    '', '', n_name, n['unit'], '')
                    db.asap2_signals.append(s)
    if not db.alignment:
        db.alignment = Alignment(
            alignment_byte=1,
            alignment_float32_ieee=4,
            alignment_float64_ieee=8,
            alignment_int64=8,
            alignment_long=4,
            alignment_word=2
        )
    else:
        if not db.alignment.alignment_byte:
            db.alignment.alignment_byte = 1
        if not db.alignment.alignment_word:
            db.alignment.alignment_word = 2
        if not db.alignment.alignment_long:
            db.alignment.alignment_long = 4
        if not db.alignment.alignment_int64:
            db.alignment.alignment_int64 = 8
        if not db.alignment.alignment_float32_ieee:
            db.alignment.alignment_float32_ieee = 4
        if not db.alignment.alignment_float64_ieee:
            db.alignment.alignment_float64_ieee = 8
    for s in db.asap2_parameters + db.asap2_signals:
        s.parent = db
        if s.compu_method:
            cm = next((c for c in db.compu_methods if c.name == s.compu_method), None)
            s.compu_method_ref = cm
            s.identifier = '/'.join([db.name, s.name])
            if not s.unit and cm.unit:
                s.unit = cm.unit
        if not s.count:
            s.count = 1
        if s.alignment:
            if not s.alignment.alignment_byte:
                s.alignment.alignment_byte = db.alignment.alignment_byte
            if not db.alignment.alignment_word:
                s.alignment.alignment_word = db.alignment.alignment_word
            if not db.alignment.alignment_long:
                s.alignment.alignment_long = db.alignment.alignment_long
            if not db.alignment.alignment_int64:
                s.alignment.alignment_int64 = db.alignment.alignment_int64
            if not db.alignment.alignment_float32_ieee:
                s.alignment.alignment_float32_ieee = db.alignment.alignment_float32_ieee
            if not db.alignment.alignment_float64_ieee:
                s.alignment.alignment_float64_ieee = db.alignment.alignment_float64_ieee
        else:
            s.alignment = db.alignment
    for s in db.asap2_parameters:
        if s.ref_x:
            x = next((p for p in db.asap2_parameters if p.name == s.ref_x), None)
            s.ref_x_ref = x
        if s.ref_y:
            y = next((p for p in db.asap2_parameters if p.name == s.ref_y), None)
            s.ref_x_ref = y


def find_asap2_object(db: Asap2Database, obj_name: str):
    return next((s for s in db.asap2_parameters + db.asap2_signals if s.name == obj_name), None)


def size_of_datatype(dt: Datatype) -> int:
    return {
        Datatype.A_INT64: 8,
        Datatype.A_UINT64: 8,
        Datatype.FLOAT32_IEEE: 4,
        Datatype.FLOAT64_IEEE: 8,
        Datatype.SBYTE: 1,
        Datatype.SLONG: 4,
        Datatype.SWORD: 2,
        Datatype.UBYTE: 1,
        Datatype.ULONG: 4,
        Datatype.UWORD: 2
    }[dt]


def calc_deposit_from_datatype(dt: Datatype, alignment: Alignment) -> int:
    align = 0
    if dt in [Datatype.UBYTE, Datatype.SBYTE]:
        align = alignment.alignment_byte
    elif dt in [Datatype.UWORD, Datatype.SWORD]:
        align = alignment.alignment_word
    elif dt in [Datatype.ULONG, Datatype.SLONG]:
        align = alignment.alignment_long
    elif dt in [Datatype.A_UINT64, Datatype.A_INT64]:
        align = alignment.alignment_int64
    elif dt == Datatype.FLOAT32_IEEE:
        align = alignment.alignment_float32_ieee
    elif dt == Datatype.FLOAT64_IEEE:
        align = alignment.alignment_float64_ieee
    return max(size_of_datatype(dt), align)


def size_of_asap2_object(obj: Union[Asap2Parameter, Asap2Signal]) -> int:
    if type(obj) is Asap2Parameter:
        return obj.count * calc_deposit_from_datatype(obj.datatype, obj.alignment)
    else:
        return calc_deposit_from_datatype(obj.datatype, obj.alignment)


def calc_phy_value_4_parameter(byts: bytes, obj: Asap2Parameter) -> \
        Tuple[Union[int, List, Tuple], Union[int, float, str, List, Tuple]]:
    if obj.parameter_type == ParameterType.VALUE:
        return bytes_to_single_phy_value(byts, obj.datatype, obj.alignment, obj.parent.byte_order, obj.compu_method_ref)
    elif obj.parameter_type == ParameterType.ASCII:
        return list(byts), byts.decode('ascii')
    elif obj.parameter_type == ParameterType.ARRAY:
        return bytes_to_array_phy_value(byts,
                                        obj.count,
                                        obj.datatype,
                                        obj.alignment,
                                        obj.parent.byte_order,
                                        obj.compu_method_ref)
    elif obj.parameter_type == ParameterType.CURVE:
        pass
    elif obj.parameter_type == ParameterType.MAP:
        pass


def bytes_to_single_raw_value(byts: bytes, datatype: Datatype, alignment: Alignment, byte_order: ByteOrder) -> \
        Union[int, float]:
    bo = "big" if byte_order == ByteOrder.MSB_FIRST else "little"
    fmt_endian = '>' if bo == "big" else '<'
    if datatype in [Datatype.SBYTE, Datatype.SWORD, Datatype.SLONG, Datatype.A_INT64]:
        return int.from_bytes(byts, byteorder=bo, signed=True)
    elif datatype in [Datatype.UBYTE, Datatype.UWORD, Datatype.ULONG, Datatype.A_UINT64]:
        return int.from_bytes(byts, byteorder=bo, signed=False)
    elif datatype == Datatype.FLOAT32_IEEE:
        return struct.unpack(f'{fmt_endian}f', byts)[0]
    elif datatype == Datatype.FLOAT64_IEEE:
        return struct.unpack(f'{fmt_endian}d', byts)[0]


def raw_value_to_phy_value(raw_value: Union[int, float], compu_method: CompuMethod):
    if not compu_method or compu_method.compu_method_type == CompuMethodType.IDENTICAL:
        return raw_value
    out = raw_value
    if compu_method.compu_method_type == CompuMethodType.LINEAR:
        val = raw_value * compu_method.coeffs.a + compu_method.coeffs.b
        out = type(raw_value)(val)
    elif compu_method.compu_method_type == CompuMethodType.DICT:
        out = compu_method.dictionary[str(int(raw_value))]
        return out
    else:
        raise Exception("unimplemented compu_method")
    return type(raw_value)(out)


def bytes_to_single_phy_value(byts: bytes, datatype: Datatype, alignment: Alignment, byte_order: ByteOrder,
                              compu_method: CompuMethod) \
        -> Tuple[int, Union[int, float, str]]:
    raw_val = bytes_to_single_raw_value(byts, datatype, alignment, byte_order)
    return raw_val, raw_value_to_phy_value(raw_val, compu_method)


def bytes_to_array_phy_value(byts: bytes, count: int, datatype: Datatype, alignment: Alignment, byte_order: ByteOrder,
                             compu_method: CompuMethod) \
        -> Tuple[List[int], List[Union[int, float]]]:
    start = 0
    deposit_size = calc_deposit_from_datatype(datatype, alignment)
    ret_raw = []
    ret_phy = []
    for i in range(count):
        raw_val, phy_val = bytes_to_single_phy_value(byts[start: start + deposit_size], datatype, alignment, byte_order,
                                                     compu_method)
        start += deposit_size
        ret_raw.append(raw_val)
        ret_phy.append(phy_val)
    return ret_raw, ret_phy


def calc_phy_value_4_signal(byts: bytes, obj: Asap2Signal) \
        -> Tuple[int, Union[int, float, str]]:
    return bytes_to_single_phy_value(byts,
                                     obj.datatype,
                                     obj.alignment,
                                     obj.parent.byte_order,
                                     obj.compu_method_ref)


def bytes_to_phy_value(byts: bytes, obj: Union[Asap2Parameter, Asap2Signal]) \
        -> Tuple[Union[int, List, Tuple], Union[int, float, str, List, Tuple]]:
    if type(obj) is Asap2Parameter:
        return calc_phy_value_4_parameter(byts, obj)
    elif type(obj) is Asap2Signal:
        return calc_phy_value_4_signal(byts, obj)


def calc_bytes_4_parameter(phy_value: Union[int, float, List, List[List]], obj: Asap2Parameter) \
        -> bytes:
    if obj.parameter_type == ParameterType.VALUE:
        return single_phy_value_to_bytes(phy_value,
                                         obj.datatype,
                                         obj.parent.byte_order,
                                         obj.compu_method_ref)
    elif obj.parameter_type == ParameterType.ASCII:
        raise Exception('string is not allowed to be calibrated')
    elif obj.parameter_type == ParameterType.ARRAY:
        return array_phy_value_to_bytes(phy_value,
                                        obj.datatype,
                                        obj.parent.byte_order,
                                        obj.compu_method_ref)
    elif obj.parameter_type == ParameterType.CURVE:
        raise Exception('unimplemented yet')
    elif obj.parameter_type == ParameterType.MAP:
        raise Exception('unimplemented yet')


def calc_bytes_4_signal(phy_value: Union[int, float, List], obj: Asap2Signal) \
        -> bytes:
    return single_phy_value_to_bytes(phy_value,
                                     obj.datatype,
                                     obj.parent.byte_order,
                                     obj.compu_method_ref)


def raw_value_to_bytes(raw_value: Union[int, float], datatype: Datatype,
                       byte_order: ByteOrder) -> bytes:
    bo = "big" if byte_order == ByteOrder.MSB_FIRST else "little"
    fmt_datatype = {
        Datatype.SBYTE: 'b',
        Datatype.UBYTE: 'B',
        Datatype.SWORD: 'h',
        Datatype.UWORD: 'H',
        Datatype.SLONG: 'l',
        Datatype.ULONG: 'L',
        Datatype.A_INT64: 'q',
        Datatype.A_UINT64: 'Q',
        Datatype.FLOAT32_IEEE: 'f',
        Datatype.FLOAT64_IEEE: 'd',
    }[datatype]
    fmt_endian = '>' if bo == "big" else '<'
    return struct.pack(f'{fmt_endian}{fmt_datatype}', int(raw_value))


def phy_value_to_raw_value(phy_value: Union[int, float, str], dt: Datatype, compu_method: CompuMethod):
    if not compu_method or compu_method.compu_method_type == CompuMethodType.IDENTICAL:
        return phy_value
    out = None
    if compu_method.compu_method_type == CompuMethodType.LINEAR:
        val = (phy_value - compu_method.coeffs.b) / compu_method.coeffs.a
        if dt in [Datatype.FLOAT32_IEEE, Datatype.FLOAT64_IEEE]:
            out = float(val)
        else:
            out = int(val)
    elif compu_method.compu_method_type == CompuMethodType.DICT:
        dic = compu_method.dictionary
        for k, v in dic.items():
            if v == phy_value:
                out = k
    else:
        raise Exception("unimplemented compu_method")
    return out


def single_phy_value_to_bytes(phy_value: Union[int, float], dt: Datatype, bo: ByteOrder,
                              cm: CompuMethod) -> bytes:
    raw_value = phy_value_to_raw_value(phy_value, dt, cm)
    return raw_value_to_bytes(raw_value, dt, bo)


def array_phy_value_to_bytes(phy_value: List[Union[int, float]], dt: Datatype,
                             bo: ByteOrder, cm: CompuMethod) -> bytes:
    ret = bytes()
    for p in phy_value:
        ret += single_phy_value_to_bytes(p, dt, bo, cm)
    return ret


def phy_value_to_bytes(phy_value: Union[int, float, List],
                       obj: Union[Asap2Parameter, Asap2Signal]) -> bytes:
    # todo: alignment is not considered yet
    if type(obj) is Asap2Parameter:
        return calc_bytes_4_parameter(phy_value, obj)
    elif type(obj) is Asap2Signal:
        return calc_bytes_4_signal(phy_value, obj)
