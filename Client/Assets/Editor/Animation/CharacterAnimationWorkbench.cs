using System;
using System.Linq;
using Afauxzhub.Project.Animation;
using UnityEditor;
using UnityEngine;

namespace Afauxzhub.Project.Editor.Animation
{
    public sealed class CharacterAnimationWorkbench : EditorWindow
    {
        [SerializeField] private CharacterAnimationProfile profile;
        [SerializeField] private WeaponStance stance;
        [SerializeField] private MotionSlot selectedSlot;
        [SerializeField] private int tab;
        private Vector2 scroll;
        private AnimationPreview preview;
        private UnityEditor.Editor movementEditor;
        private AnimatedCharacterDriver live;
        private AnimationClip bindingClip;
        private string prefixFrom = "", prefixTo = "", report = "";
        private float previewTime;
        private bool playing;
        [SerializeField] private bool showAllMotionSlots;
        private double lastTime;
        [MenuItem("Tools/MY Project/Animation/Character Workbench")]
        public static void Open() { GetWindow<CharacterAnimationWorkbench>("Character Animation"); }
        public static void Open(CharacterAnimationProfile selected) { var w = GetWindow<CharacterAnimationWorkbench>("Character Animation"); w.profile = selected; w.Show(); }
        private void OnEnable() { minSize = new Vector2(800, 650); preview = new AnimationPreview(); lastTime = EditorApplication.timeSinceStartup; EditorApplication.update += Tick; Undo.undoRedoPerformed += Repaint; }
        private void OnDisable() { EditorApplication.update -= Tick; Undo.undoRedoPerformed -= Repaint; preview?.Dispose(); if (movementEditor != null) DestroyImmediate(movementEditor); }
        private void Tick()
        {
            double now = EditorApplication.timeSinceStartup;
            var clip = profile != null ? profile.Set(stance).Find(selectedSlot)?.clip : null;
            if (playing && clip != null) previewTime = Mathf.Repeat(previewTime + (float)(now - lastTime), Mathf.Max(0.01f, clip.length));
            lastTime = now;
            if (playing || tab == 3) Repaint();
        }
        private void OnGUI()
        {
            EditorGUILayout.BeginHorizontal(EditorStyles.toolbar);
            profile = (CharacterAnimationProfile)EditorGUILayout.ObjectField(profile, typeof(CharacterAnimationProfile), false);
            using (new EditorGUI.DisabledScope(EditorApplication.isPlaying))
                if (GUILayout.Button("New lab profile", EditorStyles.toolbarButton, GUILayout.Width(105))) profile = AnimationLabBuilder.CreateProfileDialog();
            EditorGUILayout.EndHorizontal();
            if (profile == null) { EditorGUILayout.HelpBox("Create a profile, assign two independent movement sets, then generate an editable Animator Controller. No source assets or scenes are changed on opening this window.", MessageType.Info); return; }
            tab = GUILayout.Toolbar(tab, new[] { "Locomotion", "Actions / Graph", "Foot IK / Rig", "Live Debug", "Bindings / Missing" });
            scroll = EditorGUILayout.BeginScrollView(scroll);
            var serialized = new SerializedObject(profile); serialized.Update();
            using (new EditorGUI.DisabledScope(EditorApplication.isPlaying && tab != 3))
            {
                EditorGUILayout.PropertyField(serialized.FindProperty("previewModel"));
                switch (tab)
                {
                    case 0: DrawMotion(serialized); break;
                    case 1: DrawActions(serialized); break;
                    case 2: DrawIK(serialized); break;
                    case 3: DrawLive(); break;
                    case 4: DrawBindings(); break;
                }
                serialized.ApplyModifiedProperties();
            }
            EditorGUILayout.EndScrollView();
        }
        private void DrawMotion(SerializedObject so)
        {
            stance = (WeaponStance)GUILayout.Toolbar((int)stance, new[] { "Sheathed / 收武器", "Drawn / 持武器" });
            EditorGUILayout.HelpBox("Stance and targeting are independent. Missing directional slots keep their states, but cannot demonstrate finished animation quality. Curves and foot contacts are authored outside the source clips.", MessageType.Info);
            var set = so.FindProperty(stance == WeaponStance.Sheathed ? "sheathed" : "drawn");
            EditorGUILayout.PropertyField(set.FindPropertyRelative("movement"));
            selectedSlot = (MotionSlot)EditorGUILayout.EnumPopup("Preview slot", selectedSlot);
            showAllMotionSlots = EditorGUILayout.Foldout(showAllMotionSlots, "Show all slot assignments / missing clips", true);
            var list = set.FindPropertyRelative("motions");
            if (list.arraySize < Enum.GetValues(typeof(MotionSlot)).Length && GUILayout.Button("Add missing slot records"))
            { so.ApplyModifiedProperties(); Undo.RecordObject(profile, "Add motion slots"); profile.EnsureSlots(); EditorUtility.SetDirty(profile); so.Update(); }
            for (int i = 0; i < list.arraySize; i++)
            {
                var item = list.GetArrayElementAtIndex(i); var slot = (MotionSlot)item.FindPropertyRelative("slot").enumValueIndex;
                if (!showAllMotionSlots && slot != selectedSlot) continue;
                var clip = item.FindPropertyRelative("clip");
                EditorGUILayout.BeginHorizontal();
                if (GUILayout.Button(slot.ToString(), GUILayout.Width(150))) { selectedSlot = slot; previewTime = 0; }
                EditorGUILayout.PropertyField(clip, GUIContent.none);
                GUILayout.Label(clip.objectReferenceValue == null ? "MISSING" : "Assigned", GUILayout.Width(70));
                EditorGUILayout.EndHorizontal();
                if (slot == selectedSlot)
                {
                    EditorGUI.indentLevel++;
                    EditorGUILayout.PropertyField(item.FindPropertyRelative("playbackSpeed"));
                    EditorGUILayout.PropertyField(item.FindPropertyRelative("leftContact"), new GUIContent("Left plant (0–1 phase)"));
                    EditorGUILayout.PropertyField(item.FindPropertyRelative("rightContact"), new GUIContent("Right plant (0–1 phase)"));
                    EditorGUILayout.PropertyField(item.FindPropertyRelative("note"));
                    EditorGUI.indentLevel--;
                }
            }
            var chosen = profile.Set(stance).Find(selectedSlot)?.clip;
            EditorGUILayout.BeginHorizontal(); playing = GUILayout.Toggle(playing, "Play preview", "Button", GUILayout.Width(110));
            previewTime = EditorGUILayout.Slider(previewTime, 0, chosen != null ? chosen.length : 1); EditorGUILayout.EndHorizontal();
            preview.Draw(GUILayoutUtility.GetRect(250, 320, GUILayout.ExpandWidth(true)), profile.previewModel, chosen, previewTime);
            EditorGUILayout.LabelField("Movement dynamics / steering curves", EditorStyles.boldLabel);
            var movement = profile.Set(stance).movement;
            if (movement != null) { UnityEditor.Editor.CreateCachedEditor(movement, null, ref movementEditor); movementEditor.OnInspectorGUI(); }
            foreach (string p in new[] { "motionBlend", "stanceBlend", "parameterDamping", "inputBufferSeconds", "locomotionRootMotion" }) EditorGUILayout.PropertyField(so.FindProperty(p));
        }
        private void DrawActions(SerializedObject so)
        {
            EditorGUILayout.PropertyField(so.FindProperty("controller"));
            EditorGUILayout.BeginHorizontal();
            if (GUILayout.Button("Generate NEW Animator…"))
            {
                string path = EditorUtility.SaveFilePanelInProject("Generate new editable controller", profile.name + "_Animator", "controller", "Existing controllers are never overwritten.");
                if (!string.IsNullOrEmpty(path)) Try(() => { so.ApplyModifiedProperties(); Selection.activeObject = AnimationControllerBuilder.Build(profile, path); so.Update(); });
            }
            if (GUILayout.Button("Open Animator") && profile.controller != null) AssetDatabase.OpenAsset(profile.controller);
            if (GUILayout.Button("Create NEW lab scene…")) Try(() => AnimationLabBuilder.CreateScene(profile));
            EditorGUILayout.EndHorizontal();
            EditorGUILayout.HelpBox("The Animator is a normal editable graph, not a locked generated runtime graph. Generate to a new file after changing slots/IDs; manually edited graphs remain untouched. Combat rules accept actions; animation transitions do not authorize attacks.", MessageType.Info);
            EditorGUILayout.PropertyField(so.FindProperty("actions"), true);
            foreach (var action in profile.actions)
                if (action != null && GUILayout.Button("Edit timeline: " + action.id)) CombatActionEditor.Open(action, profile.previewModel);
        }
        private void DrawIK(SerializedObject so)
        {
            EditorGUILayout.HelpBox("Generic two-bone IK; no Humanoid avatar required. Paths are relative to the model root. Contact curves default to 0: ground alignment is available, but planted-foot locking must be authored and verified. Animator should use Always Animate.", MessageType.Info);
            EditorGUILayout.HelpBox("Sole Offset is ground-to-ANKLE height. Optional pelvis correction lowers the visual skeleton, not the motor. Set its explicit common-parent path and limits; inspect target error and body clearance on uneven steps. Weight 1 alone does not prove contact.", MessageType.Info);
            BoneFields(so.FindProperty("leftFoot"), "Left leg"); BoneFields(so.FindProperty("rightFoot"), "Right leg");
            foreach (string p in new[] { "footIKWeight", "footRayHeight", "footRayDepth", "soleOffset", "maxFootCorrection", "maxPlantDistance", "pelvisPath", "maxPelvisDrop", "pelvisResponse", "groundMask" }) EditorGUILayout.PropertyField(so.FindProperty(p));
        }
        private void BoneFields(SerializedProperty leg, string label)
        {
            EditorGUILayout.LabelField(label, EditorStyles.boldLabel);
            var paths = profile.previewModel != null ? profile.previewModel.GetComponentsInChildren<Transform>(true).Select(t => AnimationUtility.CalculateTransformPath(t, profile.previewModel.transform)).ToArray() : Array.Empty<string>();
            foreach (string p in new[] { "thigh", "calf", "foot" })
            {
                var property = leg.FindPropertyRelative(p); EditorGUILayout.PropertyField(property);
                if (paths.Length == 0) continue;
                int index = Array.IndexOf(paths, property.stringValue);
                int next = EditorGUILayout.Popup("Pick " + p, index, paths);
                if (next != index && next >= 0) property.stringValue = paths[next];
            }
            EditorGUILayout.PropertyField(leg.FindPropertyRelative("kneeDirection")); EditorGUILayout.PropertyField(leg.FindPropertyRelative("soleUp"));
        }
        private void DrawLive()
        {
            live = (AnimatedCharacterDriver)EditorGUILayout.ObjectField("Scene driver", live, typeof(AnimatedCharacterDriver), true);
            if (!Application.isPlaying || live == null) { EditorGUILayout.HelpBox("In Play Mode, drag the lab character here to observe authoritative state, windows and animation blends. This window never starts Play Mode.", MessageType.Info); return; }
            EditorGUILayout.LabelField("Locomotion", $"{live.stance} / {live.Phase} / speed {live.Speed:F2} / turn {live.HeadingError:F1}°");
            EditorGUILayout.LabelField("Root owner", live.MotionOwner ?? "Not evaluated");
            var ik = live.GetComponent<GenericFootIK>();
            if (ik != null) { DrawLegStatus("Left foot IK", ik.left); DrawLegStatus("Right foot IK", ik.right); EditorGUILayout.LabelField("Pelvis offset", $"{ik.PelvisOffset * 100:F1} cm (visual only)"); }
            if (live.animator != null && live.animator.runtimeAnimatorController != null)
            {
                var current = live.animator.GetCurrentAnimatorStateInfo(0); var next = live.animator.GetNextAnimatorStateInfo(0);
                EditorGUILayout.LabelField("Animator current", $"{StateName(live.animator, current.fullPathHash)} / normalized {current.normalizedTime:F3}");
                EditorGUILayout.LabelField("Animator next", $"{StateName(live.animator, next.fullPathHash)} / blend {live.animator.GetAnimatorTransitionInfo(0).normalizedTime:F3}");
                foreach (var c in live.animator.GetCurrentAnimatorClipInfo(0)) EditorGUILayout.LabelField(c.clip.name, $"weight {c.weight:F3}");
            }
            var combat = live.combat;
            if (combat != null)
            {
                combat.suspended = EditorGUILayout.Toggle("Pause rules + presentation", combat.suspended);
                EditorGUILayout.LabelField("Rules", combat.Phase + " / " + combat.LastDecision);
                if (combat.Current != null)
                {
                    EditorGUILayout.LabelField("Action time", combat.Current.id + " / " + combat.TimeInAction.ToString("F3"));
                    foreach (WindowKind kind in Enum.GetValues(typeof(WindowKind))) if (combat.IsOpen(kind)) EditorGUILayout.LabelField("OPEN", kind.ToString());
                    if (GUILayout.Button("Open current action (read-only during Play Mode)")) CombatActionEditor.Open(combat.Current, profile.previewModel);
                }
            }
            if (!string.IsNullOrEmpty(live.LastConfigurationError)) EditorGUILayout.HelpBox(live.LastConfigurationError, MessageType.Error);
        }
        private static void DrawLegStatus(string label, GenericFootIK.Leg leg)
        {
            if (!leg.Valid) { EditorGUILayout.LabelField(label, "Missing / invalid leg chain"); return; }
            if (leg.weight <= 0) { EditorGUILayout.LabelField(label, "Inactive (no weighted ground correction)"); return; }
            float error = Vector3.Distance(leg.foot.position, leg.target);
            EditorGUILayout.LabelField(label, $"weight {leg.weight:F2} / planted {leg.planted} / target error {error * 100:F1} cm");
            if (leg.weight > 0.95f && error > 0.02f)
                EditorGUILayout.HelpBox(label + ": target not reached. Check ankle offset, leg reach, pelvis path/drop limit, contact timing and terrain height.", MessageType.Warning);
        }
        private static string StateName(Animator animator, int hash)
        {
            if (hash == 0) return "None";
            var runtime = animator.runtimeAnimatorController;
            if (runtime is AnimatorOverrideController over) runtime = over.runtimeAnimatorController;
            var controller = runtime as UnityEditor.Animations.AnimatorController;
            if (controller == null) return hash.ToString();
            string Find(UnityEditor.Animations.AnimatorStateMachine machine, string prefix)
            {
                foreach (var state in machine.states) if (Animator.StringToHash(prefix + "." + state.state.name) == hash) return prefix + "." + state.state.name;
                foreach (var child in machine.stateMachines) { var found = Find(child.stateMachine, prefix + "." + child.stateMachine.name); if (found != null) return found; }
                return null;
            }
            foreach (var layer in controller.layers) { var found = Find(layer.stateMachine, layer.name); if (found != null) return found; }
            return hash.ToString();
        }
        private void DrawBindings()
        {
            if (GUILayout.Button("Audit missing animation slots")) report = string.Join("\n", AnimationBindingTools.Missing(profile));
            bindingClip = (AnimationClip)EditorGUILayout.ObjectField("Source clip", bindingClip, typeof(AnimationClip), false);
            if (GUILayout.Button("Check binding coverage")) report = AnimationBindingTools.Coverage(profile.previewModel, bindingClip);
            if (GUILayout.Button("Create reviewed per-bone map…")) Try(() => ClipBindingMapEditor.Open(profile.previewModel, bindingClip));
            prefixFrom = EditorGUILayout.TextField("Old path prefix", prefixFrom); prefixTo = EditorGUILayout.TextField("New path prefix", prefixTo);
            EditorGUILayout.HelpBox("A shared bone naming convention does not prove identical hierarchy. Remap makes a NEW clip, checks every target path and rejects collisions. It never rewrites the source clip or guesses a bone mapping. Legacy Animation Events are removed from the copy.", MessageType.Warning);
            if (GUILayout.Button("Create remapped COPY…"))
            {
                string path = EditorUtility.SaveFilePanelInProject("New remapped clip", bindingClip != null ? bindingClip.name + "_Mapped" : "Mapped", "anim", "For reference assets, choose Assets/LocalAnimationLab only.");
                if (!string.IsNullOrEmpty(path)) Try(() => { var copy = AnimationBindingTools.RemapCopy(bindingClip, profile.previewModel, prefixFrom, prefixTo, path); report = AnimationBindingTools.Coverage(profile.previewModel, copy); Selection.activeObject = copy; });
            }
            EditorGUILayout.TextArea(report, GUILayout.MinHeight(200));
        }
        private void Try(Action action) { try { action(); } catch (Exception e) { report = e.Message; EditorUtility.DisplayDialog("Animation workbench", e.Message, "OK"); } }
    }
}
