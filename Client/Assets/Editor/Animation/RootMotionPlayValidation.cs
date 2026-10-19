using System;
using System.Collections.Generic;
using System.Linq;
using Afauxzhub.Project.Animation;
using UnityEditor;
using UnityEngine;
using Object = UnityEngine.Object;

namespace Afauxzhub.Project.Editor.Animation
{
    /// <summary>Real PlayerLoop/CharacterController tests. All fixtures exist only during Play.</summary>
    [InitializeOnLoad]
    public static class RootMotionPlayValidation
    {
        const string Key = "MYProject.RootMotionSweep.";
        [Serializable] public sealed class Result
        {
            public string name; public int frames; public float elapsed, distance, height, yaw;
        }
        [Serializable] public sealed class Report
        {
            public string status; public int targetFps, frames, assertions; public float elapsed, averageFps;
            public List<Result> cases = new List<Result>(); public string[] failures;
        }
        sealed class Step { public string name; public float seconds; public LabInputFrame input; public Action enter, verify; }
        static readonly List<Step> steps = new List<Step>();
        static readonly List<Object> temporary = new List<Object>();
        static readonly HashSet<string> failures = new HashSet<string>();
        static AnimatedCharacterDriver driver;
        static AnimationLabInput input;
        static Report report;
        static Result current;
        static int index;
        static float elapsed, lastYaw;
        static Vector3 lastPosition, origin, pausePosition;
        static LabCommand pending;
        static RootMotionTrack runTrack;
        static AnimationClip run, idle, rotate, lift;
        static ActionDefinition attack, reaction;
        static GameObject wall;
        static string sourceJson, profileJson;
        static float bridgeDistance;
        static CharacterAnimationProfile sourceProfile;
        public static string Status => SessionState.GetString(Key + "status", "Not started");
        static RootMotionPlayValidation() { EditorApplication.playModeStateChanged += StateChanged; }
        [MenuItem("Tools/MY Project/Animation/Run Root Motion Sweep/30 fps")] public static void Run30() => Start(30);
        [MenuItem("Tools/MY Project/Animation/Run Root Motion Sweep/60 fps")] public static void Run60() => Start(60);
        [MenuItem("Tools/MY Project/Animation/Run Root Motion Sweep/120 fps")] public static void Run120() => Start(120);
        public static void Start(int fps)
        {
            var scene = UnityEngine.SceneManagement.SceneManager.GetActiveScene();
            if (EditorApplication.isPlayingOrWillChangePlaymode || scene.isDirty || !scene.path.StartsWith("Assets/LocalAnimationLab/", StringComparison.Ordinal))
                throw new InvalidOperationException("Use a clean isolated lab scene, outside Play.");
            if (Object.FindObjectsByType<MotionLibraryPlayer>(FindObjectsSortMode.None).Length != 1) throw new InvalidOperationException("Expected exactly one no-wires actor.");
            SessionState.SetInt(Key + "fps", fps); SessionState.SetBool(Key + "run", true);
            SessionState.SetInt(Key + "oldFps", Application.targetFrameRate); SessionState.SetInt(Key + "oldVsync", QualitySettings.vSyncCount);
            SessionState.SetFloat(Key + "oldScale", Time.timeScale); SessionState.SetBool(Key + "oldBackground", Application.runInBackground);
            SessionState.SetString(Key + "status", "Starting"); EditorApplication.isPlaying = true;
        }
        static void StateChanged(PlayModeStateChange state)
        {
            if (!SessionState.GetBool(Key + "run", false)) return;
            if (state == PlayModeStateChange.EnteredPlayMode)
            { try { Begin(); } catch (Exception e) { failures.Add(e.ToString()); Finish(true); } }
            if (state == PlayModeStateChange.ExitingPlayMode) { failures.Add("Interrupted"); Finish(false); }
        }
        static T Keep<T>(T value) where T : Object { value.hideFlags = HideFlags.DontSave; temporary.Add(value); return value; }
        static void Check(bool ok, string reason) { report.assertions++; if (!ok) failures.Add(current?.name + ": " + reason); }
        static GameObject Box(Vector3 position, Vector3 scale, float pitch = 0)
        {
            var go = Keep(GameObject.CreatePrimitive(PrimitiveType.Cube)); go.name = "Root Motion fixture";
            go.transform.SetPositionAndRotation(position, Quaternion.Euler(pitch, 0, 0)); go.transform.localScale = scale; return go;
        }
        static void ResetAt(Vector3 position)
        {
            driver.combat.enabled = false; driver.combat.enabled = true; driver.combat.suspended = false;
            var cc = driver.GetComponent<CharacterController>(); cc.enabled = false; driver.transform.SetPositionAndRotation(position, Quaternion.identity); cc.enabled = true;
            driver.enabled = false; driver.enabled = true; driver.lockTarget = null;
            driver.motor.Configure(cc, 20, 2); driver.ClearFacingRequest();
        }
        static void Begin()
        {
            failures.Clear(); temporary.Clear(); steps.Clear(); index = -1; current = null;
            report = new Report { status = "Running", targetFps = SessionState.GetInt(Key + "fps", 60) };
            Application.targetFrameRate = report.targetFps; QualitySettings.vSyncCount = 0; Application.runInBackground = true; Time.timeScale = 1;
            driver = Object.FindFirstObjectByType<AnimatedCharacterDriver>(); input = driver.GetComponent<AnimationLabInput>();
            driver.cameraReference = null; driver.useManualInput = true; input.showHUD = false;
            driver.motionPlayer.Ensure(); sourceJson = EditorJsonUtility.ToJson(driver.motionPlayer.library);
            sourceProfile = driver.profile; profileJson = EditorJsonUtility.ToJson(sourceProfile);
            driver.profile = Keep(Object.Instantiate(sourceProfile)); driver.combat.profile = driver.profile;
            run = Keep(RootMotionValidation.Clip()); idle = Keep(RootMotionValidation.Clip(0));
            rotate = Keep(RootMotionValidation.Clip(0, 90)); lift = Keep(RootMotionValidation.Clip(0, 0, 1));
            var lib = driver.motionPlayer.WorkingLibrary; runTrack = RootMotionBaker.Bake(lib.model, run);
            lib.defaultBlend = 0; lib.overrides.Clear(); lib.templates = null;
            foreach (var entry in lib.entries)
            {
                bool moving = entry.slot == MotionSlot.Run || entry.slot == MotionSlot.Walk || entry.slot == MotionSlot.Sprint || entry.slot >= MotionSlot.ArcLeft && entry.slot <= MotionSlot.SprintRight
                    || entry.slot >= MotionSlot.StrafeForward && entry.slot <= MotionSlot.StrafeBackRight;
                entry.clip = moving ? run : idle; entry.rootMotion = new RootMotionSettings { enabled = moving, track = moving ? runTrack : null };
                entry.inPoint = 0; entry.outPoint = 1; entry.speed = 1; entry.phaseOffset = 0; entry.matchPlaybackToSpeed = false; entry.stageSeconds = 0;
            }
            attack = Keep(ScriptableObject.CreateInstance<ActionDefinition>()); attack.id = "Root fixture attack"; attack.kind = ActionKind.LightAttack;
            attack.clip = run; attack.duration = 1; attack.blendIn = attack.blendOut = 0; attack.movement = MovementAuthority.RootMotion;
            attack.rootMotion = new RootMotionSettings { enabled = true, track = runTrack };
            reaction = Keep(ScriptableObject.CreateInstance<ActionDefinition>()); reaction.id = "Root fixture reaction"; reaction.kind = ActionKind.LightHit; reaction.clip = idle; reaction.duration = 0.6f; reaction.blendIn = reaction.blendOut = 0;
            driver.profile.actions = new List<ActionDefinition> { attack, reaction };
            Box(new Vector3(1200, 19.5f, 0), new Vector3(100, 1, 200));
            wall = Box(new Vector3(1200, 22, 4), new Vector3(8, 5, 0.5f)); wall.SetActive(false);
            Box(new Vector3(1400, 19.5f, 0), new Vector3(30, 1, 30), 30);
            Box(new Vector3(1500, 14.5f, 0), new Vector3(40, 1, 60));
            Box(new Vector3(1500, 19.5f, 0), new Vector3(10, 1, 4));
            ResetAt(new Vector3(1200, 20.1f, 0));
            void Add(string name, float seconds, Vector2 move = default, LabCommand command = LabCommand.None, Action enter = null, Action verify = null)
                => steps.Add(new Step { name = name, seconds = seconds, input = new LabInputFrame { move = move, pressed = command }, enter = enter, verify = verify });
            Add("settle", 0.5f);
            Add("continuous root loops", 3.2f, Vector2.up, verify: () => Check(current.distance > 5 && current.distance < 8, "root cycles travel without wrap jump"));
            Add("stop", 0.7f);
            Add("second stance loops", 1.5f, Vector2.up, LabCommand.ForceStance, verify: () => Check(current.distance > 2, "second stance root path"));
            Add("pause movement", 0.35f, Vector2.up, LabCommand.Pause, enter: () => pausePosition = driver.transform.position, verify: () => Check(Vector3.Distance(pausePosition, driver.transform.position) < 0.001f, "pause holds position"));
            Add("resume movement", 0.8f, Vector2.up, LabCommand.Pause, verify: () => Check(current.distance > 1 && current.distance < 2, "resume without catch-up"));
            Add("action settle", 0.8f);
            Add("complete action endpoint", 1.3f, command: LabCommand.Light, verify: () => Check(Mathf.Abs(current.distance - 2) < 0.025f, "whole action trajectory including final fraction: " + current.distance));
            Add("same action replay", 1.3f, command: LabCommand.Light, verify: () => Check(Mathf.Abs(current.distance - 2) < 0.025f, "independent clock: " + current.distance));
            Add("action before graph rebuild", 0.25f, command: LabCommand.Light);
            Add("re-enable rebases active action", 0.35f, enter: () =>
            { driver.motionPlayer.enabled = false; driver.motionPlayer.enabled = true; driver.motionPlayer.Ensure(); },
                verify: () => Check(current.distance > 0.4f && current.distance < 0.8f, "re-enable never replays elapsed action distance: " + current.distance));
            Add("rebuilt action finish", 0.8f, verify: () => Check(driver.combat.Current == null, "rebuilt action still finishes"));
            Add("action before pause", 0.25f, command: LabCommand.Light);
            Add("pause action", 0.3f, command: LabCommand.Pause, verify: () => Check(current.distance < 0.001f, "suspended action does not move"));
            Add("resume action", 1.1f, command: LabCommand.Pause, verify: () => Check(driver.combat.Current == null && current.distance < 1.6f, "action completes with no replayed pause distance"));
            Add("action before hit", 0.25f, command: LabCommand.Light);
            Add("reaction cuts root immediately", 0.8f, command: LabCommand.Hit, verify: () => Check(current.distance < 0.001f, "no residual root after authoritative hit"));
            Add("missing root fails closed", 1.3f, command: LabCommand.Light, enter: () => attack.rootMotion.track = null,
                verify: () => { Check(current.distance < 0.001f, "missing root never secretly uses procedural movement"); attack.rootMotion.track = runTrack; });
            Add("wall settle", 0.5f, enter: () => { ResetAt(new Vector3(1200, 20.1f, 0)); wall.SetActive(true); });
            Add("root collision wall", 3, Vector2.up, verify: () => Check(driver.transform.position.z < 3.7f, "wall blocks root movement"));
            Add("wall removed no debt", 0.8f, Vector2.up, enter: () => wall.SetActive(false), verify: () => Check(current.distance > 1 && current.distance < 2, "blocked displacement never accumulates"));
            Add("jump from root run", 0.2f, Vector2.up, LabCommand.Jump, verify: () => Check(!driver.motor.IsGrounded && current.height > 0.3f, "ballistic takeoff"));
            Add("root jump landing", 1.8f, Vector2.up, verify: () => Check(driver.motor.IsGrounded, "landing returns to root movement"));
            Add("slope settle", 0.8f, enter: () => ResetAt(new Vector3(1400, 23.6f, -6)));
            Add("slope root downhill", 2, Vector2.up, verify: () => Check(driver.motor.IsGrounded && driver.transform.position.y < origin.y - 0.4f, "root movement follows walkable downhill"));
            Add("ledge settle", 0.6f, enter: () => ResetAt(new Vector3(1500, 20.1f, 0)));
            Add("root ledge and landing", 3.5f, Vector2.up, verify: () => Check(driver.motor.IsGrounded && driver.transform.position.y < 16 && driver.transform.position.z > 5, "ledge momentum/physics landing"));
            Add("yaw settle", 0.6f, enter: () => ResetAt(new Vector3(1200, 20.1f, 0)));
            Add("authored root yaw", 1.1f, enter: () => ConfigureIdle(rotate, true, false), verify: () => Check(current.yaw > 85 && current.yaw < 115 && current.distance < 0.01f, "yaw applied once by Motor: " + current.yaw));
            Add("authored vertical", 1.1f, command: LabCommand.Light, enter: () =>
            {
                ConfigureIdle(idle, false, false); attack.clip = lift;
                attack.rootMotion = new RootMotionSettings { enabled = true, vertical = true, track = RootMotionBaker.Bake(lib.model, lift) };
            }, verify: () => Check(current.height > 0.8f && current.height < 1.2f, "authored vertical not double gravity: " + current.height));
            Add("return to gravity", 1.5f, enter: () => { ConfigureIdle(idle, false, false); }, verify: () => Check(driver.motor.IsGrounded, "vertical ownership returns to gravity"));
            Add("one-shot turn settle", 0.5f, enter: () =>
            {
                ResetAt(new Vector3(1200, 20.1f, 0));
                foreach (var entry in lib.entries.Where(e => e.slot == MotionSlot.TurnInPlaceRight))
                { entry.clip = rotate; entry.stageSeconds = 1; entry.rootMotion = new RootMotionSettings { enabled = true, rotation = true, track = RootMotionBaker.Bake(lib.model, rotate) }; }
            });
            Add("one-shot turn exact endpoint", 1.3f, command: LabCommand.FaceRight,
                verify: () => Check(Mathf.Abs(current.yaw - 90) < 0.5f, "root turn ends once without procedural snap: " + current.yaw));
            Add("bridge settle", 0.5f, enter: () =>
            {
                ResetAt(new Vector3(1200, 20.1f, 0)); bridgeDistance = 0;
                var bridge = lib.entries.First(e => e.stance == driver.stance && e.slot == MotionSlot.IdleVariation);
                bridge.enabled = true; bridge.clip = run; bridge.rootMotion = new RootMotionSettings { enabled = true, track = runTrack };
                lib.overrides.Add(new MotionRecipe { to = MotionFamily.Move, bridgeEntry = bridge.id, bridgeSeconds = 0.5f, blendSeconds = 0, bridgeOutSeconds = 0 });
            });
            Add("root bridge exact endpoint", 2.2f, Vector2.up, verify: () => Check(Mathf.Abs(bridgeDistance - 2) < 0.025f, "bridge clock/terminal fraction: " + bridgeDistance));
            input.replay = Read; driver.FrameCompleted += Tick; Next();
        }
        static void ConfigureIdle(AnimationClip clip, bool yaw, bool vertical)
        {
            var lib = driver.motionPlayer.WorkingLibrary;
            foreach (var entry in lib.entries.Where(e => e.slot == MotionSlot.Idle))
            { entry.clip = clip; entry.rootMotion = new RootMotionSettings { enabled = yaw || vertical, rotation = yaw, vertical = vertical, track = RootMotionBaker.Bake(lib.model, clip) }; }
        }
        static LabInputFrame Read() { if (index < 0 || index >= steps.Count) return default; var frame = steps[index].input; frame.pressed = pending; pending = LabCommand.None; return frame; }
        static void Next()
        {
            if (current != null) { steps[index].verify?.Invoke(); report.cases.Add(current); }
            if (++index >= steps.Count) { Finish(true); return; }
            current = new Result { name = steps[index].name }; elapsed = 0;
            steps[index].enter?.Invoke(); origin = lastPosition = driver.transform.position; lastYaw = driver.transform.eulerAngles.y;
            pending = steps[index].input.pressed; SessionState.SetString(Key + "status", $"Running {index + 1}/{steps.Count}: {current.name}");
        }
        static void Tick(AnimatedCharacterDriver actor)
        {
            try
            {
                float dt = Time.deltaTime; elapsed += dt; report.elapsed += dt; report.frames++; current.frames++; current.elapsed += dt;
                var position = driver.transform.position; float yaw = driver.transform.eulerAngles.y;
                current.distance += new Vector2(position.x - lastPosition.x, position.z - lastPosition.z).magnitude;
                current.height = position.y - origin.y; current.yaw += Mathf.DeltaAngle(lastYaw, yaw);
                if (current.name == "root bridge exact endpoint" && (driver.motionPlayer.Player.Key.EndsWith("/bridge", StringComparison.Ordinal) || driver.motionPlayer.CompletionFrame.positionWeight > 0))
                    bridgeDistance += driver.motionPlayer.Player.Key.EndsWith("/bridge", StringComparison.Ordinal)
                        ? driver.motionPlayer.RootFrame.localDelta.magnitude : driver.motionPlayer.CompletionFrame.localDelta.magnitude;
                Check(RootMotionSettings.Finite(position.sqrMagnitude) && position.y > 10, "finite collision-resolved position");
                Check(driver.animator.runtimeAnimatorController == null && !driver.animator.applyRootMotion, "single Motor owner, no Controller/native auto motion");
                Check(Vector3.Distance(position, lastPosition) < 1.5f, "no one-frame root teleport");
                Check(driver.motionPlayer.Player.VoiceCount <= 24 && Mathf.Abs(driver.motionPlayer.Player.WeightSum - 1) < 0.002f, "bounded normalized pose");
                lastPosition = position; lastYaw = yaw;
                if (elapsed >= steps[index].seconds) Next();
            }
            catch (Exception e) { failures.Add(e.ToString()); Finish(true); }
        }
        static void Finish(bool stop)
        {
            if (report == null) report = new Report();
            if (driver != null)
            {
                driver.FrameCompleted -= Tick;
                Check(EditorJsonUtility.ToJson(driver.motionPlayer.library) == sourceJson, "source library unchanged");
                Check(EditorJsonUtility.ToJson(sourceProfile) == profileJson, "source profile unchanged");
                driver.combat.suspended = false;
            }
            if (input != null) input.replay = null;
            Check(report.cases.Count == steps.Count && steps.Count >= 20, "all scenarios completed");
            report.status = failures.Count == 0 ? "PASS root mechanisms; final asset quality pending" : "FAIL";
            report.failures = failures.ToArray(); report.averageFps = report.frames / Mathf.Max(0.001f, report.elapsed);
            var json = JsonUtility.ToJson(report, true); SessionState.SetString(Key + "status", json);
            string path = System.IO.Path.GetFullPath(System.IO.Path.Combine(Application.dataPath, "../Library/NoWiresValidation"));
            System.IO.Directory.CreateDirectory(path); System.IO.File.WriteAllText(System.IO.Path.Combine(path, "root-" + report.targetFps + ".json"), json);
            foreach (var item in temporary) if (item != null) Object.Destroy(item); temporary.Clear();
            Application.targetFrameRate = SessionState.GetInt(Key + "oldFps", -1); QualitySettings.vSyncCount = SessionState.GetInt(Key + "oldVsync", 1);
            Time.timeScale = SessionState.GetFloat(Key + "oldScale", 1); Application.runInBackground = SessionState.GetBool(Key + "oldBackground", false);
            SessionState.SetBool(Key + "run", false); if (stop) EditorApplication.delayCall += () => EditorApplication.isPlaying = false;
        }
    }
}
