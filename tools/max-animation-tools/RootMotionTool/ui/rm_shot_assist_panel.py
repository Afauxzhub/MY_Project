# -*- coding: utf-8 -*-
"""
镜头辅助工具页签

在 3ds Max 中给当前相机前方生成构图辅助线框。
线框作为 SplineShape 挂到相机下，便于在相机视图中直接观察。
"""
from __future__ import division
import math

from PySide2 import QtCore, QtWidgets

try:
    _text_type = unicode
except NameError:
    _text_type = str


GUIDE_LABELS = [
    u"三分法",
    u"黄金分割",
    u"斐波那契螺旋",
    u"黄金三角",
    u"画幅框",
    u"汇聚引导线",
]

SPIRAL_FOCUS_LABELS = [u"左上", u"左下", u"右上", u"右下"]
TRIANGLE_DIAGONAL_LABELS = [u"左下 到 右上", u"左上 到 右下"]

GUIDE_COLORS = {
    0: (0, 235, 255),
    1: (255, 198, 20),
    2: (40, 255, 70),
    3: (255, 0, 235),
    4: (255, 140, 0),
    5: (255, 38, 38),
}

THICKNESS_TO_FRAME_HEIGHT_RATIO = 0.001072


class ShotAssistPanel(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super(ShotAssistPanel, self).__init__(parent)
        self._rt = None
        self._camera = None
        self._syncing = False
        self._build_ui()

    def bind_runtime(self, rt):
        self._rt = rt
        self._refresh_camera_label()

    def showEvent(self, event):
        super(ShotAssistPanel, self).showEvent(event)
        QtCore.QTimer.singleShot(0, self._refresh_camera_label)

    def _ensure_rt(self):
        if self._rt is None:
            import pymxs
            self._rt = pymxs.runtime
        return self._rt

    def _build_ui(self):
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        hint = QtWidgets.QLabel(
            u"选中相机后点击“使用选中相机”，工具会在相机前方生成构图辅助线。\n"
            u"辅助线为 Max 场景中的样条线，跟随相机移动；参数调整后会自动刷新。"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(u"color: #aab4c8; font-size: 11px;")
        lay.addWidget(hint)

        camera_group = QtWidgets.QGroupBox(u"目标相机")
        camera_lay = QtWidgets.QVBoxLayout(camera_group)
        camera_lay.setContentsMargins(10, 8, 10, 8)
        self._camera_label = QtWidgets.QLabel(u"当前相机：未指定")
        self._camera_label.setWordWrap(True)
        camera_lay.addWidget(self._camera_label)
        camera_btn_lay = QtWidgets.QHBoxLayout()
        use_selected_btn = QtWidgets.QPushButton(u"使用选中相机")
        use_selected_btn.clicked.connect(self._use_selected_camera)
        find_main_btn = QtWidgets.QPushButton(u"查找 Main_Camera")
        find_main_btn.clicked.connect(self._use_main_camera)
        camera_btn_lay.addWidget(use_selected_btn)
        camera_btn_lay.addWidget(find_main_btn)
        camera_lay.addLayout(camera_btn_lay)
        lay.addWidget(camera_group)

        guide_group = QtWidgets.QGroupBox(u"辅助线")
        guide_lay = QtWidgets.QVBoxLayout(guide_group)
        guide_lay.setContentsMargins(10, 8, 10, 8)
        self._show_chk = QtWidgets.QCheckBox(u"显示辅助线")
        self._show_chk.setChecked(True)
        self._show_chk.stateChanged.connect(self._on_control_changed)
        guide_lay.addWidget(self._show_chk)

        form = QtWidgets.QFormLayout()
        self._guide_combo = QtWidgets.QComboBox()
        self._guide_combo.addItems(GUIDE_LABELS)
        self._guide_combo.currentIndexChanged.connect(self._on_guide_changed)
        form.addRow(u"辅助线类型", self._guide_combo)

        self._distance_spn = QtWidgets.QDoubleSpinBox()
        self._distance_spn.setRange(0.1, 10000.0)
        self._distance_spn.setValue(5.0)
        self._distance_spn.setDecimals(2)
        self._distance_spn.setSingleStep(0.1)
        self._distance_spn.valueChanged.connect(self._on_control_changed)
        form.addRow(u"相机前方距离", self._distance_spn)

        self._opacity_sld, self._opacity_label = self._make_slider(5, 100, 100)
        self._opacity_sld.valueChanged.connect(self._on_control_changed)
        form.addRow(u"透明度", self._wrap_slider(self._opacity_sld, self._opacity_label, 100.0))

        self._thickness_sld, self._thickness_label = self._make_slider(1, 5, 2)
        self._thickness_sld.valueChanged.connect(self._on_control_changed)
        form.addRow(u"线宽", self._wrap_slider(self._thickness_sld, self._thickness_label, 1.0))
        guide_lay.addLayout(form)
        lay.addWidget(guide_group)

        self._golden_group = self._make_group(u"黄金矩形")
        golden_form = QtWidgets.QFormLayout(self._golden_group)
        self._golden_offset_sld, self._golden_offset_label = self._make_slider(-100, 100, 0)
        self._golden_offset_sld.valueChanged.connect(self._on_control_changed)
        golden_form.addRow(u"黄金矩形左右位置", self._wrap_slider(self._golden_offset_sld, self._golden_offset_label, 100.0))
        golden_form.addRow(u"位置说明", QtWidgets.QLabel(u"最左 = -1，居中 = 0，最右 = 1"))
        lay.addWidget(self._golden_group)

        self._spiral_group = self._make_group(u"斐波那契螺旋")
        spiral_form = QtWidgets.QFormLayout(self._spiral_group)
        self._spiral_focus_combo = QtWidgets.QComboBox()
        self._spiral_focus_combo.addItems(SPIRAL_FOCUS_LABELS)
        self._spiral_focus_combo.setCurrentIndex(2)
        self._spiral_focus_combo.currentIndexChanged.connect(self._on_control_changed)
        spiral_form.addRow(u"螺旋中心", self._spiral_focus_combo)
        lay.addWidget(self._spiral_group)

        self._triangle_group = self._make_group(u"黄金三角")
        triangle_form = QtWidgets.QFormLayout(self._triangle_group)
        self._triangle_diag_combo = QtWidgets.QComboBox()
        self._triangle_diag_combo.addItems(TRIANGLE_DIAGONAL_LABELS)
        self._triangle_diag_combo.currentIndexChanged.connect(self._on_control_changed)
        triangle_form.addRow(u"对角线方向", self._triangle_diag_combo)
        lay.addWidget(self._triangle_group)

        self._focus_group = self._make_group(u"汇聚引导线")
        focus_form = QtWidgets.QFormLayout(self._focus_group)
        self._focus_x_sld, self._focus_x_label = self._make_slider(-100, 100, 0)
        self._focus_y_sld, self._focus_y_label = self._make_slider(-100, 100, 0)
        self._focus_x_sld.valueChanged.connect(self._on_control_changed)
        self._focus_y_sld.valueChanged.connect(self._on_control_changed)
        focus_form.addRow(u"汇聚点横向位置", self._wrap_slider(self._focus_x_sld, self._focus_x_label, 100.0))
        focus_form.addRow(u"汇聚点纵向位置", self._wrap_slider(self._focus_y_sld, self._focus_y_label, 100.0))
        focus_form.addRow(u"位置说明", QtWidgets.QLabel(u"中心 = 0，左/上 = -1，右/下 = 1"))
        lay.addWidget(self._focus_group)

        self._frame_group = self._make_group(u"画幅框")
        frame_lay = QtWidgets.QVBoxLayout(self._frame_group)
        self._frame_one_size_sld, self._frame_one_size_label = self._make_slider(0, 100, 100)
        self._frame_one_x_sld, self._frame_one_x_label = self._make_slider(-100, 100, 0)
        self._frame_one_y_sld, self._frame_one_y_label = self._make_slider(-100, 100, 0)
        self._frame_two_size_sld, self._frame_two_size_label = self._make_slider(0, 100, 68)
        self._frame_two_x_sld, self._frame_two_x_label = self._make_slider(-100, 100, 0)
        self._frame_two_y_sld, self._frame_two_y_label = self._make_slider(-100, 100, 0)
        self._add_frame_controls(frame_lay, u"框架一", self._frame_one_size_sld, self._frame_one_size_label,
                                 self._frame_one_x_sld, self._frame_one_x_label,
                                 self._frame_one_y_sld, self._frame_one_y_label)
        self._add_frame_controls(frame_lay, u"框架二", self._frame_two_size_sld, self._frame_two_size_label,
                                 self._frame_two_x_sld, self._frame_two_x_label,
                                 self._frame_two_y_sld, self._frame_two_y_label)
        frame_lay.addWidget(QtWidgets.QLabel(u"大小 0 = 点，大小 1 = 顶满画框；位置中心 = 0，左/上 = -1，右/下 = 1"))
        lay.addWidget(self._frame_group)

        btn_lay = QtWidgets.QHBoxLayout()
        apply_btn = QtWidgets.QPushButton(u"应用/刷新辅助线")
        apply_btn.clicked.connect(self.apply_guides)
        delete_btn = QtWidgets.QPushButton(u"删除当前相机辅助线")
        delete_btn.clicked.connect(self.delete_guides)
        btn_lay.addWidget(apply_btn)
        btn_lay.addWidget(delete_btn)
        lay.addLayout(btn_lay)

        lay.addStretch()
        self._on_guide_changed()

    def _make_group(self, title):
        group = QtWidgets.QGroupBox(title)
        group.setContentsMargins(0, 0, 0, 0)
        return group

    def _make_slider(self, min_value, max_value, value):
        slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        slider.setRange(min_value, max_value)
        slider.setValue(value)
        label = QtWidgets.QLabel()
        label.setMinimumWidth(42)
        return slider, label

    def _wrap_slider(self, slider, label, divisor):
        box = QtWidgets.QWidget()
        lay = QtWidgets.QHBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(slider, 1)
        lay.addWidget(label)

        def _update(v):
            label.setText(u"{0:.2f}".format(v / divisor))

        slider.valueChanged.connect(_update)
        _update(slider.value())
        return box

    def _add_frame_controls(self, parent_lay, title, size_sld, size_label, x_sld, x_label, y_sld, y_label):
        parent_lay.addWidget(QtWidgets.QLabel(u"<b>{0}</b>".format(title)))
        form = QtWidgets.QFormLayout()
        form.addRow(u"大小", self._wrap_slider(size_sld, size_label, 100.0))
        form.addRow(u"左右位置", self._wrap_slider(x_sld, x_label, 100.0))
        form.addRow(u"上下位置", self._wrap_slider(y_sld, y_label, 100.0))
        parent_lay.addLayout(form)
        for sld in (size_sld, x_sld, y_sld):
            sld.valueChanged.connect(self._on_control_changed)

    def _on_guide_changed(self, *args):
        guide = self._guide_combo.currentIndex()
        self._golden_group.setVisible(guide in (2, 3))
        self._spiral_group.setVisible(guide == 2)
        self._triangle_group.setVisible(guide == 3)
        self._frame_group.setVisible(guide == 4)
        self._focus_group.setVisible(guide == 5)
        self._on_control_changed()

    def _on_control_changed(self, *args):
        if self._syncing:
            return
        self._update_slider_labels()
        if self._camera is not None and self._show_chk.isChecked():
            self.apply_guides()
        elif self._camera is not None:
            self.delete_guides()

    def _update_slider_labels(self):
        pairs = [
            (self._golden_offset_sld, self._golden_offset_label, 100.0),
            (self._focus_x_sld, self._focus_x_label, 100.0),
            (self._focus_y_sld, self._focus_y_label, 100.0),
            (self._opacity_sld, self._opacity_label, 100.0),
            (self._thickness_sld, self._thickness_label, 1.0),
            (self._frame_one_size_sld, self._frame_one_size_label, 100.0),
            (self._frame_one_x_sld, self._frame_one_x_label, 100.0),
            (self._frame_one_y_sld, self._frame_one_y_label, 100.0),
            (self._frame_two_size_sld, self._frame_two_size_label, 100.0),
            (self._frame_two_x_sld, self._frame_two_x_label, 100.0),
            (self._frame_two_y_sld, self._frame_two_y_label, 100.0),
        ]
        for slider, label, divisor in pairs:
            label.setText(u"{0:.2f}".format(slider.value() / divisor))

    def _use_selected_camera(self):
        rt = self._ensure_rt()
        selected = self._selected_nodes()
        if not selected:
            QtWidgets.QMessageBox.warning(self, u"提示", u"请先在场景中选中一个相机。")
            return
        node = selected[0]
        if not self._is_camera(node):
            QtWidgets.QMessageBox.warning(self, u"提示", u"当前选中对象不是相机。")
            return
        self._camera = node
        self._refresh_camera_label()
        self.apply_guides()

    def _selected_nodes(self):
        rt = self._ensure_rt()
        try:
            return list(rt.selection)
        except Exception:
            pass
        selected = []
        try:
            count = int(rt.selection.count)
            for i in range(1, count + 1):
                selected.append(rt.selection[i])
        except Exception:
            pass
        return selected

    def _use_main_camera(self):
        rt = self._ensure_rt()
        node = rt.getNodeByName(u"Main_Camera")
        if node is None or not rt.isValidNode(node):
            QtWidgets.QMessageBox.warning(self, u"提示", u"场景中找不到 Main_Camera。")
            return
        if not self._is_camera(node):
            QtWidgets.QMessageBox.warning(self, u"提示", u"Main_Camera 不是相机对象。")
            return
        self._camera = node
        self._refresh_camera_label()
        self.apply_guides()

    def _refresh_camera_label(self):
        if self._camera is not None:
            try:
                rt = self._ensure_rt()
                if rt.isValidNode(self._camera):
                    self._camera_label.setText(u"当前相机：{0}".format(_text_type(self._camera.name)))
                    return
            except Exception:
                pass
        self._camera_label.setText(u"当前相机：未指定")

    def _is_camera(self, node):
        rt = self._ensure_rt()
        try:
            return bool(rt.isKindOf(node, rt.Camera))
        except Exception:
            pass
        try:
            return _text_type(rt.superClassOf(node)).lower().find("camera") >= 0
        except Exception:
            return False

    def apply_guides(self):
        rt = self._ensure_rt()
        if self._camera is None or not rt.isValidNode(self._camera):
            self._refresh_camera_label()
            return
        if not self._show_chk.isChecked():
            self.delete_guides()
            return
        existing = rt.getNodeByName(self._guide_node_name(self._camera))
        if existing is not None and rt.isValidNode(existing) and self._is_auto_key_enabled():
            self._key_existing_shape(existing)
            self._refresh_camera_label()
            return
        self.delete_guides()
        segments = self._build_segments()
        if not segments:
            return
        shape = self._create_shape(segments)
        if shape is None:
            return
        self._refresh_camera_label()

    def delete_guides(self):
        rt = self._ensure_rt()
        if self._camera is None:
            return
        name = self._guide_node_name(self._camera)
        node = rt.getNodeByName(name)
        if node is not None and rt.isValidNode(node):
            try:
                rt.delete(node)
            except Exception:
                pass

    def _guide_node_name(self, camera):
        return u"OP_镜头辅助线_{0}".format(_text_type(camera.name))

    def _camera_frame(self):
        rt = self._ensure_rt()
        distance = float(self._distance_spn.value())
        fov = 45.0
        try:
            fov = float(self._camera.fov)
        except Exception:
            pass
        if fov > math.pi * 2.0:
            fov_rad = math.radians(fov)
        else:
            fov_rad = fov
        if fov_rad <= 0.01:
            fov_rad = math.radians(45.0)
        aspect = 2400.0 / 1080.0
        frame_width = 2.0 * distance * math.tan(fov_rad * 0.5)
        frame_height = frame_width / aspect
        self._last_frame_width = frame_width
        self._last_frame_height = frame_height
        self._last_distance = distance
        self._last_fov_rad = fov_rad
        return frame_width, frame_height, distance

    def _build_segments(self):
        frame_width, frame_height, distance = self._camera_frame()
        guide = self._guide_combo.currentIndex()
        lines = []
        if guide == 0:
            self._rule_of_thirds(lines, frame_width, frame_height)
        elif guide == 1:
            self._golden_ratio(lines, frame_width, frame_height)
        elif guide == 2:
            self._fibonacci(lines, frame_width, frame_height)
        elif guide == 3:
            self._golden_triangle(lines, frame_width, frame_height)
        elif guide == 4:
            self._frame_box(lines, frame_width, frame_height)
        elif guide == 5:
            self._focus_lines(lines, frame_width, frame_height)
        return [(self._to_point(a[0], a[1], frame_width, frame_height, distance),
                 self._to_point(b[0], b[1], frame_width, frame_height, distance)) for a, b in lines]

    def _to_point(self, x, y, width, height, distance):
        rt = self._ensure_rt()
        return rt.Point3(x - width * 0.5, height * 0.5 - y, -distance)

    def _line(self, lines, x1, y1, x2, y2):
        lines.append(((x1, y1), (x2, y2)))

    def _rect(self, lines, rect):
        x, y, w, h = rect
        self._line(lines, x, y, x + w, y)
        self._line(lines, x + w, y, x + w, y + h)
        self._line(lines, x + w, y + h, x, y + h)
        self._line(lines, x, y + h, x, y)

    def _circle(self, lines, cx, cy, radius, segments=24):
        prev = None
        for i in range(segments + 1):
            a = math.pi * 2.0 * i / segments
            p = (cx + math.cos(a) * radius, cy + math.sin(a) * radius)
            if prev is not None:
                lines.append((prev, p))
            prev = p

    def _arc(self, lines, cx, cy, radius, start_deg, end_deg, segments=48):
        prev = None
        for i in range(segments + 1):
            t = i / float(segments)
            a = math.radians(start_deg + (end_deg - start_deg) * t)
            p = (cx + math.cos(a) * radius, cy + math.sin(a) * radius)
            if prev is not None:
                lines.append((prev, p))
            prev = p

    def _rule_of_thirds(self, lines, w, h):
        self._line(lines, w / 3.0, 0, w / 3.0, h)
        self._line(lines, w * 2.0 / 3.0, 0, w * 2.0 / 3.0, h)
        self._line(lines, 0, h / 3.0, w, h / 3.0)
        self._line(lines, 0, h * 2.0 / 3.0, w, h * 2.0 / 3.0)
        r = min(w, h) * 0.008
        for x in (w / 3.0, w * 2.0 / 3.0):
            for y in (h / 3.0, h * 2.0 / 3.0):
                self._circle(lines, x, y, r)

    def _golden_ratio(self, lines, w, h):
        for x in (w * 0.382, w * 0.618):
            self._line(lines, x, 0, x, h)
        for y in (h * 0.382, h * 0.618):
            self._line(lines, 0, y, w, y)
        r = min(w, h) * 0.008
        for x in (w * 0.382, w * 0.618):
            for y in (h * 0.382, h * 0.618):
                self._circle(lines, x, y, r)

    def _golden_rect(self, w, h):
        phi = 1.61803398875
        gw = min(w, h * phi)
        gh = gw / phi
        if gh > h:
            gh = h
            gw = gh * phi
        max_offset = (w - gw) * 0.5
        offset = self._golden_offset_sld.value() / 100.0
        x = max_offset + max(-1.0, min(1.0, offset)) * max_offset
        y = (h - gh) * 0.5
        return x, y, gw, gh

    def _fibonacci(self, lines, w, h):
        rect = self._golden_rect(w, h)
        self._rect(lines, rect)
        x, y, rw, rh = rect
        phi = 1.61803398875
        s0 = rh
        sizes = [s0]
        for _ in range(6):
            sizes.append(sizes[-1] / phi)
        s0, s1, s2, s3, s4, s5, s6 = sizes[:7]
        arcs = [
            ((x + s0, y + s0), s0, 180.0, 270.0),
            ((x + s0, y + s1), s1, 270.0, 360.0),
            ((x + s0 + s1 - s2, y + s1), s2, 0.0, 90.0),
            ((x + s0 + s1 - s2, y + s1 + s2 - s3), s3, 90.0, 180.0),
            ((x + s0 + s1 - s2 - s3 + s4, y + s1 + s2 - s3), s4, 180.0, 270.0),
            ((x + s0 + s1 - s2 - s3 + s4, y + s1 + s2 - s3 - s4 + s5), s5, 270.0, 360.0),
            ((x + s0 + s1 - s2 - s3 + s4 + s5 - s6, y + s1 + s2 - s3 - s4 + s5), s6, 0.0, 90.0),
        ]
        focus = self._spiral_focus_combo.currentIndex()
        for center, radius, start, end in arcs:
            self._arc_transformed(lines, center[0], center[1], radius, start, end, rect, focus)

    def _transform_spiral_point(self, x, y, rect, focus):
        rx, ry, rw, rh = rect
        if focus in (0, 1):
            x = rx + rw - (x - rx)
        if focus in (1, 3):
            y = ry + rh - (y - ry)
        return x, y

    def _arc_transformed(self, lines, cx, cy, radius, start_deg, end_deg, rect, focus):
        prev = None
        for i in range(49):
            t = i / 48.0
            a = math.radians(start_deg + (end_deg - start_deg) * t)
            x = cx + math.cos(a) * radius
            y = cy + math.sin(a) * radius
            p = self._transform_spiral_point(x, y, rect, focus)
            if prev is not None:
                lines.append((prev, p))
            prev = p

    def _golden_triangle(self, lines, w, h):
        rect = self._golden_rect(w, h)
        self._rect(lines, rect)
        x, y, rw, rh = rect
        if self._triangle_diag_combo.currentIndex() == 0:
            a, b = (x, y + rh), (x + rw, y)
            c, d = (x, y), (x + rw, y + rh)
        else:
            a, b = (x, y), (x + rw, y + rh)
            c, d = (x, y + rh), (x + rw, y)
        fc = self._project_point(c, a, b)
        fd = self._project_point(d, a, b)
        lines.append((a, b))
        lines.append((c, fc))
        lines.append((d, fd))
        r = min(w, h) * 0.008
        self._circle(lines, fc[0], fc[1], r)
        self._circle(lines, fd[0], fd[1], r)

    def _project_point(self, p, a, b):
        ax, ay = a
        bx, by = b
        px, py = p
        vx, vy = bx - ax, by - ay
        denom = vx * vx + vy * vy
        if denom <= 0.000001:
            return a
        t = ((px - ax) * vx + (py - ay) * vy) / denom
        return ax + vx * t, ay + vy * t

    def _frame_box(self, lines, w, h):
        f1 = self._movable_frame(w, h,
                                  self._frame_one_size_sld.value() / 100.0,
                                  self._frame_one_x_sld.value() / 100.0,
                                  self._frame_one_y_sld.value() / 100.0)
        f2 = self._movable_frame(w, h,
                                  self._frame_two_size_sld.value() / 100.0,
                                  self._frame_two_x_sld.value() / 100.0,
                                  self._frame_two_y_sld.value() / 100.0)
        self._rect(lines, f1)
        self._rect(lines, f2)
        x1, y1, w1, h1 = f1
        x2, y2, w2, h2 = f2
        self._line(lines, x1, y1, x2, y2)
        self._line(lines, x1 + w1, y1, x2 + w2, y2)
        self._line(lines, x1, y1 + h1, x2, y2 + h2)
        self._line(lines, x1 + w1, y1 + h1, x2 + w2, y2 + h2)

    def _movable_frame(self, w, h, size, ox, oy):
        size = max(0.0, min(1.0, size))
        fw, fh = w * size, h * size
        half_w, half_h = fw * 0.5, fh * 0.5
        nx = (max(-1.0, min(1.0, ox)) + 1.0) * 0.5
        ny = (max(-1.0, min(1.0, oy)) + 1.0) * 0.5
        cx = half_w + (w - fw) * nx
        cy = half_h + (h - fh) * ny
        return cx - half_w, cy - half_h, fw, fh

    def _focus_lines(self, lines, w, h):
        cx = w * (0.5 + (self._focus_x_sld.value() / 100.0) * 0.5)
        cy = h * (0.5 + (self._focus_y_sld.value() / 100.0) * 0.5)
        points = [
            (0.0, 0.0), (w * 0.5, 0.0), (w, 0.0), (w, h * 0.5),
            (w, h), (w * 0.5, h), (0.0, h), (0.0, h * 0.5),
        ]
        for p in points:
            lines.append((p, (cx, cy)))
        self._circle(lines, cx, cy, min(w, h) * 0.02)
        self._circle(lines, cx, cy, min(w, h) * 0.008)

    def _is_auto_key_enabled(self):
        rt = self._ensure_rt()
        try:
            return bool(rt.animButtonState)
        except Exception:
            return False

    def _ensure_key_helper(self):
        rt = self._ensure_rt()
        rt.execute(
            u"""
            global OP_ShotAssist_NormalizeFov
            global OP_ShotAssist_FovAt
            global OP_ShotAssist_SetLocalFrame
            global OP_ShotAssist_KeyCurrentFrame

            fn OP_ShotAssist_NormalizeFov f =
            (
                if f > (pi * 2.0) then degToRad f else f
            )

            fn OP_ShotAssist_FovAt cam t =
            (
                local f = 0.785398
                at time t
                (
                    try(f = cam.fov)catch()
                )
                OP_ShotAssist_NormalizeFov f
            )

            fn OP_ShotAssist_SetLocalFrame shape cam zOffset thicknessValue =
            (
                if shape == undefined or cam == undefined then return false
                try(shape.parent = cam)catch()
                try(in coordsys parent shape.pos = [0, 0, zOffset])catch()
                try(in coordsys parent shape.rotation = (quat 0 0 0 1))catch()
                try(in coordsys parent shape.scale = [1, 1, 1])catch()
                try(shape.render_thickness = thicknessValue)catch()
                true
            )

            fn OP_ShotAssist_KeyCurrentFrame shape cam baseDistance baseFrameWidth currentFov thicknessValue =
            (
                local normalizedCurrentFov = OP_ShotAssist_NormalizeFov currentFov
                local denom = tan(normalizedCurrentFov * 0.5)
                local targetDistance = baseDistance
                if (abs denom) > 0.000001 do
                (
                    targetDistance = (baseFrameWidth * 0.5) / denom
                )
                local zOffset = baseDistance - targetDistance
                with animate on
                (
                    at time currentTime (OP_ShotAssist_SetLocalFrame shape cam zOffset thicknessValue)
                )
                true
            )
            """
        )

    def _align_shape_to_camera(self, shape):
        rt = self._ensure_rt()
        try:
            shape.transform = self._camera.transform
            shape.parent = self._camera
        except Exception:
            try:
                shape.transform = self._camera.transform
            except Exception:
                pass

    def _current_thickness(self):
        frame_height = max(0.001, float(getattr(self, "_last_frame_height", 1.0)))
        return self._thickness_for_frame_height(frame_height)

    def _thickness_for_frame_height(self, frame_height):
        return max(0.001, float(frame_height)) * float(self._thickness_sld.value()) * THICKNESS_TO_FRAME_HEIGHT_RATIO

    def _key_existing_shape(self, shape):
        rt = self._ensure_rt()
        self._camera_frame()
        base_distance = float(getattr(self, "_last_distance", self._distance_spn.value()))
        base_frame_width = float(getattr(self, "_last_frame_width", 1.0))
        base_frame_height = float(getattr(self, "_last_frame_height", 1.0))
        base_fov = float(getattr(self, "_last_fov_rad", math.radians(45.0)))
        try:
            value = rt.getUserProp(shape, u"OPShotAssistBaseDistance")
            if value not in (None, u""):
                base_distance = float(value)
        except Exception:
            pass
        try:
            value = rt.getUserProp(shape, u"OPShotAssistBaseFov")
            if value not in (None, u""):
                base_fov = float(value)
        except Exception:
            pass
        base_frame_width = 2.0 * base_distance * math.tan(base_fov * 0.5)
        base_frame_height = base_frame_width / (2400.0 / 1080.0)
        try:
            value = rt.getUserProp(shape, u"OPShotAssistBaseFrameWidth")
            if value not in (None, u""):
                base_frame_width = float(value)
        except Exception:
            pass
        try:
            value = rt.getUserProp(shape, u"OPShotAssistBaseFrameHeight")
            if value not in (None, u""):
                base_frame_height = float(value)
        except Exception:
            pass
        try:
            self._ensure_key_helper()
            rt.OP_ShotAssist_KeyCurrentFrame(
                shape,
                self._camera,
                base_distance,
                base_frame_width,
                self._last_fov_rad,
                self._thickness_for_frame_height(base_frame_height)
            )
        except Exception:
            pass

    def _create_shape(self, segments):
        rt = self._ensure_rt()
        try:
            shape = rt.splineShape()
        except Exception:
            shape = rt.SplineShape()
        shape.name = self._guide_node_name(self._camera)
        color = GUIDE_COLORS.get(self._guide_combo.currentIndex(), (255, 255, 255))
        opacity = self._opacity_sld.value() / 100.0
        dimmed = [int(max(0, min(255, c * opacity))) for c in color]
        try:
            shape.wirecolor = rt.Color(dimmed[0], dimmed[1], dimmed[2])
        except Exception:
            pass
        for a, b in segments:
            try:
                rt.addNewSpline(shape)
                idx = rt.numSplines(shape)
                rt.addKnot(shape, idx, rt.Name("corner"), rt.Name("line"), a)
                rt.addKnot(shape, idx, rt.Name("corner"), rt.Name("line"), b)
            except Exception:
                pass
        try:
            rt.updateShape(shape)
        except Exception:
            pass
        self._align_shape_to_camera(shape)
        try:
            rt.setUserProp(shape, u"OPShotAssistBaseFov", _text_type(getattr(self, "_last_fov_rad", math.radians(45.0))))
        except Exception:
            pass
        try:
            rt.setUserProp(shape, u"OPShotAssistBaseDistance", _text_type(getattr(self, "_last_distance", self._distance_spn.value())))
        except Exception:
            pass
        try:
            rt.setUserProp(shape, u"OPShotAssistBaseFrameWidth", _text_type(getattr(self, "_last_frame_width", 1.0)))
        except Exception:
            pass
        try:
            rt.setUserProp(shape, u"OPShotAssistBaseFrameHeight", _text_type(getattr(self, "_last_frame_height", 1.0)))
        except Exception:
            pass
        thickness = self._current_thickness()
        for prop, value in (
            ("render_renderable", True),
            ("render_displayRenderMesh", True),
            ("render_thickness", thickness),
            ("render_sides", 4),
            ("renderable", False),
        ):
            try:
                setattr(shape, prop, value)
            except Exception:
                pass
        return shape
