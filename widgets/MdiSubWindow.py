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

from PySide2 import QtWidgets, QtGui, QtCore

def create_icon_by_color(color):
    pixmap = QtGui.QPixmap(512, 512)
    pixmap.fill(color)
    return QtGui.QIcon(pixmap)

class TitleProxyStyle(QtWidgets.QProxyStyle):
    def drawComplexControl(self, control, option, painter, widget=None):
        if control == QtWidgets.QStyle.CC_TitleBar:
            if hasattr(widget, "titleColor"):
                color = widget.titleColor
                if color.isValid():
                    option.palette.setBrush(
                        QtGui.QPalette.Highlight, QtGui.QColor(color)
                    )
            option.icon = create_icon_by_color(QtGui.QColor("transparent"))
        super(TitleProxyStyle, self).drawComplexControl(
            control, option, painter, widget
        )


class MdiSubWindow(QtWidgets.QMdiSubWindow):
    def __init__(self, parent=None, flags=QtCore.Qt.Widget):
        super(MdiSubWindow, self).__init__(parent, flags)
        style = TitleProxyStyle(self.style())
        self.setStyle(style)
        self._titleColor = QtGui.QColor()

    @property
    def titleColor(self):
        return self._titleColor

    @titleColor.setter
    def titleColor(self, color):
        self._titleColor = color
        self.update()
