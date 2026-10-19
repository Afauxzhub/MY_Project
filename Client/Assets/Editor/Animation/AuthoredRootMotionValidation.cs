using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Afauxzhub.CharacterLocomotion;
using Afauxzhub.Project.Animation;
using UnityEditor;
using UnityEngine;
using Object = UnityEngine.Object;

namespace Afauxzhub.Project.Editor.Animation
{
    /// <summary>Uses the scene's real clips/configuration, never substitutes synthetic animation.</summary>
    [InitializeOnLoad]
    public static class AuthoredRootMotionValidation
    {
        const string Key = "MYProject.AuthoredRoot.";
        [Serializable] public sealed class Case
        {
            public string name; public int frames, rootFrames; public float elapsed, travel, yaw, lastSpeed, headingError, maxStep, maxDeltaTime, maxStepDeltaTime, maxRootStep, maxSpeed;
            public string[] actions, missing;
            public List<string> diagnostics = new List<string>();
        }
        [Serializable] public sealed class Report
        {
            public string status, boundary = "Real assigned clips. Missing assets, physical input feel and dynamic foot locking are not certified.";
            public int targetFps, frames, assertions; public float elapsed, averageFps;
            public List<Case> cases = new List<Case>(); public string[] failures;
        }
        sealed class Step { public string name; public float seconds; public LabInputFrame input; public Action enter, verify; public bool capture; }
        static readonly List<Step> steps = new List<Step>();
        static readonly HashSet<string> errors = new HashSet<string>(), actions = new HashSet<string>(), missing = new HashSet<string>();
        static readonly List<Object> temporary = new List<Object>();
        static AnimatedCharacterDriver driver; static AnimationLabInput input; static AnimationLabCamera camera;
        static Report report; static Case current; static int index; static float elapsed, lastYaw, pausedTime;
        static Vector3 lastPosition, pausedPosition; static int captures; static LabCommand pending;
        static string sourceLibrary, sourceProfile; static GameObject wall;
        public static string Status => SessionState.GetString(Key + "status", "Not started");
        static AuthoredRootMotionValidation() { EditorApplication.playModeStateChanged += StateChanged; }
        [MenuItem("Tools/MY Project/Animation/Run Authored Root Motion Sweep/30 fps")] public static void Run30() => Start(30);
        [MenuItem("Tools/MY Project/Animation/Run Authored Root Motion Sweep/60 fps")] public static void Run60() => Start(60);
        [MenuItem("Tools/MY Project/Animation/Run Authored Root Motion Sweep/120 fps")] public static void Run120() => Start(120);
        public static void Start(int fps)
        {
            var scene = UnityEngine.SceneManagement.SceneManager.GetActiveScene();
            if (EditorApplication.isPlayingOrWillChangePlaymode || scene.isDirty || !scene.path.StartsWith("Assets/LocalAnimationLab/", StringComparison.Ordinal))
                throw new InvalidOperationException("Use a clean isolated Root Motion lab outside Play.");
            var players = Object.FindObjectsByType<MotionLibraryPlayer>(FindObjectsSortMode.None);
            if (players.Length != 1 || players[0].library == null || players[0].library.entries.Count(e => e.clip != null && e.rootMotion != null && e.rootMotion.enabled) < 4)
                throw new InvalidOperationException("Expected one actor with assigned native root trajectories.");
            var actor = players[0].driver;
            if (actor == null || actor.animator == null || actor.motor == null || actor.combat == null || actor.profile == null
                || actor.GetComponent<AnimationLabInput>() == null || Object.FindObjectsByType<AnimationLabCamera>(FindObjectsSortMode.None).Length != 1)
                throw new InvalidOperationException("Assign the actor, Animator, Motor, combat profile, lab input and exactly one lab camera.");
            if (fps != 30 && fps != 60 && fps != 120) throw new ArgumentOutOfRangeException(nameof(fps));
            RootMotionGuards.Validate(players[0]);
            foreach (var stance in new[] { WeaponStance.Sheathed, WeaponStance.Drawn })
                foreach (var slot in new[] { MotionSlot.Idle, MotionSlot.Run, MotionSlot.Start, MotionSlot.StopLeft })
                    if (players[0].library.Find(stance, slot, MotionGait.Run, slot == MotionSlot.Start ? MotionDirection.Forward : MotionDirection.Any, out _) == null)
                        throw new InvalidOperationException("This sweep requires both sets of Idle/Run/Start/StopLeft. Missing " + stance + "/" + slot);
            foreach (var id in new[] { "L1", "L2", "L3", "L4", "Dodge", "LightHit" })
                if (!players[0].driver.profile.actions.Any(a => a != null && a.id == id && a.clip != null && a.movement == MovementAuthority.RootMotion))
                    throw new InvalidOperationException("Authored root action required: " + id);
            SessionState.SetInt(Key + "fps", fps); SessionState.SetBool(Key + "run", true);
            SessionState.SetInt(Key + "oldFps", Application.targetFrameRate); SessionState.SetInt(Key + "oldVsync", QualitySettings.vSyncCount);
            SessionState.SetFloat(Key + "oldScale", Time.timeScale); SessionState.SetBool(Key + "oldBackground", Application.runInBackground);
            SessionState.SetString(Key + "status", "Starting"); EditorApplication.isPlaying = true;
        }
        static void StateChanged(PlayModeStateChange state)
        {
            if (!SessionState.GetBool(Key + "run", false)) return;
            if (state == PlayModeStateChange.EnteredPlayMode) { try { Begin(); } catch (Exception e) { errors.Add(e.ToString()); Finish(true); } }
            if (state == PlayModeStateChange.ExitingPlayMode) { errors.Add("Interrupted before completion"); Finish(false); }
        }
        static void Check(bool ok, string why) { report.assertions++; if (!ok) errors.Add(current?.name + ": " + why); }
        static string ProfileJson() => EditorJsonUtility.ToJson(driver.profile) + string.Concat(driver.profile.actions.Select(EditorJsonUtility.ToJson));
        static ActionDefinition Action(string id) => driver.profile.actions.First(a => a.id == id);
        static GameObject Box(Vector3 point, Vector3 scale)
        {
            var box = GameObject.CreatePrimitive(PrimitiveType.Cube); box.hideFlags = HideFlags.DontSave;
            box.name = "Authored root collision fixture"; box.transform.position = point; box.transform.localScale = scale; temporary.Add(box); return box;
        }
        static void Reset(WeaponStance stance)
        {
            driver.combat.enabled = false; driver.combat.enabled = true; driver.combat.suspended = false;
            driver.enabled = false; var cc = driver.GetComponent<CharacterController>(); cc.enabled = false;
            driver.transform.SetPositionAndRotation(new Vector3(3000, 0.1f, 0), Quaternion.identity); cc.enabled = true;
            driver.stance = stance; driver.lockTarget = null; driver.enabled = true; driver.ClearFacingRequest();
            camera.yaw = 0; camera.pitch = 15; Physics.SyncTransforms();
        }
        static void Add(string name, float seconds, Vector2 move = default, LabCommand command = LabCommand.None, bool sprint = false, Action enter = null, Action verify = null, bool capture = false)
            => steps.Add(new Step { name = name, seconds = seconds, input = new LabInputFrame { move = move, pressed = command, sprint = sprint }, enter = enter, verify = verify, capture = capture });
        static void Begin()
        {
            report = new Report { targetFps = SessionState.GetInt(Key + "fps", 60) }; errors.Clear(); temporary.Clear(); steps.Clear(); index = -1; current = null;
            Application.targetFrameRate = report.targetFps; QualitySettings.vSyncCount = 0; Application.runInBackground = true; Time.timeScale = 1;
            driver = Object.FindFirstObjectByType<AnimatedCharacterDriver>(); input = driver.GetComponent<AnimationLabInput>(); camera = Object.FindFirstObjectByType<AnimationLabCamera>();
            camera.externalLook = true; input.showHUD = false; driver.cameraReference = camera.transform;
            driver.motionPlayer.Ensure(); sourceLibrary = EditorJsonUtility.ToJson(driver.motionPlayer.library); sourceProfile = ProfileJson();
            Box(new Vector3(3000, -0.5f, 100), new Vector3(400, 1, 500));
            wall = Box(new Vector3(3000, 2, 5), new Vector3(12, 5, 0.5f)); wall.SetActive(false);
            var target = new GameObject("Authored root target fixture") { hideFlags = HideFlags.DontSave };
            target.transform.position = new Vector3(3000, 0, 15); temporary.Add(target);
            foreach (var set in new[] { WeaponStance.Sheathed, WeaponStance.Drawn })
            {
                var stance = set; string p = stance + "/"; Vector2 forward = Vector2.up;
                Add(p + "reset", 0.5f, enter: () => Reset(stance));
                Add(p + "idle", 0.5f, verify: () => Check(driver.Phase == LocomotionPhase.Idle && current.travel < 0.02f, "idle does not drift or play a false stop"), capture: true);
                Add(p + "start-run", 2.5f, forward, verify: () => { Check(current.rootFrames > 10, "real root requested"); Check(Mathf.Abs(current.lastSpeed - driver.profile.Set(stance).movement.runSpeed) < 0.7f, "authored stride speed matches run tuning"); }, capture: true);
                Add(p + "arc-right", 3f, new Vector2(0.7071f, 0.7071f), verify: () => Check(Mathf.Abs(driver.HeadingError) < 15, "continuous arc catches 45 degree heading"), capture: true);
                Add(p + "arc-left-return", 3f, forward, verify: () => Check(Mathf.Abs(driver.HeadingError) < 15, "arc returns to heading"));
                Add(p + "sprint", 2f, forward, sprint: true, verify: () => Check(current.lastSpeed > driver.profile.Set(stance).movement.runSpeed * 1.1f, "sprint requests higher actual root speed"));
                Add(p + "stop", 1.8f, verify: () => Check(driver.Phase == LocomotionPhase.Idle && current.lastSpeed < 0.05f, "stop settles without residual motion"), capture: true);
                Add(p + "run-before-attack", 1.2f, forward);
                Add(p + "attack-return", Action("L1").duration + 1.1f, forward, LabCommand.Light,
                    verify: () => { Check(actions.Contains("L1"), "attack accepted from movement"); Check(driver.combat.Current == null && current.lastSpeed > 1, "returns to real root locomotion"); }, capture: true);
                Add(p + "combo-L1", Action("L1").duration * 0.65f, forward, LabCommand.Light, verify: () => Check(actions.Contains("L1"), "L1 observed"));
                Add(p + "combo-L2", Action("L2").duration * 0.65f, forward, LabCommand.Light, verify: () => Check(actions.Contains("L2"), "L2 observed"), capture: true);
                Add(p + "combo-L3", Action("L3").duration * 0.65f, forward, LabCommand.Light, verify: () => Check(actions.Contains("L3"), "L3 observed"));
                Add(p + "combo-L4-return", Action("L4").duration + 1.1f, forward, LabCommand.Light, verify: () => { Check(actions.Contains("L4"), "L4 observed"); Check(driver.combat.Current == null && current.lastSpeed > 1, "combo returns to moving"); }, capture: true);
                Add(p + "attack-before-dodge", Action("L1").duration * 0.65f, forward, LabCommand.Light);
                Add(p + "recovery-cancel-dodge", Action("Dodge").duration + 1.1f, forward, LabCommand.Dodge, verify: () => { Check(actions.Contains("Dodge"), "ATK-05 recovery dodge accepted"); Check(driver.combat.Current == null, "dodge ends"); }, capture: true);
                Add(p + "attack-before-hit", Action("L1").duration * 0.25f, forward, LabCommand.Light);
                Add(p + "hit-interrupt", 0.35f, forward, LabCommand.Hit, verify: () => Check(driver.combat.Current == Action("LightHit"), "resolved hit interrupts attack"), capture: true);
                Add(p + "hit-reject-attack", 0.3f, forward, LabCommand.Light, verify: () => Check(driver.combat.Current == Action("LightHit"), "hit-stun rejects ordinary action"));
                Add(p + "hit-return", Action("LightHit").duration + 1.1f, forward, verify: () => Check(driver.combat.Current == null && current.lastSpeed > 1, "hit returns to root movement"));
                Add(p + "attack-before-pause", 0.25f, forward, LabCommand.Light);
                Add(p + "pause", 0.4f, forward, LabCommand.Pause, enter: () => { pausedPosition = driver.transform.position; pausedTime = driver.combat.TimeInAction; },
                    verify: () => Check(Vector3.Distance(driver.transform.position, pausedPosition) < 0.001f && Mathf.Abs(driver.combat.TimeInAction - pausedTime) < 0.001f, "pause holds root and action clock"));
                Add(p + "resume-return", Action("L1").duration + 1.1f, forward, LabCommand.Pause, verify: () => Check(driver.combat.Current == null, "resume finishes naturally"));
                Add(p + "switch-running", 1.2f, forward, LabCommand.ForceStance, verify: () => Check(driver.stance != stance && current.lastSpeed > 1, "F2 lab set switch while moving"), capture: true);
                Add(p + "switch-stop", 1.8f, verify: () => Check(driver.Phase == LocomotionPhase.Idle, "other set stops"));
                Add(p + "target-missing-move", 1.5f, Vector2.right, enter: () => { Reset(stance); driver.lockTarget = target.transform; },
                    verify: () => {
                        Check(current.travel > 1 && current.lastSpeed > 1, "targeting still translates with available poses");
                        if (driver.motionPlayer.Missing.Contains("→ Idle")) Check(driver.motionPlayer.RootFrame.positionWeight < 0.999f,
                            "missing targeting pose does not lock procedural movement");
                    });
                Add(p + "target-return-free", 1.2f, forward, enter: () => driver.lockTarget = null,
                    verify: () => Check(driver.Mode == MotionMode.Free && current.lastSpeed > 1 && current.rootFrames > 5, "returns from missing-pose fallback to real root movement"));
            }
            Add("collision/reset", 0.5f, enter: () => { Reset(WeaponStance.Sheathed); wall.SetActive(true); Physics.SyncTransforms(); });
            Add("collision/blocked", 3f, Vector2.up, verify: () => Check(driver.transform.position.z < 5 && current.lastSpeed < 0.05f, "real run stopped by wall"));
            Add("collision/released", 1.5f, Vector2.up, enter: () => wall.SetActive(false), verify: () => Check(current.travel > 1 && current.maxSpeed < 10, "no root debt after unblock"));
            input.replay = Read; driver.FrameCompleted += Tick; Next();
        }
        static LabInputFrame Read() { var result = steps[index].input; result.pressed = pending; pending = LabCommand.None; return result; }
        static void Next()
        {
            if (current != null) { steps[index].verify?.Invoke(); current.actions = actions.ToArray(); current.missing = missing.ToArray(); report.cases.Add(current); }
            if (++index >= steps.Count) { Finish(true); return; }
            current = new Case { name = steps[index].name }; elapsed = 0; captures = 0; actions.Clear(); missing.Clear();
            steps[index].enter?.Invoke(); lastPosition = driver.transform.position; lastYaw = driver.transform.eulerAngles.y;
            pending = steps[index].input.pressed; SessionState.SetString(Key + "status", $"Running {index + 1}/{steps.Count}: {current.name}");
        }
        static void Tick(AnimatedCharacterDriver actor)
        {
            try
            {
                float dt = Time.deltaTime; elapsed += dt; report.elapsed += dt; current.elapsed += dt; report.frames++; current.frames++;
                var position = driver.transform.position; var step = position - lastPosition; float planar = new Vector2(step.x, step.z).magnitude;
                current.travel += planar; current.lastSpeed = new Vector2(driver.motor.Velocity.x, driver.motor.Velocity.z).magnitude;
                current.yaw += Mathf.DeltaAngle(lastYaw, driver.transform.eulerAngles.y); current.headingError = driver.HeadingError; current.maxStep = Mathf.Max(current.maxStep, step.magnitude);
                current.maxDeltaTime = Mathf.Max(current.maxDeltaTime, dt);
                current.maxRootStep = Mathf.Max(current.maxRootStep, driver.motionPlayer.RootFrame.localDelta.magnitude);
                current.maxSpeed = Mathf.Max(current.maxSpeed, planar / Mathf.Max(0.00001f, dt));
                if (step.magnitude >= current.maxStep) current.maxStepDeltaTime = dt;
                if ((index <= 1 && planar > 0.001f || step.magnitude >= 0.8f) && current.diagnostics.Count < 60)
                    current.diagnostics.Add($"dt={dt:F5} step={step} root={driver.motionPlayer.RootFrame.localDelta} phase={driver.Phase} speed={driver.Speed:F3} input={driver.manualInput} key={driver.motionPlayer.Player.Key}\n{driver.motionPlayer.Player.Describe()}");
                if (driver.motionPlayer.RootFrame.localDelta.sqrMagnitude > 0.0000001f) current.rootFrames++;
                if (driver.combat.Current != null) actions.Add(driver.combat.Current.id);
                if (!string.IsNullOrEmpty(driver.motionPlayer.Missing)) missing.Add(driver.motionPlayer.Missing);
                Check(RootMotionSettings.Finite(position.sqrMagnitude) && position.y > -1, "finite grounded position");
                Check(driver.motionPlayer.Player.VoiceCount <= 24 && Mathf.Abs(driver.motionPlayer.Player.WeightSum - 1) < 0.003f, "bounded normalized pose");
                // Wall-clock hitches legitimately cover more distance; catch debt on the following
                // short frame instead. Real assigned clips here must remain below 30 m/s.
                Check(step.magnitude < 30 * dt + 0.03f, "no displacement spike relative to current frame duration");
                Check(string.IsNullOrEmpty(driver.motionPlayer.RootFrame.problem), "no root data error");
                Check(driver.animator.runtimeAnimatorController == null && !driver.animator.applyRootMotion, "Motor remains sole root owner");
                float[] captureTimes = { 0.03f, 0.10f, 0.20f, 0.65f };
                if (captures < captureTimes.Length && report.targetFps == 60 && steps[index].capture && elapsed >= Mathf.Min(captureTimes[captures], steps[index].seconds * 0.9f))
                {
                    string folder = Path.GetFullPath(Path.Combine(Application.dataPath, "../Library/NoWiresValidation/AuthoredCaptures")); Directory.CreateDirectory(folder);
                    ScreenCapture.CaptureScreenshot(Path.Combine(folder, index.ToString("D2") + "-" + current.name.Replace('/', '-') + "-" + captures + ".png")); captures++;
                }
                lastPosition = position; lastYaw = driver.transform.eulerAngles.y;
                if (elapsed >= steps[index].seconds) Next();
            }
            catch (Exception e) { errors.Add(e.ToString()); Finish(true); }
        }
        static void Finish(bool stop)
        {
            if (report == null) report = new Report();
            try
            {
                if (driver != null)
                {
                    driver.FrameCompleted -= Tick;
                    if (sourceLibrary != null) Check(EditorJsonUtility.ToJson(driver.motionPlayer.library) == sourceLibrary, "source library unchanged");
                    if (sourceProfile != null) Check(ProfileJson() == sourceProfile, "source action configurations unchanged");
                    if (driver.combat != null) driver.combat.suspended = false;
                }
                if (input != null) input.replay = null;
                Check(report.cases.Count == steps.Count && steps.Count > 40, "all real-clip scenarios completed");
                report.failures = errors.ToArray(); report.status = errors.Count == 0 ? "PASS assigned-root transitions; missing assets and final visual polish excluded" : "FAIL";
                report.averageFps = report.frames / Mathf.Max(0.001f, report.elapsed);
                string json = JsonUtility.ToJson(report, true); SessionState.SetString(Key + "status", json);
                string folder = Path.GetFullPath(Path.Combine(Application.dataPath, "../Library/NoWiresValidation")); Directory.CreateDirectory(folder); File.WriteAllText(Path.Combine(folder, "authored-root-" + report.targetFps + ".json"), json);
            }
            finally
            {
                // Even a report IO/fixture failure must not leave the user's timing settings changed.
                foreach (var value in temporary) if (value != null) Object.Destroy(value); temporary.Clear();
                Application.targetFrameRate = SessionState.GetInt(Key + "oldFps", -1); QualitySettings.vSyncCount = SessionState.GetInt(Key + "oldVsync", 1);
                Time.timeScale = SessionState.GetFloat(Key + "oldScale", 1); Application.runInBackground = SessionState.GetBool(Key + "oldBackground", false);
                SessionState.SetBool(Key + "run", false); if (stop) EditorApplication.delayCall += () => EditorApplication.isPlaying = false;
            }
        }
    }
}
