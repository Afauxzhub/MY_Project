using System;
using System.IO;
using System.Linq;
using Afauxzhub.CharacterLocomotion;
using Afauxzhub.Project.Locomotion;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace Afauxzhub.Project.Editor
{
    public static class LocomotionGreyboxValidation
    {
        private const string ScenePath = "Assets/Scenes/LocomotionGreybox.unity";
        private const string ProfileFolder = "Assets/Locomotion";
        private const string ProfilePath = ProfileFolder + "/LocomotionGreyboxProfile.asset";

        [MenuItem("Tools/MY Project/Create or Validate Locomotion Greybox")]
        public static void CreateOrValidate()
        {
            LocomotionProfile profile = CreateOrLoadProfile();
            AssetDatabase.SaveAssets();
            CreateScene(profile);
            Scene scene = EditorSceneManager.OpenScene(ScenePath, OpenSceneMode.Single);
            ValidateScene(scene);
            EnsureSceneIsInBuildSettings();
            AssetDatabase.SaveAssets();

            Debug.Log(
                "[MY_Project Locomotion] PASS: greybox scene recreated and validated. "
                + "Runtime feel and physical keyboard input still require Play Mode acceptance.");
        }

        private static LocomotionProfile CreateOrLoadProfile()
        {
            if (!AssetDatabase.IsValidFolder(ProfileFolder))
            {
                AssetDatabase.CreateFolder("Assets", "Locomotion");
            }
            var profile = AssetDatabase.LoadAssetAtPath<LocomotionProfile>(ProfilePath);
            if (profile != null)
            {
                return profile;
            }

            profile = ScriptableObject.CreateInstance<LocomotionProfile>();
            profile.inputDeadZone = 0.1f;
            profile.runSpeed = 5f;
            profile.wideTurnRadius = 4f;
            profile.minimumTurnRadius = 1.25f;
            profile.headingCatchUpTime = 0.25f;
            profile.maximumYawRate = 300f;
            profile.yawAcceleration = 900f;
            profile.yawDeceleration = 1200f;
            AssetDatabase.CreateAsset(profile, ProfilePath);
            return profile;
        }

        private static Scene CreateScene(LocomotionProfile profile)
        {
            Directory.CreateDirectory(Path.GetDirectoryName(ScenePath) ?? "Assets");
            Scene scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);

            CreateDirectionalLight();
            CreateEnvironmentCube("Ground", new Vector3(0f, -0.5f, 0f), new Vector3(20f, 1f, 20f));
            CreateEnvironmentCube("ForwardObstacle", new Vector3(0f, 1f, 5f), new Vector3(5f, 2f, 1f));
            CreateEnvironmentCube("SideObstacle", new Vector3(4f, 0.75f, 0f), new Vector3(1f, 1.5f, 6f));

            GameObject player = new GameObject("Player");
            player.transform.SetPositionAndRotation(Vector3.zero, Quaternion.identity);
            var controller = player.AddComponent<CharacterController>();
            controller.center = new Vector3(0f, 1f, 0f);
            controller.height = 2f;
            controller.radius = 0.45f;
            controller.skinWidth = 0.05f;
            controller.stepOffset = 0.3f;

            var keyboardInput = player.AddComponent<KeyboardMovementInput>();
            var motor = player.AddComponent<CharacterControllerMotor>();
            motor.Configure(controller, 20f, 2f);
            var brain = player.AddComponent<ThirdPersonLocomotionBrain>();

            GameObject visual = GameObject.CreatePrimitive(PrimitiveType.Capsule);
            visual.name = "CapsuleVisual";
            UnityEngine.Object.DestroyImmediate(visual.GetComponent<Collider>());
            visual.transform.SetParent(player.transform, false);
            visual.transform.localPosition = Vector3.up;
            visual.transform.localScale = new Vector3(0.9f, 1f, 0.9f);

            GameObject cameraObject = new GameObject("Main Camera");
            cameraObject.tag = "MainCamera";
            cameraObject.AddComponent<Camera>();
            cameraObject.AddComponent<AudioListener>();
            var cameraReference = cameraObject.AddComponent<FixedFollowCameraReference>();
            cameraReference.Configure(player.transform, new Vector3(0f, 6f, -8f), 1.25f);

            brain.Configure(keyboardInput, cameraReference, motor, profile);

            if (!EditorSceneManager.SaveScene(scene, ScenePath))
            {
                throw new InvalidOperationException($"Failed to save locomotion scene at {ScenePath}.");
            }

            return scene;
        }

        private static void CreateDirectionalLight()
        {
            GameObject lightObject = new GameObject("Directional Light");
            var light = lightObject.AddComponent<Light>();
            light.type = LightType.Directional;
            light.intensity = 1f;
            lightObject.transform.rotation = Quaternion.Euler(50f, -30f, 0f);
        }

        private static void CreateEnvironmentCube(string name, Vector3 position, Vector3 scale)
        {
            GameObject cube = GameObject.CreatePrimitive(PrimitiveType.Cube);
            cube.name = name;
            cube.transform.position = position;
            cube.transform.localScale = scale;
        }

        private static void ValidateScene(Scene scene)
        {
            if (!scene.IsValid() || scene.path != ScenePath)
            {
                throw new InvalidOperationException($"Expected open scene {ScenePath}.");
            }

            GameObject player = RequireRoot(scene, "Player");
            RequireComponent<CharacterController>(player);
            RequireComponent<KeyboardMovementInput>(player);

            var motor = RequireComponent<CharacterControllerMotor>(player);
            if (!motor.IsConfigured)
            {
                throw new InvalidOperationException("Player motor is not configured.");
            }

            var brain = RequireComponent<ThirdPersonLocomotionBrain>(player);
            if (!brain.IsConfigured)
            {
                throw new InvalidOperationException(
                    $"Locomotion brain adapters are not configured: {brain.ConfigurationStatus}.");
            }

            GameObject cameraObject = RequireRoot(scene, "Main Camera");
            RequireComponent<Camera>(cameraObject);
            var cameraReference = RequireComponent<FixedFollowCameraReference>(cameraObject);
            if (!cameraReference.IsConfigured)
            {
                throw new InvalidOperationException("Camera reference is not configured.");
            }

            RequireCollider(scene, "Ground");
            RequireCollider(scene, "ForwardObstacle");
            RequireCollider(scene, "SideObstacle");

            if (AssetDatabase.LoadAssetAtPath<LocomotionProfile>(ProfilePath) == null)
            {
                throw new InvalidOperationException($"Missing locomotion profile at {ProfilePath}.");
            }
        }

        private static GameObject RequireRoot(Scene scene, string name)
        {
            GameObject result = scene.GetRootGameObjects().FirstOrDefault(item => item.name == name);
            return result != null
                ? result
                : throw new InvalidOperationException($"Scene is missing root object '{name}'.");
        }

        private static T RequireComponent<T>(GameObject gameObject) where T : Component
        {
            T component = gameObject.GetComponent<T>();
            return component != null
                ? component
                : throw new InvalidOperationException($"{gameObject.name} is missing {typeof(T).Name}.");
        }

        private static void RequireCollider(Scene scene, string objectName)
        {
            GameObject gameObject = RequireRoot(scene, objectName);
            RequireComponent<Collider>(gameObject);
        }

        private static void EnsureSceneIsInBuildSettings()
        {
            var scenes = EditorBuildSettings.scenes.ToList();
            int existingIndex = scenes.FindIndex(scene => scene.path == ScenePath);
            var entry = new EditorBuildSettingsScene(ScenePath, true);
            if (existingIndex >= 0)
            {
                scenes[existingIndex] = entry;
            }
            else
            {
                scenes.Add(entry);
            }

            EditorBuildSettings.scenes = scenes.ToArray();
        }
    }
}
