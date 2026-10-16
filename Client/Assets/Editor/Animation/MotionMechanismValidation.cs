using System;
using System.Collections.Generic;
using System.Linq;
using Afauxzhub.Project.Animation;
using Afauxzhub.Project.Locomotion;
using UnityEditor;
using UnityEngine;

namespace Afauxzhub.Project.Editor.Animation
{
    /// <summary>Play-only terrain/input matrix. Never saves a scene or source configuration.</summary>
    [InitializeOnLoad]
    public static class MotionMechanismValidation
    {
        const string Key = "MYProject.MotionMatrix.";
        [Serializable] public sealed class CaseResult
        {
            public string name;
            public int frames, airborneFrames;
            public float duration, distance, heightDelta, maxHeight, maxYawStep;
            public string[] phases, missing;
        }
        [Serializable] public sealed class TerrainResult
        {
            public string name;
            public int fps, airborneFrames;
            public float travel, heightDelta;
        }
        [Serializable] public sealed class Report
        {
            public string status, boundary;
            public int targetFps, frames, assertions, maxVoices, plannedCases;
            public float elapsed, averageFps, maxWeightError, edgeRetainedSpeed;
            public List<TerrainResult> terrain = new List<TerrainResult>();
            public List<CaseResult> cases = new List<CaseResult>();
            public string[] failures;
        }
        sealed class Step
        {
            public string name; public float duration; public LabInputFrame input;
            public float cameraRate; public Action enter, verify;
        }
        static readonly List<Step> steps = new List<Step>();
        static readonly HashSet<string> errors = new HashSet<string>(), phases = new HashSet<string>(), missing = new HashSet<string>();
        static Report report;
        static CaseResult current;
        static AnimatedCharacterDriver driver;
        static AnimationLabInput controls;
        static AnimationLabCamera camera;
        static GameObject terrainRoot;
        static Vector3 origin, previousPosition, pausePosition;
        static float previousYaw, elapsed, pauseActionTime, edgeSpeed;
        static bool wasGrounded, edgeObserved;
        static int index, lastFrame;
        static string sourceJson;
        static LabCommand pending;
        public static string Status => SessionState.GetString(Key + "status", "Not started");
        static MotionMechanismValidation() { EditorApplication.playModeStateChanged += StateChanged; }
        [MenuItem("Tools/MY Project/Animation/Run Terrain and Input Matrix/30 fps")]
        public static void Run30() => Start(30);
        [MenuItem("Tools/MY Project/Animation/Run Terrain and Input Matrix/60 fps")]
        public static void Run60() => Start(60);
        [MenuItem("Tools/MY Project/Animation/Run Terrain and Input Matrix/120 fps")]
        public static void Run120() => Start(120);
        public static void Start(int fps)
        {
            var scene = UnityEngine.SceneManagement.SceneManager.GetActiveScene();
            if (EditorApplication.isPlayingOrWillChangePlaymode || scene.isDirty || !scene.path.StartsWith("Assets/LocalAnimationLab/", StringComparison.Ordinal))
                throw new InvalidOperationException("Use a clean isolated local scene outside Play.");
            if (UnityEngine.Object.FindObjectsByType<MotionLibraryPlayer>(FindObjectsSortMode.None).Length != 1 || UnityEngine.Object.FindObjectsByType<AnimationLabInput>(FindObjectsSortMode.None).Length != 1 || UnityEngine.Object.FindObjectsByType<AnimationLabCamera>(FindObjectsSortMode.None).Length != 1)
                throw new InvalidOperationException("Expected one no-wires actor, lab input and lab camera.");
            SessionState.SetInt(Key + "fps", fps); SessionState.SetBool(Key + "run", true);
            SessionState.SetInt(Key + "oldFps", Application.targetFrameRate); SessionState.SetInt(Key + "oldVsync", QualitySettings.vSyncCount);
            SessionState.SetFloat(Key + "oldScale", Time.timeScale); SessionState.SetBool(Key + "oldBackground", Application.runInBackground);
            SessionState.SetString(Key + "status", "Starting"); EditorApplication.isPlaying = true;
        }
        static void StateChanged(PlayModeStateChange state)
        {
            if (!SessionState.GetBool(Key + "run", false)) return;
            if (state == PlayModeStateChange.EnteredPlayMode)
            { try { Begin(); } catch (Exception e) { errors.Add(e.ToString()); Finish(true); } }
            if (state == PlayModeStateChange.ExitingPlayMode)
            { errors.Add("Interrupted before completion"); Finish(false); }
        }
        static void Check(bool ok, string reason)
        { report.assertions++; if (!ok) errors.Add((current != null ? current.name + ": " : "") + reason); }
        static GameObject Box(string name, Vector3 position, Vector3 scale, float angle = 0)
        {
            var go = GameObject.CreatePrimitive(PrimitiveType.Cube); go.name = name; go.hideFlags = HideFlags.DontSave;
            go.transform.SetParent(terrainRoot.transform); go.transform.SetPositionAndRotation(position, Quaternion.Euler(angle, 0, 0)); go.transform.localScale = scale;
            return go;
        }
        static void Begin()
        {
            report = new Report { status = "Running", targetFps = SessionState.GetInt(Key + "fps", 60), boundary = "Mechanisms only. Replay uses lab input adapter; physical keyboard/gamepad and missing animation quality are not certified. Dynamic foot locking disabled." };
            errors.Clear(); steps.Clear(); current = null; index = -1; lastFrame = -1;
            Application.targetFrameRate = report.targetFps; QualitySettings.vSyncCount = 0; Time.timeScale = 1; Application.runInBackground = true;
            terrainRoot = new GameObject("Temporary mechanism fixtures (Play only)") { hideFlags = HideFlags.DontSave };
            RunMotorMatrix();
            driver = UnityEngine.Object.FindFirstObjectByType<AnimatedCharacterDriver>();
            controls = driver.GetComponent<AnimationLabInput>(); camera = UnityEngine.Object.FindFirstObjectByType<AnimationLabCamera>();
            driver.motionPlayer.Ensure(); sourceJson = EditorJsonUtility.ToJson(driver.motionPlayer.library);
            driver.cameraReference = camera.transform; camera.externalLook = true; camera.yaw = 0;
            controls.replay = ReadInput;
            Box("Input floor", new Vector3(300, 19.5f, 300), new Vector3(250, 1, 1000));
            Box("Ledge", new Vector3(500, 24.5f, 300), new Vector3(8, 1, 8));
            Box("Ledge landing floor", new Vector3(500, 19.5f, 300), new Vector3(100, 1, 100));
            Box("Live slope", new Vector3(700, 30, 300), new Vector3(12, 1, 60), 30);
            Physics.SyncTransforms();
            BuildInputs(); report.plannedCases = steps.Count;
            driver.FrameCompleted += Tick; Next();
        }
        // Analytic dt sweeps isolate real CharacterController collision behavior from rendering cadence.
        static void RunMotorMatrix()
        {
            foreach (int fps in new[] { 30, 60, 120 })
            foreach (float angle in new[] { 15f, 30f, 44f, 60f })
            foreach (int sign in new[] { -1, 1 })
            {
                var slope = Box("Motor slope", new Vector3(1000, 40, 1000), new Vector3(20, 1, 100), angle);
                var actor = new GameObject("Motor probe") { hideFlags = HideFlags.DontSave };
                var cc = actor.AddComponent<CharacterController>(); cc.height = 2; cc.radius = 0.3f; cc.center = Vector3.up; cc.skinWidth = 0.02f; cc.slopeLimit = 45;
                var motor = actor.AddComponent<CharacterControllerMotor>(); motor.Configure(cc, 20, 2);
                actor.transform.position = slope.transform.TransformPoint(new Vector3(0, 0.5f, 0)) + Vector3.up * 0.1f;
                Physics.SyncTransforms(); float dt = 1f / fps;
                for (int i = 0; i < fps; i++) motor.ApplyDisplacement(Vector3.zero, Quaternion.identity, dt);
                var start = actor.transform.position;
                var result = new TerrainResult { name = angle + "deg " + (sign > 0 ? "down" : "up"), fps = fps };
                for (int i = 0; i < fps * 2; i++)
                {
                    motor.ApplyDisplacement(Vector3.forward * sign * 8 * dt, Quaternion.identity, dt);
                    if (!motor.IsGrounded) result.airborneFrames++;
                }
                result.travel = Mathf.Abs(actor.transform.position.z - start.z); result.heightDelta = actor.transform.position.y - start.y;
                report.terrain.Add(result);
                if (angle <= 45)
                { Check(result.airborneFrames == 0, $"{fps}fps {result.name} stays grounded ({result.airborneFrames})"); Check(result.travel > 8, $"{fps}fps {result.name} traverses"); }
                else if (sign < 0) Check(result.heightDelta < 0.35f, $"{fps}fps steep slope rejects climbing");
                UnityEngine.Object.DestroyImmediate(actor); UnityEngine.Object.DestroyImmediate(slope);
            }
        }
        public static string RunTerrainChecks()
        {
            if (!Application.isPlaying || SessionState.GetBool(Key + "run", false)) throw new InvalidOperationException("Use Play without an active matrix.");
            report = new Report(); current = null; errors.Clear();
            terrainRoot = new GameObject("Temporary terrain checks") { hideFlags = HideFlags.DontSave };
            try { RunMotorMatrix(); report.failures = errors.ToArray(); return JsonUtility.ToJson(report); }
            finally { UnityEngine.Object.DestroyImmediate(terrainRoot); terrainRoot = null; }
        }
        static void Add(string name, float seconds, Vector2 move, int gait = 1, LabCommand command = LabCommand.None, Action enter = null, Action verify = null, float cameraRate = 0)
        { steps.Add(new Step { name = name, duration = seconds, input = new LabInputFrame { move = move, walk = gait == 0, sprint = gait == 2, pressed = command }, enter = enter, verify = verify, cameraRate = cameraRate }); }
        static void ResetAt(Vector3 point)
        {
            driver.enabled = false; var cc = driver.GetComponent<CharacterController>(); cc.enabled = false;
            driver.transform.SetPositionAndRotation(point, Quaternion.identity); cc.enabled = true; driver.enabled = true;
            driver.ClearFacingRequest(); driver.lockTarget = null; camera.yaw = 0; camera.pitch = 20;
            controls.target.gameObject.SetActive(true); controls.target.position = point + Vector3.forward * 60;
            Physics.SyncTransforms();
        }
        static void BuildInputs()
        {
            for (int s = 0; s < 2; s++)
            {
                var stance = (WeaponStance)s;
                Add(stance + "/reset", 0.7f, Vector2.zero, enter: () => { driver.stance = stance; ResetAt(new Vector3(300, 20.1f, 300)); });
                for (int mode = 0; mode < 2; mode++)
                {
                    bool targeting = mode == 1;
                    string prefix = stance + "/" + (targeting ? "Target" : "Free");
                    Add(prefix + "/mode", 0.7f, Vector2.zero, command: targeting ? LabCommand.Target : LabCommand.None, verify: () => Check(driver.Targeting == targeting, "mode applied through input"));
                    for (int gait = 0; gait < 3; gait++)
                    for (int dir = 0; dir < 8; dir++)
                    {
                        float a = dir * Mathf.PI / 4; var move = new Vector2(Mathf.Sin(a), Mathf.Cos(a));
                        Add(prefix + "/gait" + gait + "/direction" + dir, 0.85f, move, gait, verify: () =>
                        {
                            Check(current.distance > 0.1f && driver.Speed > 0.1f, "moves through input/driver/motor");
                            Check(driver.Targeting == targeting, "mode remains valid");
                            if (targeting) Check(Vector3.Dot(new Vector3(driver.motor.Velocity.x, 0, driver.motor.Velocity.z).normalized, new Vector3(move.x, 0, move.y)) > 0.9f, "targeting translation follows camera-relative input");
                        });
                    }
                    for (int from = 0; from < 3; from++) for (int to = 0; to < 3; to++) if (from != to)
                    {
                        Add(prefix + "/shift prepare " + from, 0.8f, Vector2.up, from);
                        Add(prefix + "/shift " + from + "->" + to, 1.2f, Vector2.up, to, verify: () => Check(Mathf.Abs(driver.Speed - driver.TargetSpeed) < 0.1f, "reaches requested gait speed"));
                    }
                    Add(prefix + "/camera clockwise cross180", 1.4f, Vector2.up, cameraRate: 540);
                    Add(prefix + "/camera reverse cross180", 1.4f, Vector2.up, cameraRate: -720);
                    Add(prefix + "/camera pitch high", 0.3f, Vector2.up, enter: () => camera.ApplyLook(new Vector2(0, -1000), 0), verify: () => Check(camera.pitch == 70 && driver.Speed > 0, "high pitch keeps horizontal intent"));
                    Add(prefix + "/camera pitch low", 0.3f, Vector2.up, enter: () => camera.ApplyLook(new Vector2(0, 1000), 0), verify: () => Check(camera.pitch == -10 && driver.Speed > 0, "low pitch keeps horizontal intent"));
                    Add(prefix + "/camera stable recovery", 1.6f, Vector2.up, enter: () => { camera.yaw = 0; camera.pitch = 20; }, verify: () => Check(current.distance > 1, "recovers after camera spin"));
                    Add(prefix + "/rapid reverse", 0.6f, Vector2.down);
                    Add(prefix + "/release in turn", 0.8f, Vector2.zero, verify: () => Check(driver.Speed < 0.01f, "release stops"));
                    Add(prefix + "/jump chain run", 0.8f, Vector2.up);
                    Add(prefix + "/jump chain takeoff", 0.16f, Vector2.up, command: LabCommand.Jump, verify: () => Check(!driver.motor.IsGrounded && driver.motor.VerticalSpeed > 0, "real jump"));
                    Add(prefix + "/jump reverse no second jump", 0.45f, Vector2.down, command: LabCommand.Jump | LabCommand.Light, verify: () => Check(driver.combat.Current == null && driver.motor.VerticalSpeed < 2, "air attack/second jump rejected"));
                    Add(prefix + "/jump land sprint", 1.5f, Vector2.up, 2, verify: () => Check(driver.motor.IsGrounded && phases.Contains("Land"), "lands and recovers"));
                    if (targeting)
                    {
                        Add(prefix + "/target disabled", 0.2f, Vector2.right, enter: () => controls.target.gameObject.SetActive(false), verify: () => Check(!driver.Targeting, "inactive target falls back"));
                        Add(prefix + "/target cleared", 0.3f, Vector2.up, command: LabCommand.Target, enter: () => controls.target.gameObject.SetActive(true));
                    }
                }
                Add(stance + "/slope settle", 0.8f, Vector2.zero, enter: () => ResetAt(new Vector3(700, 36.4f, 290)));
                Add(stance + "/slope downhill sprint", 1.5f, Vector2.up, 2, verify: () => Check(current.airborneFrames == 0 && !phases.Contains("Fall"), "no false fall/land downhill"));
                Add(stance + "/slope jump", 0.3f, Vector2.up, command: LabCommand.Jump, verify: () => Check(current.maxHeight > 0.5f && !driver.motor.IsGrounded, "slope snap does not swallow jump"));
                Add(stance + "/slope landing", 2.2f, Vector2.up, verify: () => Check(driver.motor.IsGrounded && phases.Contains("Land"), "slope landing recovery"));
                foreach (int mode in new[] { 0, 1, 2 })
                {
                    int edgeMode = mode;
                    Add(stance + "/edge settle " + mode, 0.8f, Vector2.zero, enter: () => { ResetAt(new Vector3(500, 25.1f, 299)); edgeObserved = false; edgeSpeed = 0; });
                    Add(stance + "/edge run " + mode, 1.5f, Vector2.up, 2, verify: () => { Check(edgeObserved, "left platform"); Check(edgeSpeed > 5, "retains horizontal momentum at edge"); });
                    Add(stance + "/edge air change " + mode, 0.2f, edgeMode == 0 ? Vector2.zero : Vector2.down, command: edgeMode == 2 ? LabCommand.Target | LabCommand.Jump : LabCommand.Jump, verify: () => Check(driver.motor.VerticalSpeed < 0, "no edge double jump"));
                    Add(stance + "/edge landing " + mode, 2, Vector2.up, verify: () => Check(driver.motor.IsGrounded && driver.transform.position.y < 21, "lands on lower floor"));
                }
            }
            Add("combat reset", 0.8f, Vector2.zero, enter: () => ResetAt(new Vector3(300, 20.1f, 300)));
            Add("input attack", 0.2f, Vector2.up, command: LabCommand.Light, verify: () => Check(driver.combat.Current != null, "attack via adapter"));
            Add("input pause", 0.3f, Vector2.up, command: LabCommand.Pause, enter: () => { pausePosition = driver.transform.position; pauseActionTime = driver.combat.TimeInAction; }, verify: () => { Check(driver.combat.suspended, "paused"); Check(Vector3.Distance(driver.transform.position, pausePosition) < 0.01f && Mathf.Abs(driver.combat.TimeInAction - pauseActionTime) < 0.04f, "pause freezes motor and action"); });
            Add("input resume and hit", 0.2f, Vector2.up, command: LabCommand.Pause | LabCommand.Hit);
            Add("hit rejects skill and jump", 0.15f, Vector2.up, command: LabCommand.Skill | LabCommand.Jump, verify: () => Check(driver.combat.Current != null && driver.combat.Current.kind == ActionKind.LightHit && driver.motor.IsGrounded, "hit permission retained"));
            Add("return move", 1.5f, Vector2.up, verify: () => Check(driver.combat.Current == null && driver.Speed > 1, "action returns to locomotion"));
            Add("final idle", 0.8f, Vector2.zero, verify: () => Check(driver.Phase.ToString() == "Idle", "no stuck state"));
        }
        static LabInputFrame ReadInput()
        {
            if (index < 0 || index >= steps.Count) return default;
            var frame = steps[index].input; frame.pressed = pending; pending = LabCommand.None; return frame;
        }
        static void Next()
        {
            if (current != null)
            {
                current.phases = phases.OrderBy(x => x).ToArray(); current.missing = missing.OrderBy(x => x).ToArray();
                current.heightDelta = driver.transform.position.y - origin.y;
                steps[index].verify?.Invoke(); report.cases.Add(current);
            }
            index++; if (index >= steps.Count) { Finish(true); return; }
            current = new CaseResult { name = steps[index].name }; phases.Clear(); missing.Clear(); elapsed = 0;
            steps[index].enter?.Invoke(); origin = previousPosition = driver.transform.position; previousYaw = driver.transform.eulerAngles.y;
            wasGrounded = driver.motor.IsGrounded; pending = steps[index].input.pressed;
        }
        static void Tick(AnimatedCharacterDriver actor)
        {
            if (report == null || report.status != "Running" || Time.frameCount == lastFrame) return;
            lastFrame = Time.frameCount;
            try
            {
                var player = driver.motionPlayer.Player;
                float dt = Time.deltaTime; elapsed += dt; report.elapsed += dt; report.frames++; current.frames++; current.duration += dt;
                var position = driver.transform.position; float yaw = driver.transform.eulerAngles.y;
                current.distance += new Vector2(position.x - previousPosition.x, position.z - previousPosition.z).magnitude;
                current.maxHeight = Mathf.Max(current.maxHeight, position.y - origin.y);
                current.maxYawStep = Mathf.Max(current.maxYawStep, Mathf.Abs(Mathf.DeltaAngle(previousYaw, yaw)));
                if (!driver.motor.IsGrounded) current.airborneFrames++;
                phases.Add(driver.Phase.ToString()); if (!string.IsNullOrEmpty(driver.motionPlayer.Missing)) missing.Add(driver.motionPlayer.Missing);
                if (current.name.Contains("/edge run") && !driver.motor.IsGrounded && wasGrounded) { edgeObserved = true; edgeSpeed = new Vector2(driver.motor.Velocity.x, driver.motor.Velocity.z).magnitude; report.edgeRetainedSpeed = edgeSpeed; }
                if (current.name.Contains("/edge run") && edgeObserved && !driver.motor.IsGrounded) edgeSpeed = Mathf.Min(edgeSpeed, new Vector2(driver.motor.Velocity.x, driver.motor.Velocity.z).magnitude);
                if (current.name.Contains("/edge run") && !driver.motor.IsGrounded) Check(driver.combat.LocomotionInputBlocked, "departure-frame airborne gate closes before next input");
                wasGrounded = driver.motor.IsGrounded;
                float weightError = Mathf.Abs(player.WeightSum - 1); report.maxWeightError = Mathf.Max(report.maxWeightError, weightError); report.maxVoices = Mathf.Max(report.maxVoices, player.VoiceCount);
                Check(weightError < 0.002f && player.VoiceCount <= 24, "bounded normalized graph");
                Check(!float.IsNaN(position.x + position.y + position.z) && position.y > 10 && position.sqrMagnitude < 1e8f, "finite collision-resolved position");
                Check(driver.animator.runtimeAnimatorController == null, "no Controller");
                Check(current.maxYawStep < 95, "no one-frame yaw teleport");
                camera.ApplyLook(new Vector2(steps[index].cameraRate * dt / camera.sensitivity, 0), 0);
                previousPosition = position; previousYaw = yaw;
                if (elapsed >= steps[index].duration) Next();
                else if (report.frames % 60 == 0) SessionState.SetString(Key + "status", $"Running {index + 1}/{steps.Count}: {current.name}");
            }
            catch (Exception e) { errors.Add(e.ToString()); Finish(true); }
        }
        static void Finish(bool stop)
        {
            if (report == null) report = new Report();
            if (driver != null)
            {
                driver.FrameCompleted -= Tick;
                Check(EditorJsonUtility.ToJson(driver.motionPlayer.library) == sourceJson, "source library unchanged");
                driver.combat.suspended = false; driver.manualInput = Vector2.zero;
            }
            if (controls != null) controls.replay = null;
            if (camera != null) camera.externalLook = false;
            Check(report.cases.Count == report.plannedCases && report.plannedCases > 150, "all matrix cases completed");
            report.status = errors.Count == 0 ? "PASS mechanisms; visual assets pending" : "FAIL";
            report.failures = errors.ToArray(); report.averageFps = report.frames / Mathf.Max(0.001f, report.elapsed);
            string json = JsonUtility.ToJson(report, true); SessionState.SetString(Key + "status", json);
            var path = System.IO.Path.GetFullPath(System.IO.Path.Combine(Application.dataPath, "../Library/NoWiresValidation"));
            System.IO.Directory.CreateDirectory(path); System.IO.File.WriteAllText(System.IO.Path.Combine(path, "matrix-" + report.targetFps + ".json"), json);
            if (terrainRoot != null) UnityEngine.Object.Destroy(terrainRoot);
            Application.targetFrameRate = SessionState.GetInt(Key + "oldFps", -1); QualitySettings.vSyncCount = SessionState.GetInt(Key + "oldVsync", 1);
            Time.timeScale = SessionState.GetFloat(Key + "oldScale", 1); Application.runInBackground = SessionState.GetBool(Key + "oldBackground", false);
            SessionState.SetBool(Key + "run", false); if (stop) EditorApplication.delayCall += () => EditorApplication.isPlaying = false;
        }
    }
}
