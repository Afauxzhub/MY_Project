using System;
using System.Collections.Generic;
using System.Linq;
using Afauxzhub.Project.Animation;
using UnityEditor;
using UnityEngine;

namespace Afauxzhub.Project.Editor.Animation
{
    /// <summary>Repeatable Play-only fixture. No test MonoBehaviours, transforms or settings are saved to a scene.</summary>
    [InitializeOnLoad]
    public static class MotionPlayValidation
    {
        private const string Key = "MYProject.NoWires.Validation.";
        [Serializable] public sealed class Report
        {
            public string status, note;
            public int targetFps, frames, assertions, maxVoices, ceilingContacts;
            public float elapsed, averageFps, idleJumpHeight, movingJumpHeight, maxWeightError, outgoingReplayTime, incomingReplayTime;
            public string[] phases, missing, failures;
        }
        private sealed class Step
        {
            public string name; public float duration; public Vector2 input;
            public bool sprint, walk, target; public Action enter;
        }
        private static readonly List<Step> steps = new List<Step>();
        private static readonly HashSet<string> phases = new HashSet<string>(), missing = new HashSet<string>(), failures = new HashSet<string>();
        private static AnimatedCharacterDriver driver;
        private static AnimationLabInput controls;
        private static Report report;
        private static int index, lastFrame = -1;
        private static float stepTime, originY;
        private static string sourceJson;
        private static GameObject temporaryCeiling;
        static MotionPlayValidation()
        {
            EditorApplication.playModeStateChanged += StateChanged;
        }
        public static string Status => SessionState.GetString(Key + "report", "Not started");
        [MenuItem("Tools/MY Project/Animation/Run No-Wires Play Sweep/30 fps")]
        public static void Run30() => Start(30);
        [MenuItem("Tools/MY Project/Animation/Run No-Wires Play Sweep/60 fps")]
        public static void Run60() => Start(60);
        [MenuItem("Tools/MY Project/Animation/Run No-Wires Play Sweep/120 fps")]
        public static void Run120() => Start(120);
        public static void Start(int fps)
        {
            if (EditorApplication.isPlayingOrWillChangePlaymode) throw new InvalidOperationException("Exit Play first.");
            var scene = UnityEngine.SceneManagement.SceneManager.GetActiveScene();
            if (scene.isDirty || !scene.path.StartsWith("Assets/LocalAnimationLab/", StringComparison.Ordinal)) throw new InvalidOperationException("Use a clean isolated local scene.");
            if (UnityEngine.Object.FindObjectsByType<MotionLibraryPlayer>(FindObjectsSortMode.None).Length != 1) throw new InvalidOperationException("Expected exactly one no-wires player.");
            SessionState.SetBool(Key + "run", true); SessionState.SetInt(Key + "fps", fps);
            SessionState.SetInt(Key + "oldFps", Application.targetFrameRate); SessionState.SetInt(Key + "oldVsync", QualitySettings.vSyncCount);
            SessionState.SetBool(Key + "oldBackground", Application.runInBackground); SessionState.SetFloat(Key + "oldScale", Time.timeScale);
            SessionState.SetString(Key + "report", "Starting Play validation"); EditorApplication.isPlaying = true;
        }
        private static void StateChanged(PlayModeStateChange state)
        {
            if (state == PlayModeStateChange.EnteredPlayMode && SessionState.GetBool(Key + "run", false)) Begin();
            if (state == PlayModeStateChange.ExitingPlayMode && SessionState.GetBool(Key + "run", false))
            {
                if (report != null && report.status == "Running") { failures.Add("Run interrupted"); Complete(false); }
                Restore(); SessionState.SetBool(Key + "run", false);
            }
        }
        private static void Begin()
        {
            driver = UnityEngine.Object.FindFirstObjectByType<AnimatedCharacterDriver>(); controls = driver.GetComponent<AnimationLabInput>();
            controls.enabled = false; driver.useManualInput = true; driver.cameraReference = null;
            report = new Report { status = "Running", targetFps = SessionState.GetInt(Key + "fps", 60), note = "Mechanism regression only; missing clips remain explicit. Dynamic IK disabled." };
            Application.targetFrameRate = report.targetFps; QualitySettings.vSyncCount = 0; Application.runInBackground = true; Time.timeScale = 1;
            driver.motionPlayer.Ensure(); sourceJson = EditorJsonUtility.ToJson(driver.motionPlayer.library);
            driver.motionPlayer.Player.Evaluated += PoseEvaluated;
            index = -1; stepTime = 0; steps.Clear(); phases.Clear(); missing.Clear(); failures.Clear();
            for (int set = 0; set < 2; set++)
            {
                var stance = (WeaponStance)set;
                Add("reset / " + stance, 0.4f, Vector2.zero, enter: () => { driver.stance = stance; Teleport(); });
                Add("stationary right", 0.65f, Vector2.zero, enter: () => driver.RequestFacing(Vector3.right));
                // Exactly 180 degrees has no unique left/right sign; exercise an unambiguous left pivot.
                Add("stationary left pivot", 0.8f, Vector2.zero, enter: () => driver.RequestFacing(Quaternion.Euler(0, -170, 0) * driver.transform.forward));
                Add("in-place reset", 0.6f, Vector2.zero, enter: () => { driver.ClearFacingRequest(); Teleport(); });
                Add("run", 0.8f, Vector2.up);
                Add("sprint", 0.8f, Vector2.up, sprint: true);
                Add("moving pivot back", 0.75f, Vector2.down);
                Add("moving pivot forward", 0.75f, Vector2.up);
                Add("walk", 0.65f, Vector2.up, walk: true);
                Add("stop", 0.65f, Vector2.zero);
                Add("start right", 0.75f, Vector2.right);
                Add("pivot left", 0.75f, Vector2.left);
                Add("arc", 0.6f, new Vector2(-0.7f, 0.7f));
                Add("rapid target enter", 0.12f, Vector2.right, target: true);
                Add("rapid target exit", 0.12f, Vector2.left);
                Add("target deactivated", 0.2f, Vector2.up, target: true, enter: () => controls.target.gameObject.SetActive(false));
                Add("target loss verified", 0.3f, Vector2.up, enter: () => { Check(!driver.Targeting, "inactive target falls back to free"); controls.target.gameObject.SetActive(true); });
                for (int dir = 0; dir < 8; dir++)
                {
                    float angle = dir * Mathf.PI / 4;
                    Add("target " + dir, 0.35f, new Vector2(Mathf.Sin(angle), Mathf.Cos(angle)), target: true);
                }
                Add("settle jump", 0.65f, Vector2.zero, enter: Teleport);
                Add("idle jump", 1.4f, Vector2.zero, enter: () => { originY = driver.transform.position.y; Check(driver.RequestJump(), "idle jump accepted"); Check(!driver.RequestJump(), "double jump rejected"); Check(!driver.combat.Request(driver.profile.Find(ActionKind.LightAttack), false), "air attack fail closed"); });
                Add("run before jump", 0.6f, Vector2.up);
                Add("moving jump", 1.4f, Vector2.up, enter: () => { originY = driver.transform.position.y; Check(driver.RequestJump(), "moving jump accepted"); });
                Add("walk setup", 0.6f, Vector2.up, walk: true, enter: Teleport);
                Add("walk jump", 1.4f, Vector2.up, walk: true, enter: () => Check(driver.RequestJump(), "walk jump accepted"));
                Add("sprint setup", 0.6f, Vector2.up, sprint: true, enter: Teleport);
                Add("sprint jump", 1.4f, Vector2.up, sprint: true, enter: () => Check(driver.RequestJump(), "sprint jump accepted"));
                Add("target setup", 0.6f, Vector2.right, target: true, enter: Teleport);
                Add("target jump", 1.4f, Vector2.right, target: true, enter: () => Check(driver.RequestJump(), "target jump accepted"));
                Add("stop after jump", 0.6f, Vector2.zero);
            }
            Add("ceiling settle", 0.6f, Vector2.zero, enter: Teleport);
            Add("low ceiling jump", 1.4f, Vector2.zero, enter: () =>
            {
                var bounds = driver.GetComponent<CharacterController>().bounds;
                temporaryCeiling = GameObject.CreatePrimitive(PrimitiveType.Cube); temporaryCeiling.name = "Temporary validation roof (Play only)";
                temporaryCeiling.hideFlags = HideFlags.DontSave;
                temporaryCeiling.transform.position = new Vector3(bounds.center.x, bounds.max.y + 0.55f, bounds.center.z);
                temporaryCeiling.transform.localScale = new Vector3(4, 0.2f, 4); Physics.SyncTransforms();
                Check(driver.RequestJump(), "ceiling jump accepted");
            });
            Add("ceiling cleanup", 0.3f, Vector2.zero, enter: () =>
            { Check(report.ceilingContacts > 0, "ceiling collision observed"); UnityEngine.Object.Destroy(temporaryCeiling); temporaryCeiling = null; });
            Add("combat settle", 0.5f, Vector2.zero, enter: Teleport);
            Add("L1", 0.64f, Vector2.zero, enter: () => Check(driver.combat.Request(driver.profile.Find(ActionKind.LightAttack), false), "L1 accepted"));
            Add("repeat L1", 0.12f, Vector2.zero, enter: () => Check(driver.combat.Request(driver.profile.Find(ActionKind.LightAttack), false), "same L1 repeat in combo window"));
            Add("received hit", 1.3f, Vector2.zero, enter: () =>
            {
                Check(report.outgoingReplayTime > 0.4f && report.incomingReplayTime < 0.12f, "outgoing L1 clock preserved during blend");
                Check(driver.combat.ApplyCombatResult(driver.profile.Find(ActionKind.LightHit)), "hit interrupts action");
                Check(!driver.combat.Request(driver.profile.Find(ActionKind.Skill), false), "skill cannot cancel hit");
                Check(!driver.RequestJump(), "jump cannot escape hit");
            });
            Add("return locomotion", 0.7f, Vector2.up);
            Add("final idle", 0.6f, Vector2.zero);
            Next();
        }
        private static void Add(string name, float duration, Vector2 input, bool sprint = false, bool walk = false, bool target = false, Action enter = null)
            => steps.Add(new Step { name = name, duration = duration, input = input, sprint = sprint, walk = walk, target = target, enter = enter });
        private static void Teleport()
        {
            var cc = driver.GetComponent<CharacterController>(); cc.enabled = false;
            driver.transform.SetPositionAndRotation(new Vector3(-8, 0.1f, -8), Quaternion.identity); cc.enabled = true;
        }
        private static void Next()
        {
            index++; stepTime = 0;
            if (index >= steps.Count) { Complete(true); return; }
            var step = steps[index]; driver.manualInput = step.input; driver.walk = step.walk; driver.sprint = step.sprint;
            driver.lockTarget = step.target ? controls.target : null; step.enter?.Invoke();
        }
        private static void Check(bool value, string reason) { report.assertions++; if (!value) failures.Add(reason); }
        private static void CaptureReplay(ClipBlendPlayer player)
        {
            if (report == null || report.status != "Running" || index < 0 || index >= steps.Count || steps[index].name != "repeat L1") return;
            if (report.outgoingReplayTime <= 0 && player.TimeFor("L1", false) > 0)
            { report.outgoingReplayTime = (float)player.TimeFor("L1", false); report.incomingReplayTime = (float)player.TimeFor("L1", true); }
        }
        private static void PoseEvaluated(ClipBlendPlayer player) { CaptureReplay(player); Update(); }
        private static void Update()
        {
            if (report == null || report.status != "Running" || !EditorApplication.isPlaying || driver == null || Time.frameCount == lastFrame) return;
            lastFrame = Time.frameCount;
            try
            {
                float dt = Time.deltaTime; report.frames++; report.elapsed += dt; stepTime += dt;
                var player = driver.motionPlayer.Player; if (player == null) return;
                phases.Add(driver.stance + "/" + driver.Phase);
                if (!string.IsNullOrEmpty(driver.motionPlayer.Missing)) missing.Add(driver.stance + "/" + driver.motionPlayer.Missing);
                float error = Mathf.Abs(player.WeightSum - 1); report.maxWeightError = Mathf.Max(report.maxWeightError, error); report.maxVoices = Mathf.Max(report.maxVoices, player.VoiceCount);
                Check(error < 0.002f, "pose weights sum to one"); Check(!float.IsNaN(driver.transform.position.y) && driver.transform.position.y > -1, "finite above-floor motor");
                Check(driver.animator.runtimeAnimatorController == null, "controller remains absent");
                if ((driver.motor.LastCollision & CollisionFlags.Above) != 0)
                { report.ceilingContacts++; Check(driver.motor.VerticalSpeed <= 0, "ceiling clears upward velocity"); }
                if (steps[index].name == "idle jump") report.idleJumpHeight = Mathf.Max(report.idleJumpHeight, driver.transform.position.y - originY);
                if (steps[index].name == "moving jump") report.movingJumpHeight = Mathf.Max(report.movingJumpHeight, driver.transform.position.y - originY);
                if (stepTime >= steps[index].duration) Next();
                else if (report.frames % 60 == 0) SessionState.SetString(Key + "report", $"Running {index + 1}/{steps.Count}: {steps[index].name} / {report.frames} frames");
            }
            catch (Exception e) { failures.Add(e.ToString()); Complete(true); }
        }
        private static void Complete(bool stop)
        {
            if (driver != null && driver.motionPlayer.Player != null) driver.motionPlayer.Player.Evaluated -= PoseEvaluated;
            Check(report.idleJumpHeight > 0.6f && report.movingJumpHeight > 0.6f, "jump gains real height");
            Check(driver.motionPlayer.library != null && EditorJsonUtility.ToJson(driver.motionPlayer.library) == sourceJson, "Play does not mutate source library");
            Check(driver.combat.Current == null, "returns from action to locomotion");
            foreach (WeaponStance set in Enum.GetValues(typeof(WeaponStance)))
                foreach (string phase in new[] { "Idle", "Start", "Move", "Accelerate", "Decelerate", "Stop", "Strafe", "JumpTakeoff", "JumpRise", "JumpApex", "Fall", "Land", "TurnInPlaceRight", "PivotInPlaceLeft" })
                    Check(phases.Contains(set + "/" + phase), "visited " + set + "/" + phase);
            report.status = failures.Count == 0 ? "PASS mechanisms; asset quality pending" : "FAIL";
            report.averageFps = report.frames / Mathf.Max(0.001f, report.elapsed); report.phases = phases.OrderBy(x => x).ToArray(); report.missing = missing.OrderBy(x => x).ToArray(); report.failures = failures.ToArray();
            string json = JsonUtility.ToJson(report, true);
            SessionState.SetString(Key + "report", json);
            // Generated local evidence, deliberately outside Assets and version control.
            string directory = System.IO.Path.GetFullPath(System.IO.Path.Combine(Application.dataPath, "../Library/NoWiresValidation"));
            System.IO.Directory.CreateDirectory(directory);
            System.IO.File.WriteAllText(System.IO.Path.Combine(directory, "play-" + report.targetFps + ".json"), json);
            if (driver != null) { driver.manualInput = Vector2.zero; driver.useManualInput = false; driver.combat.suspended = false; }
            if (controls != null) controls.enabled = true;
            if (temporaryCeiling != null) UnityEngine.Object.Destroy(temporaryCeiling); temporaryCeiling = null;
            Restore(); SessionState.SetBool(Key + "run", false); if (stop) EditorApplication.delayCall += () => EditorApplication.isPlaying = false;
        }
        private static void Restore()
        {
            Application.targetFrameRate = SessionState.GetInt(Key + "oldFps", -1); QualitySettings.vSyncCount = SessionState.GetInt(Key + "oldVsync", 1);
            Application.runInBackground = SessionState.GetBool(Key + "oldBackground", false); Time.timeScale = SessionState.GetFloat(Key + "oldScale", 1);
        }
    }
}
