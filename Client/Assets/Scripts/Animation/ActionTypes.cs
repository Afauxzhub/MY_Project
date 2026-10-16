using System;

namespace Afauxzhub.Project.Animation
{
    public enum WeaponStance { Sheathed, Drawn }
    public enum ActionKind { LightAttack, HeavyAttack, Charge, Dodge, Guard, Counter, Skill, Ultimate, DrawWeapon, SheatheWeapon, LightHit, HeavyHit, Launch, Fall, Knockdown, GetUp, WallHit, Death }
    public enum ActionPhase { Free, Startup, Active, Recovery, Hold, Reaction, Dead, Suspended }
    public enum WindowKind { Hitbox, Counter, CancelToEvade, CancelToGuard, CancelToSkill, Combo, Invulnerable, Movement, Turn, EvadeEscape, FootIK }
    public enum CueKind { Effect, Sound, CameraImpulse, Marker }
    public enum MovementAuthority { Procedural, RootMotion, Stationary }

    [Serializable]
    public sealed class ActionWindow
    {
        public WindowKind kind;
        public string id = "window";
        public float start;
        public float end = 0.1f;
        public bool Contains(double time) => time >= start && time < end;
    }

    /// <summary>Pure combat permissions. Presentation cannot bypass these checks.</summary>
    public static class ActionRules
    {
        public static bool IsReaction(ActionKind kind) => kind >= ActionKind.LightHit;
        public static bool NeedsGate(ActionKind kind) => kind == ActionKind.Skill || kind == ActionKind.Guard || kind == ActionKind.Ultimate;
        public static bool IsAttack(ActionKind kind) => kind == ActionKind.LightAttack || kind == ActionKind.HeavyAttack || kind == ActionKind.Charge || kind == ActionKind.Skill || kind == ActionKind.Ultimate;
        public static bool CanRequest(ActionKind? current, ActionKind requested, Func<WindowKind, bool> open, bool resolvedInterrupt = false)
        {
            if (current == ActionKind.Death) return false;
            // Counter and hit reactions require an authoritative combat result, never a regular input.
            if (requested == ActionKind.Counter) return resolvedInterrupt && current.HasValue && IsAttack(current.Value) && open(WindowKind.Counter);
            if (IsReaction(requested)) return resolvedInterrupt;
            if (current == null) return true;
            if (IsReaction(current.Value)) return requested == ActionKind.Dodge && open(WindowKind.EvadeEscape);
            switch (requested)
            {
                case ActionKind.Dodge: return open(WindowKind.CancelToEvade);
                case ActionKind.Guard: return open(WindowKind.CancelToGuard);
                case ActionKind.Skill: return open(WindowKind.CancelToSkill);
                case ActionKind.LightAttack:
                case ActionKind.HeavyAttack: return open(WindowKind.Combo);
                default: return false;
            }
        }
    }
}
