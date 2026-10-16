using System;
using System.Collections.Generic;
using UnityEngine;

namespace Afauxzhub.Project.Animation
{
    [Serializable]
    public sealed class ActionCue
    {
        public string id = "cue";
        public CueKind kind;
        [Min(0)] public float time;
        public GameObject effect;
        public AudioClip sound;
        public string socketPath;
        public Vector3 offset;
        [Min(0.01f)] public float lifetime = 2;
        [Range(0, 1)] public float intensity = 0.5f;
    }

    [Serializable]
    public sealed class HitShape
    {
        public string windowId = "hit";
        public string bonePath;
        public Vector3 center = new Vector3(0, 1, 1);
        public Vector3 halfExtents = new Vector3(0.4f, 0.5f, 0.6f);
        public Vector3 euler;
        [Min(0)] public float damage = 10;
        [Min(0)] public float stagger = 10;
    }

    [CreateAssetMenu(menuName = "MY Project/Animation/Action Definition")]
    public sealed class ActionDefinition : ScriptableObject
    {
        public string id = "Action";
        public ActionKind kind;
        [TextArea] public string notes;
        public string ruleIds;
        public AnimationClip clip;
        [Tooltip("Complete Animator path. Generated once; may be changed for a hand-authored graph.")]
        public string animatorState;
        [Tooltip("Optional second state for the same clip, with an independent time parameter. Prevents outgoing poses rewinding when an action restarts.")]
        public string animatorAlternateState;
        public string animationTimeParameter = "ActionTime";
        public string alternateTimeParameter;
        [Min(0.01f)] public float duration = 1;
        [Min(0)] public float activeStart = 0.25f;
        [Min(0)] public float recoveryStart = 0.5f;
        [Min(0)] public float blendIn = 0.08f;
        [Min(0)] public float blendOut = 0.12f;
        [Tooltip("Hold the final pose until ReleaseHeldAction. Suitable for guard or charge.")]
        public bool hold;
        public ActionDefinition onRelease;
        public MovementAuthority movement = MovementAuthority.Stationary;
        [Range(0, 1)] public float inputMovementScale;
        [Range(0, 1)] public float turnScale;
        [Min(0)] public float rootMotionScale = 1;
        public bool applyRootRotation;
        [Tooltip("Normalized action phase (0..1) -> normalized clip time (0..1). Does not move gameplay windows.")]
        public AnimationCurve animationTime = AnimationCurve.Linear(0, 0, 1, 1);
        public AnimationCurve footIK = AnimationCurve.Constant(0, 1, 0);
        public List<ActionWindow> windows = new List<ActionWindow>();
        public List<ActionCue> cues = new List<ActionCue>();
        public List<HitShape> hitShapes = new List<HitShape>();
        public ActionDefinition nextLight;
        public ActionDefinition nextHeavy;

        public float NormalizedTime(float seconds) => Mathf.Clamp01(animationTime.Evaluate(Mathf.Clamp01(seconds / Mathf.Max(0.01f, duration))));
        public bool WindowOpen(WindowKind kindToCheck, double seconds)
        {
            foreach (var window in windows) if (window != null && window.kind == kindToCheck && window.Contains(seconds)) return true;
            return false;
        }

        public IEnumerable<string> Validate()
        {
            if (string.IsNullOrWhiteSpace(id)) yield return "Action ID is empty.";
            if (string.IsNullOrEmpty(animationTimeParameter) || !string.IsNullOrEmpty(animatorAlternateState) && string.IsNullOrEmpty(alternateTimeParameter)) yield return "Assign independent time parameters for the configured Animator states.";
            if (clip == null) yield return "Missing animation clip (state slot retained).";
            if (duration <= 0 || float.IsNaN(duration) || float.IsInfinity(duration)) yield return "Duration must be finite and positive.";
            if (!Finite(activeStart) || !Finite(recoveryStart) || activeStart < 0 || recoveryStart < activeStart || recoveryStart > duration) yield return "Phase boundaries must satisfy 0 <= active <= recovery <= duration.";
            if (!Finite(blendIn) || !Finite(blendOut) || blendIn < 0 || blendOut < 0) yield return "Blend durations must be finite and non-negative.";
            if (animationTime == null || animationTime.length < 2) yield return "Animation time curve requires at least two keys.";
            if (footIK == null) yield return "Foot IK weight curve is missing.";
            if (!Finite(rootMotionScale) || rootMotionScale < 0 || !Finite(inputMovementScale) || inputMovementScale < 0 || inputMovementScale > 1 || !Finite(turnScale) || turnScale < 0 || turnScale > 1) yield return "Movement scales must be finite and inside the authored range.";
            var ids = new HashSet<string>();
            foreach (var w in windows)
            {
                if (w == null) { yield return "Null window."; continue; }
                if (string.IsNullOrWhiteSpace(w.id) || !ids.Add(w.id)) yield return "Window IDs must be non-empty and unique.";
                if (float.IsNaN(w.start) || float.IsNaN(w.end) || w.start < 0 || w.end <= w.start || w.end > duration) yield return $"Invalid interval: {w.id}.";
                if ((kind == ActionKind.LightAttack || kind == ActionKind.HeavyAttack) &&
                    (w.kind == WindowKind.CancelToEvade || w.kind == WindowKind.CancelToGuard) && w.start < recoveryStart)
                    yield return "ATK-05: attack defensive cancellation must start in recovery.";
                if (ActionRules.IsReaction(kind) && w.kind == WindowKind.CancelToSkill) yield return "HIT-02: skill cannot cancel hit-stun.";
                if (w.kind == WindowKind.Counter && !ActionRules.IsAttack(kind)) yield return "COUNTER-01: counter windows belong to active attack actions.";
            }
            if (kind == ActionKind.LightAttack || kind == ActionKind.HeavyAttack)
            {
                float evade = First(WindowKind.CancelToEvade), guard = First(WindowKind.CancelToGuard), skill = First(WindowKind.CancelToSkill);
                if (evade > guard) yield return "ATK-06: evade must be available no later than guard/repel.";
                if (!float.IsPositiveInfinity(skill) && (skill <= evade || skill <= guard)) yield return "ATK-07: skill cancellation must be later than evade and guard.";
            }
            foreach (var cue in cues)
                if (cue == null || cue.time < 0 || cue.time >= duration || float.IsNaN(cue.time)) yield return "Cue must lie inside [0, duration).";
            foreach (var shape in hitShapes)
                if (shape == null || !windows.Exists(w => w != null && w.id == shape.windowId && w.kind == WindowKind.Hitbox)) yield return "Hit shape requires a matching Hitbox window ID.";
        }

        private static bool Finite(float value) => !float.IsNaN(value) && !float.IsInfinity(value);

        private float First(WindowKind k)
        {
            float first = float.PositiveInfinity;
            foreach (var w in windows) if (w != null && w.kind == k) first = Mathf.Min(first, w.start);
            return first;
        }
    }
}
