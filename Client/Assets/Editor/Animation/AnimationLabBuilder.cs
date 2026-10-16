using System;
using System.IO;
using Afauxzhub.CharacterLocomotion;
using Afauxzhub.Project.Animation;
using Afauxzhub.Project.Locomotion;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace Afauxzhub.Project.Editor.Animation
{
    public static class AnimationLabBuilder
    {
        public static CharacterAnimationProfile CreateProfileDialog()
        {
            string path = EditorUtility.SaveFilePanelInProject("Create animation lab profile", "CharacterAnimationProfile", "asset", "Reference assets and dependent profiles must stay under Assets/LocalAnimationLab. Choose a new file.");
            if (string.IsNullOrEmpty(path)) return null;
            if (AssetDatabase.LoadMainAssetAtPath(path) != null) { EditorUtility.DisplayDialog("Animation lab", "Choose a new asset; existing authoring is not overwritten.", "OK"); return null; }
            return CreateProfile(path);
        }

        public static CharacterAnimationProfile CreateProfile(string path)
        {
            if (Application.isPlaying) throw new InvalidOperationException("Exit Play Mode first.");
            if (string.IsNullOrEmpty(path) || !path.StartsWith("Assets/", StringComparison.Ordinal) || Path.GetExtension(path) != ".asset") throw new ArgumentException("Choose an Assets/*.asset path.");
            if (File.Exists(path) || AssetDatabase.LoadMainAssetAtPath(path) != null) throw new InvalidOperationException("Choose a new profile path; existing authoring is never overwritten.");
            var profile = ScriptableObject.CreateInstance<CharacterAnimationProfile>(); profile.name = Path.GetFileNameWithoutExtension(path);
            profile.EnsureSlots(); AssetDatabase.CreateAsset(profile, path);
            foreach (WeaponStance stance in Enum.GetValues(typeof(WeaponStance)))
            {
                var movement = ScriptableObject.CreateInstance<LocomotionProfile>(); movement.name = stance + "Movement";
                movement.constrainArcRadius = true;
                if (stance == WeaponStance.Drawn) { movement.runSpeed = 4; movement.sprintSpeed = 6; movement.strafeSpeed = 3; }
                profile.Set(stance).movement = movement; AssetDatabase.AddObjectToAsset(movement, profile);
            }
            foreach (ActionKind kind in Enum.GetValues(typeof(ActionKind)))
            {
                string id = kind == ActionKind.LightAttack ? "L1" : kind == ActionKind.HeavyAttack ? "H1" : kind.ToString();
                AddAction(profile, kind, id);
            }
            var light = profile.Find(ActionKind.LightAttack); var heavy = profile.Find(ActionKind.HeavyAttack);
            for (int i = 2; i <= 4; i++) { var next = AddAction(profile, ActionKind.LightAttack, "L" + i); light.nextLight = next; light = next; }
            for (int i = 2; i <= 3; i++) { var next = AddAction(profile, ActionKind.HeavyAttack, "H" + i); heavy.nextHeavy = next; heavy = next; }
            EditorUtility.SetDirty(profile); AssetDatabase.SaveAssetIfDirty(profile); Selection.activeObject = profile; return profile;
        }
        private static ActionDefinition AddAction(CharacterAnimationProfile profile, ActionKind kind, string id)
        {
            var action = ScriptableObject.CreateInstance<ActionDefinition>(); action.name = action.id = id; action.kind = kind;
            action.notes = "GREYBOX PLACEHOLDER — clip missing; timings are tunable test data, not accepted balance or animation acceptance.";
            action.ruleIds = "PROTO-01..03; ATK-05..07; COUNTER-01..02; HIT-02";
            action.activeStart = 0.25f; action.recoveryStart = 0.5f;
            if (kind == ActionKind.LightAttack || kind == ActionKind.HeavyAttack)
            {
                action.windows.Add(Window(WindowKind.Hitbox, "hit", 0.25f, 0.42f));
                action.windows.Add(Window(WindowKind.Counter, "counter", 0.22f, 0.32f));
                action.windows.Add(Window(WindowKind.CancelToEvade, "evade", 0.5f, 1));
                action.windows.Add(Window(WindowKind.CancelToGuard, "guard", 0.55f, 1));
                action.windows.Add(Window(WindowKind.CancelToSkill, "skill", 0.7f, 1));
                action.windows.Add(Window(WindowKind.Combo, "combo", 0.55f, 0.9f));
                action.hitShapes.Add(new HitShape());
            }
            if (kind == ActionKind.Dodge)
            {
                action.movement = MovementAuthority.Procedural; action.inputMovementScale = 1;
                action.windows.Add(Window(WindowKind.Movement, "movement", 0, 0.5f));
                action.windows.Add(Window(WindowKind.Invulnerable, "invulnerability", 0.05f, 0.3f));
            }
            if (kind == ActionKind.Guard || kind == ActionKind.Charge)
            {
                action.hold = true;
                action.windows.Add(Window(WindowKind.CancelToEvade, "evade", 0, 1));
            }
            // No default hit-stun escape: HIT-05 remains unconfirmed.
            profile.actions.Add(action); AssetDatabase.AddObjectToAsset(action, profile); return action;
        }
        private static ActionWindow Window(WindowKind kind, string id, float start, float end) => new ActionWindow { kind = kind, id = id, start = start, end = end };

        public static void CreateScene(CharacterAnimationProfile profile)
        {
            if (Application.isPlaying) throw new InvalidOperationException("Exit Play Mode first.");
            if (profile == null || profile.controller == null) throw new InvalidOperationException("Assign a profile and generate its Animator first.");
            string path = EditorUtility.SaveFilePanelInProject("Save NEW animation lab scene", "AnimationLab", "unity", "A new additive scene is created. Existing scenes are not overwritten or added to build settings.");
            if (string.IsNullOrEmpty(path)) return;
            CreateScene(profile, path);
            EditorUtility.DisplayDialog("Animation lab created", "The scene is additive. Unload other gameplay scenes before Play Mode to avoid duplicate cameras, listeners and physics. Paid actions are disabled until the explicit sandbox permission checkbox is enabled. Clips, root motion, IK and transition quality are not yet validated.", "OK");
        }

        public static UnityEngine.SceneManagement.Scene CreateScene(CharacterAnimationProfile profile, string path, bool replaceCleanUntitled = false)
        {
            if (Application.isPlaying) throw new InvalidOperationException("Exit Play Mode first.");
            if (profile == null || profile.controller == null) throw new InvalidOperationException("Assign a profile and generate its Animator first.");
            if (string.IsNullOrEmpty(path) || !path.StartsWith("Assets/", StringComparison.Ordinal) || Path.GetExtension(path) != ".unity") throw new ArgumentException("Choose an Assets/*.unity path.");
            AnimationBindingTools.RequireLocalDestination(path, profile, profile.previewModel, profile.controller);
            if (File.Exists(path)) throw new InvalidOperationException("Choose a new scene path.");
            // Additive creation must not prompt to save or modify any pre-existing scene.
            var mode = NewSceneMode.Additive;
            var current = UnityEngine.SceneManagement.SceneManager.GetActiveScene();
            if (replaceCleanUntitled)
            {
                if (UnityEngine.SceneManagement.SceneManager.sceneCount != 1 || !string.IsNullOrEmpty(current.path) || current.isDirty)
                    throw new InvalidOperationException("Only a single unmodified untitled scene may be explicitly replaced. No scene was saved or closed.");
                mode = NewSceneMode.Single;
            }
            var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, mode);
            UnityEngine.SceneManagement.SceneManager.SetActiveScene(scene);
            var root = new GameObject("AnimationLab (isolated)");
            var actor = new GameObject("Character"); actor.SetActive(false); actor.transform.SetParent(root.transform); actor.transform.position = new Vector3(0, 0.1f, 0);
            var cc = actor.AddComponent<CharacterController>(); cc.height = 1.8f; cc.radius = 0.3f; cc.center = Vector3.up * 0.9f; cc.stepOffset = 0.25f;
            var motor = actor.AddComponent<CharacterControllerMotor>(); motor.Configure(cc, 20, 2);
            var input = actor.AddComponent<KeyboardMovementInput>();
            GameObject model;
            if (profile.previewModel != null) model = RenderOnlyModel.Copy(profile.previewModel);
            else { model = GameObject.CreatePrimitive(PrimitiveType.Capsule); UnityEngine.Object.DestroyImmediate(model.GetComponent<Collider>()); model.AddComponent<Animator>(); }
            model.name = "Model"; model.transform.SetParent(actor.transform, false);
            foreach (var t in model.GetComponentsInChildren<Transform>(true)) { t.gameObject.hideFlags = HideFlags.None; foreach (var c in t.GetComponents<Component>()) if (c != null) c.hideFlags = HideFlags.None; }
            var animator = model.GetComponent<Animator>(); animator.runtimeAnimatorController = profile.controller; animator.applyRootMotion = true; animator.cullingMode = AnimatorCullingMode.AlwaysAnimate;
            var combat = actor.AddComponent<CombatActionController>(); combat.profile = profile;
            var gate = actor.AddComponent<AnimationLabPermissionGate>(); combat.permissionGate = gate;
            var driver = actor.AddComponent<AnimatedCharacterDriver>(); driver.profile = profile; driver.animator = animator; driver.motor = motor; driver.inputSource = input; driver.combat = combat;
            var relay = model.AddComponent<AnimatorMotionRelay>(); relay.driver = driver;
            var ik = actor.AddComponent<GenericFootIK>(); ik.driver = driver; ik.Bind(profile, model.transform);
            var presentation = actor.AddComponent<ActionPresentation>(); presentation.combat = combat; presentation.skeletonRoot = model.transform;
            var controls = actor.AddComponent<AnimationLabInput>(); controls.driver = driver;
            foreach (Transform t in actor.GetComponentsInChildren<Transform>(true)) t.gameObject.layer = 2; // Ignore Raycast; floor remains Default.
            var floor = GameObject.CreatePrimitive(PrimitiveType.Cube); floor.name = "Floor"; floor.transform.SetParent(root.transform); floor.transform.position = new Vector3(0, -0.2f, 0); floor.transform.localScale = new Vector3(40, 0.4f, 40);
            var slope = GameObject.CreatePrimitive(PrimitiveType.Cube); slope.name = "FootIK Slope 12deg"; slope.transform.SetParent(root.transform); slope.transform.SetPositionAndRotation(new Vector3(-4, 0.4f, 5), Quaternion.Euler(12, 0, 0)); slope.transform.localScale = new Vector3(3, 0.4f, 5);
            var step = GameObject.CreatePrimitive(PrimitiveType.Cube); step.name = "FootIK Step 0.15m"; step.transform.SetParent(root.transform); step.transform.position = new Vector3(3, 0.075f, 4); step.transform.localScale = new Vector3(2, 0.15f, 2);
            var target = GameObject.CreatePrimitive(PrimitiveType.Capsule); target.name = "Lock target (no combat resolver)"; target.transform.SetParent(root.transform); target.transform.position = new Vector3(0, 1, 6); controls.target = target.transform;
            var light = new GameObject("Key Light"); light.transform.SetParent(root.transform); light.transform.rotation = Quaternion.Euler(45, -30, 0); var lighting = light.AddComponent<Light>(); lighting.type = LightType.Directional; lighting.intensity = 1.2f;
            var camera = new GameObject("Lab Camera"); camera.SetActive(false); camera.transform.SetParent(root.transform); camera.tag = "MainCamera"; camera.AddComponent<Camera>(); camera.AddComponent<AudioListener>();
            var follow = camera.AddComponent<AnimationLabCamera>(); follow.target = actor.transform; follow.presentation = presentation;
            driver.cameraReference = camera.transform;
            actor.SetActive(true); camera.SetActive(true);
            EditorSceneManager.SaveScene(scene, path);
            Selection.activeGameObject = actor;
            return scene;
        }
    }
}
