using System;
using System.IO;
using System.Linq;
using Afauxzhub.CharacterLocomotion;
using Afauxzhub.Project.Animation;
using Afauxzhub.Project.Locomotion;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;
using Object = UnityEngine.Object;

namespace Afauxzhub.Project.Editor.Animation
{
    public sealed class MotionCharacterWizard : EditorWindow
    {
        [SerializeField] private GameObject model;
        [SerializeField] private MotionLibrary template;
        [SerializeField] private string destination = "Assets/Art/Characters/NewCharacter/MotionLab";
        [SerializeField] private bool reuseClips;
        private string message = "";
        [MenuItem("Tools/MY Project/Animation/New Character Lab (No Wires)")]
        public static void Open() => GetWindow<MotionCharacterWizard>("新角色 · 无连线").Show();
        private void OnGUI()
        {
            EditorGUILayout.HelpBox("创建全新目录：独立库、移动参数、灰盒战斗配置和测试场景。不生成 Animator，不保存/关闭原场景。模型可暂留空。参考资源必须留在 LocalAnimationLab。", MessageType.Info);
            model = (GameObject)EditorGUILayout.ObjectField("模型 Prefab / FBX", model, typeof(GameObject), false);
            template = (MotionLibrary)EditorGUILayout.ObjectField("可选配置模板", template, typeof(MotionLibrary), false);
            reuseClips = EditorGUILayout.Toggle("显式复用模板动画", reuseClips);
            destination = EditorGUILayout.TextField("新目录 Assets/...", destination);
            if (GUILayout.Button("创建（不切换当前场景）"))
            {
                try { var result = Create(model, template, destination, reuseClips); Selection.activeObject = result; message = "已创建 " + destination + "/Test.unity。退出当前 Play，手动双击 Test 场景；动作库为 Motions.asset。"; }
                catch (Exception e) { message = e.Message; }
            }
            EditorGUILayout.HelpBox(message, MessageType.None);
        }
        public static void Preflight(GameObject model, MotionLibrary template, string folder, bool reuse)
        {
            if (Application.isPlaying) throw new InvalidOperationException("Exit Play Mode first.");
            if (string.IsNullOrWhiteSpace(folder) || !folder.StartsWith("Assets/", StringComparison.Ordinal) || folder.Contains("..") || folder.Contains('\\')
                || folder.EndsWith("/", StringComparison.Ordinal) || folder.Split('/').Any(p => string.IsNullOrWhiteSpace(p) || p.IndexOfAny(Path.GetInvalidFileNameChars()) >= 0))
                throw new ArgumentException("Choose a new Assets subfolder without traversal or invalid characters.");
            if (Directory.Exists(folder) || AssetDatabase.IsValidFolder(folder) || File.Exists(folder)) throw new InvalidOperationException("Destination already exists; nothing overwritten.");
            if (model != null && !EditorUtility.IsPersistent(model)) throw new InvalidOperationException("Choose a model asset, not a scene object.");
            MotionAuthoringTools.GuardDestination(folder + "/Motions.asset", model);
            if (template != null)
            {
                if (template.Validate().Any()) throw new InvalidOperationException("Template has invalid configuration: " + template.Validate().First());
                // Configuration-only copying clears clips, model, review fingerprints and bridge references.
                if (reuse) MotionAuthoringTools.GuardDestination(folder + "/Motions.asset", template);
            }
        }
        private static void EnsureFolder(string folder)
        {
            if (AssetDatabase.IsValidFolder(folder)) return;
            string parent = folder.Substring(0, folder.LastIndexOf('/'));
            EnsureFolder(parent); AssetDatabase.CreateFolder(parent, Path.GetFileName(folder));
        }
        public static MotionLibrary Create(GameObject model, MotionLibrary template, string folder, bool reuse)
        {
            Preflight(model, template, folder, reuse);
            var previous = SceneManager.GetActiveScene(); Scene created = default;
            EnsureFolder(folder);
            var library = template != null ? Object.Instantiate(template) : ScriptableObject.CreateInstance<MotionLibrary>();
            library.name = "Motions"; library.hideFlags = HideFlags.None; library.model = model;
            AssetDatabase.CreateAsset(library, folder + "/Motions.asset");
            foreach (WeaponStance stance in Enum.GetValues(typeof(WeaponStance)))
            {
                var original = template != null ? template.Movement(stance) : null;
                var movement = original != null ? Object.Instantiate(original) : ScriptableObject.CreateInstance<LocomotionProfile>();
                movement.name = stance + " tuning"; movement.hideFlags = HideFlags.None;
                if (stance == WeaponStance.Sheathed) library.relaxedMovement = movement; else library.readyMovement = movement;
                AssetDatabase.AddObjectToAsset(movement, library);
            }
            var recipes = template != null && template.templates != null ? Object.Instantiate(template.templates) : ScriptableObject.CreateInstance<MotionRecipeTemplates>();
            recipes.hideFlags = HideFlags.None; recipes.name = "Transition templates";
            if (recipes.recipes.Count == 0) recipes.recipes.Add(new MotionRecipe { label = "Default" });
            AssetDatabase.AddObjectToAsset(recipes, library); library.templates = recipes;
            MotionCatalog.AddMissing(library);
            foreach (var entry in library.entries)
            {
                entry.review = MotionReview.Pending; entry.reviewedFingerprint = "";
                if (!reuse) { entry.clip = null; entry.note = "Assign and review for this character."; }
            }
            if (!reuse) foreach (var recipe in library.overrides.Concat(recipes.recipes)) recipe.bridgeEntry = "";
            // Compatibility adapter for the existing combat lab; movement and animation still use the new library.
            var profile = AnimationLabBuilder.CreateProfile(folder + "/CombatProfile.asset");
            profile.previewModel = model; profile.locomotionRootMotion = false;
            EditorUtility.SetDirty(profile); AssetDatabase.SaveAssetIfDirty(profile);
            EditorUtility.SetDirty(library); AssetDatabase.SaveAssetIfDirty(library);
            try
            {
                created = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Additive); SceneManager.SetActiveScene(created);
                var actor = new GameObject("Character (No Wires)"); actor.SetActive(false); actor.transform.position = Vector3.up * 0.1f;
                var cc = actor.AddComponent<CharacterController>(); cc.height = 1.8f; cc.radius = 0.3f; cc.center = Vector3.up * 0.9f; cc.stepOffset = 0.25f;
                var motor = actor.AddComponent<CharacterControllerMotor>(); motor.Configure(cc, 20, 2);
                var input = actor.AddComponent<KeyboardMovementInput>();
                GameObject render;
                if (model != null) render = RenderOnlyModel.Copy(model);
                else { render = GameObject.CreatePrimitive(PrimitiveType.Capsule); Object.DestroyImmediate(render.GetComponent<Collider>()); render.AddComponent<Animator>(); }
                render.name = "Model"; render.transform.SetParent(actor.transform, false);
                foreach (var node in render.GetComponentsInChildren<Transform>(true)) { node.gameObject.hideFlags = HideFlags.None; foreach (var c in node.GetComponents<Component>()) if (c != null) c.hideFlags = HideFlags.None; }
                var animator = render.GetComponent<Animator>(); animator.runtimeAnimatorController = null; animator.applyRootMotion = false; animator.cullingMode = AnimatorCullingMode.AlwaysAnimate;
                var combat = actor.AddComponent<CombatActionController>(); combat.profile = profile; combat.permissionGate = actor.AddComponent<AnimationLabPermissionGate>();
                var driver = actor.AddComponent<AnimatedCharacterDriver>(); driver.profile = profile; driver.animator = animator; driver.motor = motor; driver.inputSource = input; driver.combat = combat;
                var player = actor.AddComponent<MotionLibraryPlayer>(); player.driver = driver; player.library = library; driver.motionPlayer = player;
                var presentation = actor.AddComponent<ActionPresentation>(); presentation.combat = combat; presentation.skeletonRoot = render.transform;
                var controls = actor.AddComponent<AnimationLabInput>(); controls.driver = driver;
                foreach (Transform node in actor.GetComponentsInChildren<Transform>(true)) node.gameObject.layer = 2;
                var floor = GameObject.CreatePrimitive(PrimitiveType.Cube); floor.name = "Floor"; floor.transform.position = new Vector3(0, -0.2f, 0); floor.transform.localScale = new Vector3(40, 0.4f, 40);
                var target = GameObject.CreatePrimitive(PrimitiveType.Capsule); target.name = "Lock target"; target.transform.position = new Vector3(0, 1, 6); controls.target = target.transform;
                var light = new GameObject("Key Light"); light.transform.rotation = Quaternion.Euler(45, -30, 0); var lighting = light.AddComponent<Light>(); lighting.type = LightType.Directional; lighting.intensity = 1.2f;
                var camera = new GameObject("Lab Camera"); camera.SetActive(false); camera.tag = "MainCamera"; camera.AddComponent<Camera>(); camera.AddComponent<AudioListener>();
                var follow = camera.AddComponent<AnimationLabCamera>(); follow.target = actor.transform; follow.presentation = presentation; driver.cameraReference = camera.transform;
                actor.SetActive(true); camera.SetActive(true);
                if (!EditorSceneManager.SaveScene(created, folder + "/Test.unity")) throw new InvalidOperationException("New scene could not be saved. Created assets kept for recovery.");
                return library;
            }
            finally
            {
                if (previous.IsValid() && previous.isLoaded) SceneManager.SetActiveScene(previous);
                if (created.IsValid() && created.isLoaded) EditorSceneManager.CloseScene(created, true);
            }
        }
    }
}
