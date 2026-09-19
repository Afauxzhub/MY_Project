# ASCII-only entry: Max 2020 evaluates batch Python scripts as Unicode strings.
from __future__ import print_function
import io
import os
import runpy
import sys
import traceback

sys.dont_write_bytecode = True
report = os.environ.get('ANIMATION_NAMING_REPORT')
try:
    validation_dir = os.path.dirname(os.path.abspath(__file__))
    runpy.run_path(os.path.join(validation_dir, 'validate_personal_naming.py'), run_name='__main__')
    from ui import rm_new_file_dialog as new_file
    from ui.rm_rename_dialog import RenameDialog
    from ui.rm_tool_windows import detect_publish_type_from_filename
    fake_assets = os.path.abspath(os.path.join(validation_dir, 'TestOnly', 'Client', 'Assets'))
    original_publish_reader = new_file.load_publish_config
    original_browser_reader = new_file.load_anim_file_manager_config
    new_file.load_publish_config = lambda: {'unity_root': fake_assets}
    new_file.load_anim_file_manager_config = lambda root: {'local_root': validation_dir}
    try:
        window = new_file.NewFileDialog()
        window._character_edit.setText('Player')
        window._action_edit.setText('Run')
        window._update_preview(force_path=True)
        assert window._filename_edit.text() == 'Player_Unarmed_Run.max'
        assert window._path_edit.text().replace('\\', '/').endswith('/ArtSource/Characters/Player/Animations/Locomotion/Player_Unarmed_Run.max')
        window._action_set_edit.setText('Sword')
        assert window._filename_edit.text() == 'Player_Sword_Run.max'
        window._action_set_edit.clear()
        assert window._filename_edit.text() == 'Player_Run.max'
        window._naming_mode.setCurrentIndex(1)
        assert window._filename_edit.text() == 'Role_Player_Run.max'
        window._naming_mode.setCurrentIndex(0)
        window._action_set_edit.setText('Unarmed')
        assert window._filename_edit.text() == 'Player_Unarmed_Run.max'
        window._filename_edit.setText('Player_Unarmed_Run_Final.max')
        assert not window._validate_preview_filename(window._filename_edit)[0]
        window._filename_edit.setText('Player_Spear_Idle.max')
        assert window._validate_preview_filename(window._filename_edit)[0]
        rename = RenameDialog('Player_Spear_Idle', 'indoor')
        assert rename._ok_btn.isEnabled()
        rename._name_edit.setText('Player__Idle')
        assert not rename._ok_btn.isEnabled()
        assert detect_publish_type_from_filename('Player_Unarmed_Idle.max', {}) == 'indoor'
        assert detect_publish_type_from_filename('DI_Chap01_SC01.max', {}) == 'outdoor'
        rename.close()
        window.close()
    finally:
        new_file.load_publish_config = original_publish_reader
        new_file.load_anim_file_manager_config = original_browser_reader
    result = u'MAX2020_PYTHON_UI_PASS\n' + sys.version
    print(result)
except Exception:
    result = traceback.format_exc()
    print(result)
    raise
finally:
    if report:
        with io.open(report, 'w', encoding='utf-8') as stream:
            stream.write(result if isinstance(result, type(u'')) else result.decode('utf-8', 'replace'))
