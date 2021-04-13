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

import re

from PySide2 import QtCore
from PySide2.QtCore import QSize, QByteArray
from PySide2.QtGui import QIcon, QPixmap, QColor, Qt, QPainter, QImage
from PySide2.QtSvg import QSvgRenderer

icons = {}


def get_icon_by_name(name, color='black'):
    key = name + ':' + color
    if key not in icons.keys():
        renderer = QSvgRenderer(f'icon/{name}.svg')
        pixmap = QPixmap(renderer.defaultSize())
        pixmap.fill(Qt.transparent)
        painter = QPainter()
        painter.begin(pixmap)
        renderer.render(painter)
        painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
        painter.fillRect(pixmap.rect(), QColor(color))
        painter.end()
        icons[key] = QIcon(pixmap)
    return icons[key]


class Icon:
    @classmethod
    def app(cls):
        return get_icon_by_name('app', 'blue')

    @classmethod
    def symbol(cls):
        return get_icon_by_name('alphabetical', 'saddlebrown')

    @classmethod
    def trace(cls):
        return get_icon_by_name('email-outline', 'saddlebrown')

    @classmethod
    def simnode(cls):
        return get_icon_by_name('lan-connect', 'saddlebrown')

    @classmethod
    def scalar_parameter(cls):
        return get_icon_by_name('decimal', 'limegreen')

    @classmethod
    def array_parameter(cls):
        return get_icon_by_name('chart-bell-curve', 'limegreen')

    @classmethod
    def scalar_signal(cls):
        return get_icon_by_name('decimal', 'red')

    @classmethod
    def chart(cls):
        return get_icon_by_name('chart-multiple', 'red')

    @classmethod
    def settings(cls):
        return get_icon_by_name('settings', 'saddlebrown')

    @classmethod
    def database(cls):
        return get_icon_by_name('database', 'gray')

    @classmethod
    def message(cls):
        return get_icon_by_name('email-outline', 'gray')

    @classmethod
    def string(cls):
        return get_icon_by_name('code-string', 'green')

    @classmethod
    def signal(cls):
        return get_icon_by_name('chart-line-variant', 'red')

    @classmethod
    def signal_array(cls):
        return get_icon_by_name('code-array', 'red')

    @classmethod
    def parameter(cls):
        return get_icon_by_name('decimal', 'green')

    @classmethod
    def parameter_map(cls):
        return get_icon_by_name('map', 'green')

    @classmethod
    def parameter_curve(cls):
        return get_icon_by_name('chart-bell-curve', 'green')

    @classmethod
    def connect(cls):
        return get_icon_by_name('link-variant', 'yellowgreen')

    @classmethod
    def disconnect(cls):
        return get_icon_by_name('link-variant-off', 'red')

    @classmethod
    def play(cls):
        return get_icon_by_name('play', 'yellowgreen')

    @classmethod
    def stop(cls):
        return get_icon_by_name('stop', 'red')

    @classmethod
    def diag_console(cls):
        return get_icon_by_name('magnify-scan', 'saddlebrown')