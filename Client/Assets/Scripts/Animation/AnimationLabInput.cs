using UnityEngine;

namespace Afauxzhub.Project.Animation
{
    [System.Flags]
    public enum LabCommand
    {
        None = 0, Jump = 1, FaceLeft = 2, FaceRight = 4, Target = 8, Stance = 16,
        ForceStance = 32, Light = 64, Heavy = 128, Dodge = 256, Skill = 512,
        Guard = 1024, ReleaseGuard = 2048, Hit = 4096, Pause = 8192
    }
    public struct LabInputFrame
    {
        public Vector2 move;
        public bool sprint, walk;
        public LabCommand pressed;
    }
    /// <summary>Explicit lab controls, not the production input or resource policy.</summary>
    [DefaultExecutionOrder(-100)]
    public sealed class AnimationLabInput : MonoBehaviour
    {
        public AnimatedCharacterDriver driver;
        public Transform target;
        public bool showHUD = true;
        // A replay supplies the same input frame as the keyboard adapter; it never writes FSM phases.
        [System.NonSerialized] public System.Func<LabInputFrame> replay;
        private bool replayOwnedMovement;
        private void Update()
        {
            if (driver == null || driver.combat == null || driver.profile == null) return;
            if (replay != null)
            {
                var frame = replay(); driver.useManualInput = true; replayOwnedMovement = true;
                driver.manualInput = Vector2.ClampMagnitude(frame.move, 1); ApplyFrame(frame); return;
            }
            if (replayOwnedMovement) { driver.useManualInput = false; replayOwnedMovement = false; }
            var keyboard = new LabInputFrame { sprint = Input.GetKey(KeyCode.LeftShift), walk = Input.GetKey(KeyCode.LeftControl) };
            if (driver.UsesMotionLibrary)
            { driver.motionPlayer.Ensure(); if (Input.GetKeyDown(driver.motionPlayer.WorkingLibrary.jumpKey)) keyboard.pressed |= LabCommand.Jump; }
            if (Input.GetKeyDown(KeyCode.Q)) keyboard.pressed |= LabCommand.FaceLeft;
            if (Input.GetKeyDown(KeyCode.E)) keyboard.pressed |= LabCommand.FaceRight;
            if (Input.GetKeyDown(KeyCode.Tab)) keyboard.pressed |= LabCommand.Target;
            if (Input.GetKeyDown(KeyCode.V)) keyboard.pressed |= LabCommand.Stance;
            if (Input.GetKeyDown(KeyCode.F2)) keyboard.pressed |= LabCommand.ForceStance;
            if (Input.GetKeyDown(KeyCode.J)) keyboard.pressed |= LabCommand.Light;
            if (Input.GetKeyDown(KeyCode.K)) keyboard.pressed |= LabCommand.Heavy;
            if (Input.GetKeyDown(KeyCode.Space)) keyboard.pressed |= LabCommand.Dodge;
            if (Input.GetKeyDown(KeyCode.L)) keyboard.pressed |= LabCommand.Skill;
            if (Input.GetKeyDown(KeyCode.G)) keyboard.pressed |= LabCommand.Guard;
            if (Input.GetKeyUp(KeyCode.G)) keyboard.pressed |= LabCommand.ReleaseGuard;
            if (Input.GetKeyDown(KeyCode.H)) keyboard.pressed |= LabCommand.Hit;
            if (Input.GetKeyDown(KeyCode.P)) keyboard.pressed |= LabCommand.Pause;
            ApplyFrame(keyboard);
        }
        public void ApplyFrame(LabInputFrame frame)
        {
            if (driver == null || driver.combat == null || driver.profile == null) return;
            driver.sprint = frame.sprint; driver.walk = frame.walk;
            var buttons = frame.pressed;
            // Resolve suspension before other commands in the same input frame.
            if ((buttons & LabCommand.Pause) != 0) driver.combat.suspended = !driver.combat.suspended;
            if (driver.UsesMotionLibrary)
            {
                driver.motionPlayer.Ensure();
                if ((buttons & LabCommand.Jump) != 0) driver.RequestJump();
                if ((buttons & LabCommand.FaceLeft) != 0) driver.RequestFacing(Quaternion.Euler(0, -90, 0) * driver.transform.forward);
                if ((buttons & LabCommand.FaceRight) != 0) driver.RequestFacing(Quaternion.Euler(0, 90, 0) * driver.transform.forward);
            }
            if ((buttons & LabCommand.Target) != 0) driver.lockTarget = driver.lockTarget == null ? target : null;
            if ((buttons & LabCommand.Stance) != 0) driver.RequestStance(driver.stance == WeaponStance.Sheathed ? WeaponStance.Drawn : WeaponStance.Sheathed);
            // F2 is visibly labelled as a lab override for missing draw/sheathe assets.
            if ((buttons & LabCommand.ForceStance) != 0 && driver.combat.Current == null)
                driver.stance = driver.stance == WeaponStance.Sheathed ? WeaponStance.Drawn : WeaponStance.Sheathed;
            if ((buttons & LabCommand.Light) != 0) RequestChain(false);
            if ((buttons & LabCommand.Heavy) != 0) RequestChain(true);
            if ((buttons & LabCommand.Dodge) != 0) Request(ActionKind.Dodge);
            if ((buttons & LabCommand.Skill) != 0) Request(ActionKind.Skill);
            if ((buttons & LabCommand.Guard) != 0) Request(ActionKind.Guard);
            if ((buttons & LabCommand.ReleaseGuard) != 0) driver.combat.ReleaseHeldAction();
            if ((buttons & LabCommand.Hit) != 0) driver.combat.ApplyCombatResult(driver.profile.Find(ActionKind.LightHit));
        }
        private void OnDisable()
        {
            replay = null;
            if (replayOwnedMovement && driver != null) { driver.useManualInput = false; driver.manualInput = Vector2.zero; }
            replayOwnedMovement = false;
        }
        private void Request(ActionKind kind) => driver.combat.Request(driver.profile.Find(kind));
        private void RequestChain(bool heavy)
        {
            var current = driver.combat.Current;
            var next = current != null ? heavy ? current.nextHeavy : current.nextLight : null;
            driver.combat.Request(next != null ? next : driver.profile.Find(heavy ? ActionKind.HeavyAttack : ActionKind.LightAttack));
        }
        private void OnGUI()
        {
            if (!showHUD || driver == null || driver.combat == null) return;
            var c = driver.combat;
            GUILayout.BeginArea(new Rect(12, 12, 700, driver.UsesMotionLibrary ? 350 : 240), GUI.skin.box);
            GUILayout.Label("ANIMATION LAB — presentation sandbox, not combat balance validation");
            GUILayout.Label("WASD move · Shift sprint · Ctrl walk · Tab target · RMB camera");
            GUILayout.Label("V draw/sheathe · F2 FORCE SET (lab only) · J/K attack · Space dodge");
            GUILayout.Label("G hold guard · L skill · H simulate received hit · P pause");
            GUILayout.Label($"{driver.stance} | {driver.Phase} | {driver.Speed:F2} m/s | yaw {driver.YawRate:F1}°/s");
            GUILayout.Label($"Rule state: {c.Phase} | {(c.Current != null ? c.Current.id : "Free")} | {c.TimeInAction:F3}s");
            GUILayout.Label("Motion: " + driver.MotionOwner + " | " + c.LastDecision);
            if (!string.IsNullOrEmpty(driver.LastConfigurationError)) GUILayout.Label(driver.LastConfigurationError);
            if (driver.UsesMotionLibrary && driver.motionPlayer.WorkingLibrary != null)
            {
                var player = driver.motionPlayer;
                GUILayout.Label("NO WIRES / Playables · " + player.WorkingLibrary.jumpKey + " jump · dynamic foot locking deferred");
                GUILayout.Label("Q/E idle facing request · " + player.Support + $" · rate x{player.PlaybackScale:F2}");
                GUILayout.Label("Recipe: " + player.Decision);
                GUILayout.Label($"Target {driver.TargetSpeed:F2} / smoothed {driver.Speed:F2} / Motor {new Vector2(driver.motor.Velocity.x, driver.motor.Velocity.z).magnitude:F2} m/s");
                GUILayout.Label("Missing: " + (string.IsNullOrEmpty(player.Missing) ? "none in active selection" : player.Missing));
                GUILayout.Label(player.Player != null ? player.Player.Describe() : "Player starting");
            }
            GUILayout.EndArea();
        }
    }
}
