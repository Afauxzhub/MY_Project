using System;
using Afauxzhub.Project.Animation;
using UnityEditor;
using UnityEngine;

namespace Afauxzhub.Project.Editor.Animation
{
    public sealed class CombatActionEditor : EditorWindow
    {
        [SerializeField] private ActionDefinition action;
        [SerializeField] private GameObject model;
        [SerializeField] private float time, frameRate = 30;
        [SerializeField] private bool snap = true;
        private AnimationPreview preview;
        private Vector2 scroll;
        private bool playing, loop = true;
        private float speed = 1, zoom = 1;
        private int selectedWindow = -1, selectedCue = -1, dragMode, dragEdge;
        private float dragMouse, dragStart, dragEnd;
        private double lastTick;
        private WindowKind newWindow;
        private CueKind newCue;
        private float timelineOffset;
        private const float LabelWidth = 155, RowHeight = 25;

        [MenuItem("Tools/MY Project/Animation/Combat Action Editor")]
        public static void Open() => GetWindow<CombatActionEditor>("Combat Action");
        public static void Open(ActionDefinition selected, GameObject previewModel)
        {
            var window = GetWindow<CombatActionEditor>("Combat Action");
            window.action = selected; window.model = previewModel; window.time = 0;
            window.selectedWindow = window.selectedCue = -1; window.preview?.InvalidateEffects(); window.Show();
        }
        private void OnEnable() { minSize = new Vector2(800, 650); preview = new AnimationPreview(); lastTick = EditorApplication.timeSinceStartup; EditorApplication.update += Tick; Undo.undoRedoPerformed += UndoChanged; }
        private void OnDisable() { EditorApplication.update -= Tick; Undo.undoRedoPerformed -= UndoChanged; preview?.Dispose(); }
        private void UndoChanged() { preview?.InvalidateEffects(); Repaint(); }
        private void Tick()
        {
            double now = EditorApplication.timeSinceStartup;
            if (playing && action != null)
            {
                time += (float)(now - lastTick) * speed;
                if (time >= action.duration) { time = loop ? Mathf.Repeat(time, Mathf.Max(0.01f, action.duration)) : action.duration; if (!loop) playing = false; }
                Repaint();
            }
            lastTick = now;
        }
        private void OnGUI()
        {
            EditorGUILayout.BeginHorizontal(EditorStyles.toolbar);
            EditorGUI.BeginChangeCheck(); action = (ActionDefinition)EditorGUILayout.ObjectField(action, typeof(ActionDefinition), false);
            if (EditorGUI.EndChangeCheck()) { selectedCue = selectedWindow = -1; time = 0; preview.InvalidateEffects(); }
            using (new EditorGUI.DisabledScope(EditorApplication.isPlaying))
                if (GUILayout.Button("Save", EditorStyles.toolbarButton, GUILayout.Width(50)) && action != null) AssetDatabase.SaveAssetIfDirty(action);
            EditorGUILayout.EndHorizontal();
            if (action == null) { EditorGUILayout.HelpBox("Select an ActionDefinition from the character workbench, or create one through Assets > Create > MY Project > Animation. Windows are seconds on the gameplay clock; the animation time curve only maps the displayed pose.", MessageType.Info); return; }
            model = (GameObject)EditorGUILayout.ObjectField("Preview model (isolated copy)", model, typeof(GameObject), false);
            EditorGUILayout.BeginHorizontal();
            playing = GUILayout.Toggle(playing, playing ? "Pause" : "Play", "Button", GUILayout.Width(60));
            if (GUILayout.Button("< frame", GUILayout.Width(65))) { playing = false; time = Mathf.Max(0, time - 1 / Mathf.Max(1, frameRate)); }
            if (GUILayout.Button("frame >", GUILayout.Width(65))) { playing = false; time = Mathf.Min(action.duration, time + 1 / Mathf.Max(1, frameRate)); }
            loop = GUILayout.Toggle(loop, "Loop", GUILayout.Width(50)); snap = GUILayout.Toggle(snap, "Snap", GUILayout.Width(50));
            frameRate = Mathf.Clamp(EditorGUILayout.FloatField(frameRate, GUILayout.Width(45)), 1, 240); GUILayout.Label("fps", GUILayout.Width(24));
            speed = EditorGUILayout.Slider(speed, 0.05f, 2); EditorGUILayout.EndHorizontal();
            time = EditorGUILayout.Slider("Time (seconds)", time, 0, Mathf.Max(0.01f, action.duration));
            preview.Draw(GUILayoutUtility.GetRect(200, Mathf.Clamp(position.height * 0.32f, 160, 340), GUILayout.ExpandWidth(true)), model, action.clip,
                action.clip != null ? action.NormalizedTime(time) * action.clip.length : 0, action, time);
            EditorGUILayout.BeginHorizontal(); preview.pinRoot = GUILayout.Toggle(preview.pinRoot, "Pin model root"); preview.showEffects = GUILayout.Toggle(preview.showEffects, "VFX (particles / meshes)"); preview.showShapes = GUILayout.Toggle(preview.showShapes, "Hit volumes"); EditorGUILayout.EndHorizontal();
            if (EditorApplication.isPlaying) EditorGUILayout.HelpBox("Authoring locked during Play Mode. Pose preview is isolated; SFX and camera cues are evaluated in the lab scene, not while scrubbing.", MessageType.Info);
            scroll = EditorGUILayout.BeginScrollView(scroll);
            EditorGUILayout.BeginHorizontal(); zoom = EditorGUILayout.Slider("Timeline zoom", zoom, 1, 8); EditorGUILayout.EndHorizontal();
            float visible = Mathf.Max(0.01f, action.duration) / zoom;
            timelineOffset = EditorGUILayout.Slider("View offset", timelineOffset, 0, Mathf.Max(0, action.duration - visible));
            DrawTimeline(visible);
            using (new EditorGUI.DisabledScope(EditorApplication.isPlaying))
            {
                DrawAddControls();
                var so = new SerializedObject(action); so.Update();
                EditorGUI.BeginChangeCheck();
                if (selectedWindow >= 0 && selectedWindow < action.windows.Count)
                {
                    EditorGUILayout.LabelField("Selected gameplay window", EditorStyles.boldLabel);
                    EditorGUILayout.PropertyField(so.FindProperty("windows").GetArrayElementAtIndex(selectedWindow), true);
                    if (action.windows[selectedWindow].kind == WindowKind.Hitbox && GUILayout.Button("Add hit shape for this window"))
                    {
                        so.ApplyModifiedProperties(); Undo.RecordObject(action, "Add hit shape"); action.hitShapes.Add(new HitShape { windowId = action.windows[selectedWindow].id }); EditorUtility.SetDirty(action); so.Update();
                    }
                }
                if (selectedCue >= 0 && selectedCue < action.cues.Count)
                {
                    EditorGUILayout.LabelField("Selected presentation cue", EditorStyles.boldLabel);
                    EditorGUILayout.PropertyField(so.FindProperty("cues").GetArrayElementAtIndex(selectedCue), true);
                }
                EditorGUILayout.Space(); EditorGUILayout.LabelField("Action / phase / pose mapping", EditorStyles.boldLabel);
                foreach (string name in new[] { "id", "kind", "clip", "animatorState", "animatorAlternateState", "animationTimeParameter", "alternateTimeParameter", "duration", "activeStart", "recoveryStart", "blendIn", "blendOut", "hold", "onRelease", "movement", "inputMovementScale", "turnScale", "rootMotionScale", "applyRootRotation", "animationTime", "footIK", "nextLight", "nextHeavy", "hitShapes", "notes", "ruleIds" })
                    EditorGUILayout.PropertyField(so.FindProperty(name), true);
                EditorGUILayout.PropertyField(so.FindProperty("rootMotion").FindPropertyRelative("vertical"), new GUIContent("动画接管垂直位移"));
                if (EditorGUI.EndChangeCheck()) { so.ApplyModifiedProperties(); preview.InvalidateEffects(); } else so.ApplyModifiedProperties();
                EditorGUILayout.HelpBox("新播放器：Movement=RootMotion 控制启用，Root Motion Scale / Apply Root Rotation 控制缩放与旋转；Root Motion 内只使用轨迹与 Vertical。重力跳跃仍由 Motor 负责。", MessageType.Info);
                EditorGUILayout.HelpBox(RootMotionBaker.Status(new RootMotionSettings { enabled = action.movement == MovementAuthority.RootMotion, track = action.rootMotion?.track }, model, action.clip), MessageType.Info);
                RootMotionBaker.DrawTrajectory(action.rootMotion?.track, action.NormalizedTime(time));
                if (GUILayout.Button("提取动作根轨迹（不改源动画）"))
                {
                    try
                    {
                        AnimationBindingTools.RequireLocalDestination(AssetDatabase.GetAssetPath(action), model, action.clip);
                        var track = RootMotionBaker.Bake(model, action.clip);
                        Undo.RecordObject(action, "Extract action root trajectory");
                        if (action.rootMotion == null) action.rootMotion = new RootMotionSettings();
                        action.rootMotion.track = track; action.rootMotion.enabled = true;
                        EditorUtility.SetDirty(action);
                    }
                    catch (Exception error) { Debug.LogWarning(error.Message); }
                }
            }
            foreach (string issue in action.Validate()) EditorGUILayout.HelpBox(issue, MessageType.Warning);
            EditorGUILayout.HelpBox("Orange volumes only visualize authored hit shapes. Actual collision results, damage, resource payment and counter confirmation belong to the combat adapter. Script-driven effects, sub-emitter chains, SFX and camera motion need Play Mode acceptance.", MessageType.Info);
            EditorGUILayout.EndScrollView();
        }
        private void DrawAddControls()
        {
            EditorGUILayout.BeginHorizontal(); newWindow = (WindowKind)EditorGUILayout.EnumPopup(newWindow);
            if (GUILayout.Button("+ Window at cursor"))
            {
                Undo.RecordObject(action, "Add action window");
                float start = Mathf.Min(time, Mathf.Max(0, action.duration - 1 / frameRate));
                action.windows.Add(new ActionWindow { kind = newWindow, id = newWindow + "_" + Guid.NewGuid().ToString("N").Substring(0, 6), start = start, end = Mathf.Min(action.duration, start + Mathf.Max(0.1f, 1 / frameRate)) });
                selectedWindow = action.windows.Count - 1; selectedCue = -1; EditorUtility.SetDirty(action);
            }
            newCue = (CueKind)EditorGUILayout.EnumPopup(newCue);
            if (GUILayout.Button("+ Cue"))
            {
                Undo.RecordObject(action, "Add action cue");
                action.cues.Add(new ActionCue { kind = newCue, id = newCue.ToString(), time = Mathf.Clamp(time, 0, Mathf.Max(0, action.duration - 1 / frameRate)) });
                selectedCue = action.cues.Count - 1; selectedWindow = -1; EditorUtility.SetDirty(action);
            }
            using (new EditorGUI.DisabledScope(selectedWindow < 0 && selectedCue < 0))
                if (GUILayout.Button("Delete selected"))
                {
                    Undo.RecordObject(action, "Delete action item");
                    if (selectedWindow >= 0 && selectedWindow < action.windows.Count) action.windows.RemoveAt(selectedWindow);
                    if (selectedCue >= 0 && selectedCue < action.cues.Count) action.cues.RemoveAt(selectedCue);
                    selectedCue = selectedWindow = -1; EditorUtility.SetDirty(action); preview.InvalidateEffects();
                }
            EditorGUILayout.EndHorizontal();
        }
        private void DrawTimeline(float visible)
        {
            int windowRows = Enum.GetValues(typeof(WindowKind)).Length;
            int cueRows = Enum.GetValues(typeof(CueKind)).Length;
            Rect rect = GUILayoutUtility.GetRect(300, (windowRows + cueRows + 3) * RowHeight, GUILayout.ExpandWidth(true));
            var grid = new Rect(rect.x + LabelWidth, rect.y, Mathf.Max(20, rect.width - LabelWidth), rect.height);
            float X(float seconds) => grid.x + (seconds - timelineOffset) / visible * grid.width;
            float T(float x) => Mathf.Clamp(timelineOffset + (x - grid.x) / grid.width * visible, 0, action.duration);
            EditorGUI.DrawRect(rect, new Color(0.11f, 0.12f, 0.14f));
            for (int i = 0; i < 11; i++)
            {
                float x = grid.x + grid.width * i / 10;
                EditorGUI.DrawRect(new Rect(x, grid.y, 1, grid.height), new Color(0.23f, 0.25f, 0.28f));
                GUI.Label(new Rect(x + 2, grid.y, 65, RowHeight), (timelineOffset + visible * i / 10).ToString("F2"), EditorStyles.miniLabel);
            }
            GUI.Label(new Rect(rect.x + 4, rect.y, LabelWidth, RowHeight), "Scrub / drag / resize");
            GUI.Label(new Rect(rect.x + 4, rect.y + RowHeight, LabelWidth, RowHeight), "Animation pose map");
            GUI.Label(new Rect(rect.x + 4, rect.y + RowHeight * 2, LabelWidth, RowHeight), "Startup / active / recovery");
            for (int i = 0; i < 3; i++)
            {
                float start = i == 0 ? 0 : i == 1 ? action.activeStart : action.recoveryStart;
                float end = i == 0 ? action.activeStart : i == 1 ? action.recoveryStart : action.duration;
                var bar = Span(X(start), X(end), rect.y + RowHeight * 2 + 3, grid);
                EditorGUI.DrawRect(bar, i == 0 ? new Color(0.65f, 0.49f, 0.18f) : i == 1 ? new Color(0.75f, 0.22f, 0.17f) : new Color(0.2f, 0.48f, 0.65f));
            }
            Handles.BeginGUI(); Handles.color = Color.cyan;
            for (int i = 1; i <= 80; i++)
            {
                float a = timelineOffset + visible * (i - 1) / 80, b = timelineOffset + visible * i / 80;
                Handles.DrawLine(new Vector3(X(a), rect.y + RowHeight * (2 - action.NormalizedTime(a))), new Vector3(X(b), rect.y + RowHeight * (2 - action.NormalizedTime(b))));
            }
            Handles.EndGUI();
            for (int i = 0; i < windowRows + cueRows; i++)
            {
                float y = rect.y + (i + 3) * RowHeight;
                GUI.Label(new Rect(rect.x + 4, y, LabelWidth, RowHeight), i < windowRows ? ((WindowKind)i).ToString() : ((CueKind)(i - windowRows)).ToString(), EditorStyles.miniLabel);
                EditorGUI.DrawRect(new Rect(grid.x, y, grid.width, 1), new Color(0.2f, 0.22f, 0.25f));
            }
            var e = Event.current; int control = GUIUtility.GetControlID(FocusType.Passive);
            bool down = e.type == EventType.MouseDown && e.button == 0;
            bool selected = false;
            for (int i = 0; i < action.windows.Count; i++)
            {
                var w = action.windows[i]; if (w == null) continue;
                var bar = Span(X(w.start), X(w.end), rect.y + ((int)w.kind + 3) * RowHeight + 3, grid);
                EditorGUI.DrawRect(bar, i == selectedWindow ? new Color(0.3f, 0.85f, 0.65f) : new Color(0.2f, 0.49f, 0.4f));
                GUI.Label(bar, w.id, EditorStyles.miniLabel);
                if (down && bar.Contains(e.mousePosition) && !EditorApplication.isPlaying)
                {
                    selectedWindow = i; selectedCue = -1; selected = true;
                    dragMode = 1; dragMouse = T(e.mousePosition.x); dragStart = w.start; dragEnd = w.end;
                    dragEdge = Mathf.Abs(e.mousePosition.x - X(w.start)) < 7 ? -1 : Mathf.Abs(e.mousePosition.x - X(w.end)) < 7 ? 1 : 0;
                    Undo.RecordObject(action, "Move / resize gameplay window");
                }
            }
            for (int i = 0; i < action.cues.Count; i++)
            {
                var c = action.cues[i]; if (c == null || c.time < timelineOffset || c.time > timelineOffset + visible) continue;
                var marker = new Rect(X(c.time) - 5, rect.y + (3 + windowRows + (int)c.kind) * RowHeight + 3, 10, RowHeight - 6);
                EditorGUI.DrawRect(marker, i == selectedCue ? Color.yellow : new Color(0.8f, 0.5f, 0.25f));
                GUI.Label(new Rect(marker.x + 11, marker.y, 80, RowHeight), c.id, EditorStyles.miniLabel);
                if (down && marker.Contains(e.mousePosition) && !EditorApplication.isPlaying)
                {
                    selectedCue = i; selectedWindow = -1; selected = true; dragMode = 2;
                    Undo.RecordObject(action, "Move presentation cue");
                }
            }
            if (down && grid.Contains(e.mousePosition))
            {
                if (!selected) { dragMode = 3; playing = false; time = Quantize(T(e.mousePosition.x)); }
                GUIUtility.hotControl = control; e.Use();
            }
            if (GUIUtility.hotControl == control && e.type == EventType.MouseDrag)
            {
                float t = Quantize(T(e.mousePosition.x));
                if (dragMode == 1 && selectedWindow >= 0 && selectedWindow < action.windows.Count)
                {
                    var w = action.windows[selectedWindow]; float step = Mathf.Min(action.duration, 1 / frameRate);
                    if (dragEdge == -1) w.start = Mathf.Clamp(t, 0, w.end - step);
                    else if (dragEdge == 1) w.end = Mathf.Clamp(t, w.start + step, action.duration);
                    else { float length = dragEnd - dragStart; w.start = Mathf.Clamp(Quantize(dragStart + t - dragMouse), 0, Mathf.Max(0, action.duration - length)); w.end = w.start + length; }
                    EditorUtility.SetDirty(action);
                }
                else if (dragMode == 2 && selectedCue >= 0 && selectedCue < action.cues.Count) { action.cues[selectedCue].time = Mathf.Min(t, Mathf.Max(0, action.duration - 1 / frameRate)); EditorUtility.SetDirty(action); }
                else if (dragMode == 3) time = t;
                preview.InvalidateEffects(); Repaint(); e.Use();
            }
            if (GUIUtility.hotControl == control && e.type == EventType.MouseUp) { GUIUtility.hotControl = 0; dragMode = 0; e.Use(); }
            if (time >= timelineOffset && time <= timelineOffset + visible) EditorGUI.DrawRect(new Rect(X(time), grid.y, 2, grid.height), Color.white);
        }
        private float Quantize(float value) => Mathf.Clamp(snap ? Mathf.Round(value * frameRate) / frameRate : value, 0, action.duration);
        private static Rect Span(float start, float end, float y, Rect grid)
        {
            float x = Mathf.Clamp(start, grid.x, grid.xMax); float right = Mathf.Clamp(end, grid.x, grid.xMax);
            return new Rect(x, y, Mathf.Max(0, right - x), RowHeight - 6);
        }
    }
}
