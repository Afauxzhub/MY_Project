using System;
using System.Linq;
using Afauxzhub.Project.Animation;
using UnityEditor;
using UnityEngine;
using Object = UnityEngine.Object;

namespace Afauxzhub.Project.Editor.Animation
{
    public sealed partial class MotionWorkbench : EditorWindow
    {
        [SerializeField] private MotionLibrary source, draft;
        [SerializeField] private string baseline, draftBaseline, relaxedBaseline, readyBaseline;
        [SerializeField] private string sourceRelaxedBaseline, sourceReadyBaseline;
        [SerializeField] private int tab, selectedEntry, selectedRecipe, fromIndex, toIndex = 3;
        [SerializeField] private string fromEntryId, toEntryId;
        [SerializeField] private WeaponStance stance;
        [SerializeField] private float previewTime, lead = 0.8f;
        private Vector2 scroll;
        private string search = "", message = "";
        private MotionTransitionPreview preview;
        private bool playing;
        private double lastUpdate;
        private double lastLiveRepaint;
        private int dragging;
        private bool modeTransition;
        [SerializeField] private bool previewSelectedOverride;
        [SerializeField] private MotionGait previewGait = MotionGait.Run;
        [SerializeField] private MotionDirection previewDirection = MotionDirection.Forward;
        public MotionLibrary Draft => draft;
        public MotionLibrary Source => source;
        public bool HasDraftChanges => draft != null && (EditorJsonUtility.ToJson(draft) != draftBaseline
            || Json(draft.relaxedMovement) != relaxedBaseline || Json(draft.readyMovement) != readyBaseline);

        [MenuItem("Tools/MY Project/Animation/Motion Workbench (No Wires)")]
        public static void Open() => GetWindow<MotionWorkbench>("动作工作台 · 无连线").Show();
        public static void Open(MotionLibrary library)
        {
            var window = GetWindow<MotionWorkbench>("动作工作台 · 无连线");
            if (window.source != library && window.CanDiscard()) window.Load(library);
            window.Show();
        }
        private static string Json(Object value) => value != null ? EditorJsonUtility.ToJson(value) : "";
        private void OnEnable()
        {
            minSize = new Vector2(920, 650); preview = new MotionTransitionPreview();
            EditorApplication.update += Tick; Undo.undoRedoPerformed += Repaint;
            EditorApplication.playModeStateChanged += PlayStateChanged;
            AssemblyReloadEvents.beforeAssemblyReload += ReleasePreview;
            lastUpdate = EditorApplication.timeSinceStartup;
            if (source != null && draft == null) Load(source);
        }
        private void OnDisable() { EditorApplication.update -= Tick; Undo.undoRedoPerformed -= Repaint; EditorApplication.playModeStateChanged -= PlayStateChanged; AssemblyReloadEvents.beforeAssemblyReload -= ReleasePreview; ReleasePreview(); }
        private void ReleasePreview() { preview?.Dispose(); preview = null; }
        private void PlayStateChanged(PlayModeStateChange state)
        {
            modeTransition = state == PlayModeStateChange.ExitingEditMode || state == PlayModeStateChange.ExitingPlayMode;
            if (modeTransition) ReleasePreview();
        }
        private void OnDestroy() => DestroyDraft();
        private void Tick()
        {
            double now = EditorApplication.timeSinceStartup;
            if (playing) { previewTime = Mathf.Repeat(previewTime + (float)Math.Min(0.1, now - lastUpdate), 4); Repaint(); }
            else if (EditorApplication.isPlaying && now - lastLiveRepaint >= 0.1) { lastLiveRepaint = now; Repaint(); }
            lastUpdate = now;
            hasUnsavedChanges = HasDraftChanges;
            saveChangesMessage = "动作工作台有未保存草稿。保存会写入所选动作库；放弃只丢弃草稿。";
        }
        public override void SaveChanges() { if (SaveDraft()) base.SaveChanges(); }
        public override void DiscardChanges() { Load(source); base.DiscardChanges(); }
        private bool CanDiscard() => !HasDraftChanges || EditorUtility.DisplayDialog("未保存的动作配置", "切换将丢弃工作台草稿；源资产不会改变。", "丢弃草稿", "返回");
        private void DestroyDraft()
        {
            if (draft == null) return;
            if (draft.relaxedMovement != null) DestroyImmediate(draft.relaxedMovement);
            if (draft.readyMovement != null) DestroyImmediate(draft.readyMovement);
            DestroyImmediate(draft); draft = null;
        }
        public void Load(MotionLibrary library)
        {
            candidates.Clear();
            coverageSnapshot = null;
            DestroyDraft(); source = library;
            if (source == null) return;
            baseline = Json(source); sourceRelaxedBaseline = Json(source.relaxedMovement); sourceReadyBaseline = Json(source.readyMovement);
            draft = Instantiate(source); draft.hideFlags = HideFlags.HideAndDontSave;
            if (source.relaxedMovement != null) { draft.relaxedMovement = Instantiate(source.relaxedMovement); draft.relaxedMovement.hideFlags = HideFlags.HideAndDontSave; }
            if (source.readyMovement != null) { draft.readyMovement = Instantiate(source.readyMovement); draft.readyMovement.hideFlags = HideFlags.HideAndDontSave; }
            MarkBaseline(); message = "已加载草稿；修改后可预览、应用到 Play 或显式保存。";
            var assigned = draft.entries.Where(e => e.clip != null && e.enabled).ToArray();
            fromIndex = Mathf.Max(0, Array.FindIndex(assigned, e => e.slot == MotionSlot.Idle));
            toIndex = Mathf.Max(0, Array.FindIndex(assigned, e => e.slot == MotionSlot.Run));
            fromEntryId = assigned.Length > 0 ? assigned[fromIndex].id : "";
            toEntryId = assigned.Length > 0 ? assigned[toIndex].id : "";
        }
        private void MarkBaseline()
        { draftBaseline = Json(draft); relaxedBaseline = Json(draft.relaxedMovement); readyBaseline = Json(draft.readyMovement); }
        public bool SaveDraft()
        {
            if (source == null || draft == null) return false;
            if (Json(source) != baseline || Json(source.relaxedMovement) != sourceRelaxedBaseline || Json(source.readyMovement) != sourceReadyBaseline)
            { message = "源资产已被其他编辑修改；拒绝覆盖。请保留草稿并先核对差异。"; return false; }
            string[] errors = draft.Validate().ToArray();
            if (errors.Length > 0) { message = "不能保存非法配置：" + errors[0]; return false; }
            try
            {
                RootMotionBaker.RequireCurrent(draft);
                MotionAuthoringTools.GuardDestination(AssetDatabase.GetAssetPath(source), draft.model, draft.templates);
                foreach (var entry in draft.entries) if (entry?.clip != null) AnimationBindingTools.RequireLocalDestination(AssetDatabase.GetAssetPath(source), entry.clip, entry.rootMotion?.track?.model);
                var relaxed = source.relaxedMovement; var ready = source.readyMovement;
                Undo.RecordObject(source, "Save motion library draft");
                if (relaxed != null) { Undo.RecordObject(relaxed, "Save relaxed tuning"); string name = relaxed.name; EditorUtility.CopySerialized(draft.relaxedMovement, relaxed); relaxed.name = name; relaxed.hideFlags = HideFlags.None; EditorUtility.SetDirty(relaxed); }
                if (ready != null) { Undo.RecordObject(ready, "Save ready tuning"); string name = ready.name; EditorUtility.CopySerialized(draft.readyMovement, ready); ready.name = name; ready.hideFlags = HideFlags.None; EditorUtility.SetDirty(ready); }
                string originalName = source.name;
                EditorUtility.CopySerialized(draft, source); source.name = originalName; source.hideFlags = HideFlags.None;
                source.relaxedMovement = relaxed; source.readyMovement = ready;
                EditorUtility.SetDirty(source); AssetDatabase.SaveAssetIfDirty(source);
                baseline = Json(source); sourceRelaxedBaseline = Json(source.relaxedMovement); sourceReadyBaseline = Json(source.readyMovement); MarkBaseline(); hasUnsavedChanges = false;
                message = "已保存配置差异（可 Undo）。源动画、旧 Controller 和场景未写入。"; return true;
            }
            catch (Exception error) { message = error.Message; return false; }
        }
        public bool ApplyToPlay()
        {
            var players = Object.FindObjectsByType<MotionLibraryPlayer>(FindObjectsSortMode.None).Where(p => p.library == source).ToArray();
            if (!Application.isPlaying || players.Length != 1) { message = "Play 中需要恰好一个使用所选库的角色。"; return false; }
            if (draft.Validate().Any()) { message = "草稿有配置错误；请先看覆盖/诊断。"; return false; }
            try { RootMotionBaker.RequireCurrent(draft); } catch (Exception error) { message = error.Message; return false; }
            players[0].ApplyDraft(draft); message = "已应用到本次 Play 副本，尚未写源资产。"; return true;
        }
        private void OnGUI()
        {
            using (new EditorGUILayout.HorizontalScope(EditorStyles.toolbar))
            {
                var chosen = (MotionLibrary)EditorGUILayout.ObjectField(source, typeof(MotionLibrary), false, GUILayout.MinWidth(200));
                if (chosen != source && CanDiscard()) Load(chosen);
                using (new EditorGUI.DisabledScope(source == null))
                {
                    if (GUILayout.Button("保存差异", EditorStyles.toolbarButton, GUILayout.Width(75))) SaveDraft();
                    if (GUILayout.Button("丢弃草稿", EditorStyles.toolbarButton, GUILayout.Width(75)) && CanDiscard()) Load(source);
                    if (GUILayout.Button("应用到 Play", EditorStyles.toolbarButton, GUILayout.Width(90))) ApplyToPlay();
                }
            }
            if (draft == null) { EditorGUILayout.HelpBox("选择 MotionLibrary；或用 New Character Lab (No Wires) 从模型新建。无需 Animator Controller。", MessageType.Info); if (GUILayout.Button("新建独立角色测试配置")) MotionCharacterWizard.Open(); return; }
            EditorGUILayout.LabelField("无 Animator 连线 · 草稿编辑 / 显式保存" + (HasDraftChanges ? "  ● 有未保存修改" : ""), EditorStyles.boldLabel);
            tab = GUILayout.Toolbar(tab, new[] { "动作库", "衔接配方", "移动参数", "运行 / 覆盖", "批量填槽", "使用帮助" });
            using (new EditorGUILayout.HorizontalScope())
            {
                using (new EditorGUILayout.VerticalScope(GUILayout.Width(Mathf.Clamp(position.width * 0.45f, 370, 560))))
                {
                    scroll = EditorGUILayout.BeginScrollView(scroll);
                    if (tab == 0) DrawEntries(); else if (tab == 1) DrawRecipes(); else if (tab == 2) DrawTuning(); else if (tab == 3) DrawDiagnostics(); else if (tab == 4) DrawBatch(); else DrawHelp();
                    EditorGUILayout.EndScrollView();
                }
                using (new EditorGUILayout.VerticalScope()) DrawPreview();
            }
            EditorGUILayout.HelpBox(message, MessageType.Info);
        }
        private void DrawEntries()
        {
            stance = (WeaponStance)EditorGUILayout.EnumPopup("动作套", stance);
            search = EditorGUILayout.TextField("筛选", search);
            var choices = draft.entries.Select((entry, index) => new { entry, index }).Where(x => x.entry != null && x.entry.stance == stance && Label(x.entry).IndexOf(search, StringComparison.OrdinalIgnoreCase) >= 0).ToArray();
            EditorGUILayout.LabelField($"本筛选 {choices.Length} 项 / 已赋 {choices.Count(x => x.entry.clip != null)}");
            using (new EditorGUILayout.VerticalScope(EditorStyles.helpBox, GUILayout.MaxHeight(160)))
                foreach (var item in choices.Take(8))
                    if (GUILayout.Toggle(item.index == selectedEntry, Label(item.entry), "Button")) selectedEntry = item.index;
            if (choices.Length > 8) EditorGUILayout.HelpBox("用筛选定位更多槽位，或从下方完整下拉选择。", MessageType.None);
            if (draft.entries.Count > 0) selectedEntry = EditorGUILayout.Popup("编辑槽", Mathf.Clamp(selectedEntry, 0, draft.entries.Count - 1), draft.entries.Select(Label).ToArray());
            var so = new SerializedObject(draft); so.Update();
            EditorGUILayout.PropertyField(so.FindProperty("model"), new GUIContent("预览模型 / 绑定"));
            if (draft.entries.Count > 0)
            {
                var property = so.FindProperty("entries").GetArrayElementAtIndex(selectedEntry);
                foreach (string field in new[] { "stance", "mode", "slot", "gait", "direction", "clip", "enabled", "rootMotion", "speed", "inPoint", "outPoint", "phaseOffset", "stageSeconds", "minimumSpeed", "maximumSpeed", "minimumAngle", "maximumAngle", "referenceSpeed", "matchPlaybackToSpeed", "contactAuthored", "leftContact", "rightContact", "matchName", "optional", "note" }) EditorGUILayout.PropertyField(property.FindPropertyRelative(field), true);
                var entry = draft.entries[selectedEntry];
                EditorGUILayout.LabelField("稳定 ID", entry.id, EditorStyles.miniLabel);
                if (entry.clip != null && GUILayout.Button("检查模型绑定覆盖")) message = AnimationBindingTools.Coverage(draft.model, entry.clip);
            }
            so.ApplyModifiedProperties();
            if (draft.entries.Count > 0)
            {
                var entry = draft.entries[selectedEntry];
                DrawEntryReview(entry);
                EditorGUILayout.HelpBox(RootMotionBaker.Status(entry.rootMotion, draft.model, entry.clip), MessageType.Info);
                RootMotionBaker.DrawTrajectory(entry.rootMotion?.track, entry.inPoint);
                if (GUILayout.Button("提取所选动画根轨迹（仅草稿）"))
                {
                    try
                    {
                        var track = RootMotionBaker.Bake(draft.model, entry.clip);
                        Undo.RecordObject(draft, "Extract root trajectory");
                        if (entry.rootMotion == null) entry.rootMotion = new RootMotionSettings();
                        entry.rootMotion.track = track; entry.rootMotion.enabled = true;
                        message = "已提取根轨迹；原 Clip 未修改。可 Undo，应用到 Play 或保存差异。";
                    }
                    catch (Exception error) { message = error.Message; }
                }
            }
            using (new EditorGUILayout.HorizontalScope())
            {
                if (GUILayout.Button("新增槽 / 变体")) { Undo.RecordObject(draft, "Add motion entry"); draft.entries.Add(new MotionEntry { stance = stance, enabled = false, note = "Set selectors, assign a clip and enable. Only one enabled entry per selector." }); selectedEntry = draft.entries.Count - 1; }
                if (draft.entries.Count > 0 && GUILayout.Button("清空所选引用"))
                {
                    var entry = draft.entries[selectedEntry];
                    message = $"清空 {Label(entry)}；影响所有使用该槽的配方，桥接直接引用 {draft.overrides.Count(r => r.bridgeEntry == entry.id)} 项。源 Clip 未删除，可 Undo。";
                    Undo.RecordObject(draft, "Clear motion reference"); entry.clip = null;
                }
            }
            if (GUILayout.Button("补齐新版本动作槽（仅草稿，保留已有槽）")) { Undo.RecordObject(draft, "Add missing motion slots"); message = "新增 " + MotionCatalog.AddMissing(draft) + " 个槽"; candidates.Clear(); }
        }
        private static string Label(MotionEntry entry) => entry == null ? "<null>" : MotionCatalog.Selector(entry) + "  " + (entry.clip == null ? "[缺失]" : entry.clip.name);
        private void DrawRecipes()
        {
            EditorGUILayout.HelpBox("公共模板自动继承；只为例外添加覆盖。优先级相同时按条件数量排序，相同排名冲突会报警。", MessageType.Info);
            if (draft.templates != null) foreach (var r in draft.templates.recipes) EditorGUILayout.LabelField($"继承：{r.label}  {r.from} → {r.to}  {r.blendSeconds:F2}s", EditorStyles.miniLabel);
            if (draft.overrides.Count > 0)
            {
                selectedRecipe = EditorGUILayout.Popup("角色覆盖", Mathf.Clamp(selectedRecipe, 0, draft.overrides.Count - 1), draft.overrides.Select(r => r.label).ToArray());
                var so = new SerializedObject(draft); so.Update();
                var property = so.FindProperty("overrides").GetArrayElementAtIndex(selectedRecipe);
                foreach (string field in new[] { "label", "enabled", "from", "to", "fromMode", "toMode", "stance", "gait", "direction", "priority", "blendSeconds", "weight", "preserveCyclePhase", "targetPhase", "interruptAfter", "bridgeSeconds", "bridgeOutSeconds" }) EditorGUILayout.PropertyField(property.FindPropertyRelative(field), true);
                var entries = draft.entries.Where(e => e.clip != null).ToArray();
                string bridgeId = property.FindPropertyRelative("bridgeEntry").stringValue;
                int current = Array.FindIndex(entries, e => e.id == bridgeId) + 1;
                int next = EditorGUILayout.Popup("可选桥接动画", current, new[] { "无 — 直接混合" }.Concat(entries.Select(Label)).ToArray());
                if (next != current) property.FindPropertyRelative("bridgeEntry").stringValue = next == 0 ? "" : entries[next - 1].id;
                so.ApplyModifiedProperties();
            }
            using (new EditorGUILayout.HorizontalScope())
            {
                if (GUILayout.Button("添加覆盖")) { Undo.RecordObject(draft, "Add recipe"); draft.overrides.Add(new MotionRecipe { enabled = false }); selectedRecipe = draft.overrides.Count - 1; }
                if (draft.overrides.Count > 0 && GUILayout.Button("移除覆盖 / 恢复继承")) { Undo.RecordObject(draft, "Remove recipe override"); draft.overrides.RemoveAt(selectedRecipe); selectedRecipe = 0; }
            }
        }
        private void DrawTuning()
        {
            var so = new SerializedObject(draft); so.Update();
            foreach (string field in new[] { "defaultBlend", "jumpKey", "jumpHeight", "takeoffSeconds", "airControl", "apexSpeed", "idleVariation", "idleVariationInterval", "minimumPlaybackScale", "maximumPlaybackScale" }) EditorGUILayout.PropertyField(so.FindProperty(field));
            so.ApplyModifiedProperties(); stance = (WeaponStance)EditorGUILayout.EnumPopup("动作套参数", stance);
            var movement = draft.Movement(stance); if (movement == null) return;
            var tuning = new SerializedObject(movement); tuning.Update(); var iterator = tuning.GetIterator(); bool children = true;
            while (iterator.NextVisible(children)) { children = false; if (iterator.name != "m_Script") EditorGUILayout.PropertyField(iterator, true); }
            tuning.ApplyModifiedProperties();
        }
        private void DrawDiagnostics()
        {
            foreach (var error in draft.Validate()) EditorGUILayout.HelpBox(error, MessageType.Error);
            EditorGUILayout.LabelField($"动作库：{draft.entries.Count(e => e.clip != null)} / {draft.entries.Count} 已赋");
            foreach (WeaponStance set in Enum.GetValues(typeof(WeaponStance))) EditorGUILayout.LabelField($"{set}: 缺失 {draft.entries.Count(e => e.stance == set && e.clip == null)}（含可选覆盖槽）");
            EditorGUILayout.HelpBox("资源为空不等于程序未接通；回退动作不等于真实表现通过。动态锁脚 / 脚滑修正排在 MOVE-010。", MessageType.Warning);
            var active = Object.FindObjectsByType<MotionLibraryPlayer>(FindObjectsSortMode.None).FirstOrDefault(p => p.library == source);
            if (Application.isPlaying && active != null)
            {
                EditorGUILayout.LabelField("Phase", active.driver.Phase.ToString());
                EditorGUILayout.LabelField("速度", active.driver.Speed.ToString("F2") + " m/s");
                EditorGUILayout.LabelField("期望 / Motor 实际", active.driver.TargetSpeed.ToString("F2") + " / " + new Vector2(active.driver.motor.Velocity.x, active.driver.motor.Velocity.z).magnitude.ToString("F2") + " m/s");
                EditorGUILayout.LabelField("位移所有者", active.driver.MotionOwner);
                var rootFrame = active.RootFrame;
                EditorGUILayout.LabelField("根位移请求 / 转角", rootFrame.localDelta.ToString("F3") + " / " + rootFrame.yaw.ToString("F2"));
                EditorGUILayout.LabelField("根权重 XZ / Y / 转向", $"{rootFrame.positionWeight:F2} / {rootFrame.verticalWeight:F2} / {rootFrame.rotationWeight:F2}");
                EditorGUILayout.LabelField("模式 / 播放倍率", active.driver.Mode + " / " + active.PlaybackScale.ToString("F2"));
                EditorGUILayout.HelpBox(active.Support.ToString(), MessageType.None);
                EditorGUILayout.HelpBox(active.Decision ?? "", MessageType.None);
                EditorGUILayout.HelpBox(active.Missing ?? "", MessageType.Warning);
                EditorGUILayout.TextArea(active.Player?.Describe() ?? "");
            }
            else EditorGUILayout.HelpBox("在独立 No-Wires 场景进入 Play 后显示运行配方、混合与资源回退。", MessageType.Info);
            if (GUILayout.Button("导出资源覆盖到 Console"))
                Debug.Log(string.Join("\n", draft.entries.Select(e => Label(e) + " | " + e.note)));
            DrawCoverageExport();
            DrawCoverageMatrix();
        }
        // The assigned-only popup changes length/order when clips are filled, cleared or disabled.
        // Keep the selected semantic entry, not its old index in that filtered list.
        internal static int ResolvePreviewIndex(MotionEntry[] entries, string id, int fallback)
        {
            if (entries.Length == 0) return -1;
            int match = string.IsNullOrEmpty(id) ? -1 : Array.FindIndex(entries, e => e.id == id);
            return match >= 0 ? match : Mathf.Clamp(fallback, 0, entries.Length - 1);
        }
        private void DrawPreview()
        {
            if (modeTransition || EditorApplication.isCompiling) { EditorGUILayout.HelpBox("正在切换编辑器状态，预览已释放。", MessageType.Info); return; }
            var entries = draft.entries.Where(e => e.clip != null && e.enabled).ToArray();
            if (entries.Length == 0) { EditorGUILayout.HelpBox("先赋至少一条动画。", MessageType.Info); return; }
            fromIndex = EditorGUILayout.Popup("上一动画", ResolvePreviewIndex(entries, fromEntryId, fromIndex), entries.Select(Label).ToArray());
            toIndex = EditorGUILayout.Popup("下一动画", ResolvePreviewIndex(entries, toEntryId, toIndex), entries.Select(Label).ToArray());
            fromEntryId = entries[fromIndex].id;
            toEntryId = entries[toIndex].id;
            previewSelectedOverride = EditorGUILayout.Toggle("试播所选覆盖（忽略匹配）", previewSelectedOverride);
            using (new EditorGUILayout.HorizontalScope())
            {
                previewGait = (MotionGait)EditorGUILayout.EnumPopup("匹配步态", previewGait);
                previewDirection = (MotionDirection)EditorGUILayout.EnumPopup("匹配方向", previewDirection);
            }
            string resolution;
            previewFromMode = (MotionMode)EditorGUILayout.EnumPopup("源模式", previewFromMode);
            previewToMode = (MotionMode)EditorGUILayout.EnumPopup("目标模式", previewToMode);
            var target = entries[toIndex];
            // An Any entry may serve multiple contexts. Never pretend Any is the live Run/Walk selector.
            MotionRecipe recipe = draft.Resolve(MotionLibraryPlayer.FamilyForSlot(entries[fromIndex].slot), MotionLibraryPlayer.FamilyForSlot(target.slot), target.stance,
                target.gait == MotionGait.Any ? previewGait : target.gait, target.direction == MotionDirection.Any ? previewDirection : target.direction, previewFromMode, previewToMode, out resolution);
            if (previewSelectedOverride)
            { recipe = draft.overrides.Count > 0 ? draft.overrides[Mathf.Clamp(selectedRecipe, 0, draft.overrides.Count - 1)] : null; resolution = "手动试播（不代表运行命中）"; }
            EditorGUILayout.LabelField("预览配方", resolution);
            if (recipe != null && !draft.overrides.Contains(recipe) && GUILayout.Button("复制命中模板为角色覆盖后编辑"))
            {
                Undo.RecordObject(draft, "Override inherited recipe");
                var copy = JsonUtility.FromJson<MotionRecipe>(JsonUtility.ToJson(recipe)); copy.id = Guid.NewGuid().ToString("N");
                draft.overrides.Add(copy); selectedRecipe = draft.overrides.Count - 1; recipe = copy; tab = 1;
            }
            using (new EditorGUILayout.HorizontalScope())
            {
                if (GUILayout.Button(playing ? "暂停" : "播放")) playing = !playing;
                if (GUILayout.Button("◀ 1帧")) { playing = false; previewTime = Mathf.Max(0, previewTime - 1f / 30); }
                if (GUILayout.Button("1帧 ▶")) { playing = false; previewTime = Mathf.Min(4, previewTime + 1f / 30); }
                if (GUILayout.Button("重置")) { previewTime = 0; playing = false; }
            }
            previewTime = EditorGUILayout.Slider("时间 (30fps 步进)", previewTime, 0, 4);
            lead = EditorGUILayout.Slider("源动画预播 (秒)", lead, 0, 2);
            DrawTrim("上一动画裁剪", entries[fromIndex]);
            DrawTrim("下一动画裁剪", entries[toIndex]);
            Rect strip = GUILayoutUtility.GetRect(100, 56, GUILayout.ExpandWidth(true));
            DrawStrip(strip, recipe, recipe == null || draft.overrides.Contains(recipe));
            Rect rect = GUILayoutUtility.GetRect(200, 200, GUILayout.ExpandWidth(true), GUILayout.ExpandHeight(true));
            if (preview == null) preview = new MotionTransitionPreview();
            preview.Draw(rect, draft, entries[fromIndex], entries[toIndex], recipe, previewTime, lead);
            EditorGUILayout.TextArea(preview.DebugText, GUILayout.Height(68));
        }
        private void DrawStrip(Rect rect, MotionRecipe recipe, bool editable)
        {
            float blend = recipe?.blendSeconds ?? draft.defaultBlend;
            EditorGUI.DrawRect(rect, new Color(0.1f, 0.12f, 0.15f));
            EditorGUI.DrawRect(new Rect(rect.x, rect.y + 5, rect.width * Mathf.Clamp01((lead + blend) / 4), 17), new Color(0.2f, 0.5f, 0.75f));
            EditorGUI.DrawRect(new Rect(rect.x + rect.width * lead / 4, rect.y + 27, rect.width * (4 - lead) / 4, 17), new Color(0.25f, 0.65f, 0.42f));
            float handle = rect.x + rect.width * (lead + blend) / 4;
            EditorGUI.DrawRect(new Rect(handle - 3, rect.y, 6, rect.height), Color.yellow);
            GUI.Label(rect, editable ? "  上一动画 / 下一动画     拖黄色线调整融合时长" : "  继承模板只读 · 先复制为角色覆盖再拖动", EditorStyles.whiteMiniLabel);
            var e = Event.current;
            if (editable && e.type == EventType.MouseDown && rect.Contains(e.mousePosition) && Mathf.Abs(e.mousePosition.x - handle) < 12)
            { dragging = GUIUtility.GetControlID(FocusType.Passive); GUIUtility.hotControl = dragging; Undo.RecordObject(draft, "Drag blend overlap"); e.Use(); }
            if (dragging != 0 && e.type == EventType.MouseDrag)
            { float value = Mathf.Clamp((e.mousePosition.x - rect.x) / rect.width * 4 - lead, 0, 2); if (recipe != null) recipe.blendSeconds = value; else draft.defaultBlend = value; e.Use(); Repaint(); }
            if (dragging != 0 && e.type == EventType.MouseUp) { dragging = 0; GUIUtility.hotControl = 0; e.Use(); }
        }
    }
}
