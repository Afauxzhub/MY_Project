# -*- coding: utf-8 -*-
"""Qt error dialog with an explicit animator-controlled report upload."""
from __future__ import print_function

from PySide2 import QtWidgets

from core.op_error_reporting import create_error_report, upload_report


try:
    _text_type = unicode
except NameError:
    _text_type = str


def _as_text(value):
    if value is None:
        return u""
    if isinstance(value, _text_type):
        return value
    try:
        return _text_type(value)
    except Exception:
        return u""


def show_reportable_error(parent, title, message, tool_id, tool_name,
                          config=None, exception=None, traceback_text=None,
                          context=None, attachments=None, tool_version=u"",
                          warning=False):
    """Show an error and offer upload; never upload without a button click."""
    descriptor = None
    creation_error = u""
    try:
        descriptor = create_error_report(
            tool_id=tool_id,
            tool_name=tool_name,
            message=message,
            config=config,
            exception=exception,
            traceback_text=traceback_text,
            context=context,
            attachments=attachments,
            tool_version=tool_version,
        )
    except Exception as error:
        creation_error = _as_text(error)

    box = QtWidgets.QMessageBox(parent)
    box.setIcon(QtWidgets.QMessageBox.Warning if warning else QtWidgets.QMessageBox.Critical)
    box.setWindowTitle(_as_text(title))
    box.setText(_as_text(message))
    upload_button = None
    if descriptor is not None:
        upload_button = box.addButton(u"上传报错", QtWidgets.QMessageBox.ActionRole)
        box.setDetailedText(
            u"报告编号: {0}\n本机报告: {1}\n公盘目录: {2}".format(
                descriptor.get(u"report_id", u""),
                descriptor.get(u"local_dir", u""),
                descriptor.get(u"public_root", u""),
            )
        )
    elif creation_error:
        box.setInformativeText(
            u"本机报错报告生成失败，因此当前无法上传：{0}".format(creation_error)
        )
    close_button = box.addButton(u"关闭", QtWidgets.QMessageBox.RejectRole)
    box.setDefaultButton(close_button)
    box.exec_()

    if upload_button is None or box.clickedButton() != upload_button:
        return descriptor
    try:
        destination = upload_report(descriptor)
        QtWidgets.QMessageBox.information(
            parent,
            u"报错已上传",
            u"报告编号：{0}\n\n已上传到：\n{1}".format(
                descriptor.get(u"report_id", u""), destination
            ),
        )
    except Exception as error:
        QtWidgets.QMessageBox.warning(
            parent,
            u"报错上传失败",
            u"公盘上传失败，但本机报告仍然保留。\n\n原因：{0}\n\n本机报告：\n{1}".format(
                _as_text(error), descriptor.get(u"local_dir", u"")
            ),
        )
    return descriptor
