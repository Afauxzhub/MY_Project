using System;
using System.Collections.Generic;
using Afauxzhub.CharacterLocomotion;
using UnityEngine;

namespace Afauxzhub.Project.Animation
{
    public enum MotionGait { Any, Walk, Run, Sprint }
    public enum MotionDirection { Any, Forward, ForwardRight, Right, BackRight, Back, BackLeft, Left, ForwardLeft }
    public enum MotionFamily { Any, Idle, Move, Start, Stop, Accelerate, Decelerate, Turn, Pivot, Strafe, Takeoff, Air, Land, Action, TurnInPlace }
    public enum MotionMode { Any, Free, Targeting }
    public enum MotionReview { Pending, Approved, Placeholder }

    [Serializable]
    public sealed class MotionEntry
    {
        public string id = Guid.NewGuid().ToString("N");
        public WeaponStance stance;
        public MotionSlot slot;
        public MotionGait gait;
        public MotionDirection direction;
        public MotionMode mode;
        public AnimationClip clip;
        public bool enabled = true;
        [Min(0.01f)] public float speed = 1;
        [Range(0, 1)] public float inPoint;
        [Range(0, 1)] public float outPoint = 1;
        [Range(0, 1)] public float phaseOffset;
        [Header("Authoring metadata (never rewrites source animation)")]
        public MotionReview review;
        public string reviewedFingerprint;
        [Tooltip("Optional exact clip name or suffix for batch proposals; never a state name.")] public string matchName;
        public bool optional;
        [Min(0)] public float minimumSpeed;
        [Min(0)] public float maximumSpeed = 1000;
        [Range(0, 180)] public float minimumAngle;
        [Range(0, 180)] public float maximumAngle = 180;
        [Tooltip("0 uses the phase timing from movement tuning; >0 overrides it in seconds.")]
        [Min(0)] public float stageSeconds;
        [Tooltip("Actual translation speed represented by one authored cycle; 0 = unknown.")]
        [Min(0)] public float referenceSpeed;
        public bool matchPlaybackToSpeed;
        public bool contactAuthored;
        public AnimationCurve leftContact = AnimationCurve.Constant(0, 1, 0);
        public AnimationCurve rightContact = AnimationCurve.Constant(0, 1, 0);
        [TextArea] public string note;
        public float CycleSeconds => clip == null ? 1 : Mathf.Max(0.01f, clip.length * (outPoint - inPoint) / Mathf.Max(0.01f, speed));
        public bool Applicable(float actualSpeed, float angle) => (actualSpeed < 0 || actualSpeed >= minimumSpeed && actualSpeed <= maximumSpeed)
            && (angle < 0 || angle >= minimumAngle && angle <= maximumAngle);
        public float PlaybackScale(float actualSpeed, float minimum, float maximum) => matchPlaybackToSpeed && referenceSpeed > 0.001f
            ? Mathf.Clamp(actualSpeed / referenceSpeed, minimum, maximum) : 1;
        // Cycles are shared across gait/direction blends. Speed changes the cycle rate, not its wrapped phase.
        public MotionSample Sample(float phase, float weight, bool loop) => new MotionSample(id, clip, weight,
            Mathf.Lerp(inPoint, outPoint, loop ? Mathf.Repeat(phase + phaseOffset, 1) : Mathf.Clamp01(phase * speed)));
    }

    [Serializable]
    public sealed class MotionRecipe
    {
        public string id = Guid.NewGuid().ToString("N");
        public string label = "New transition";
        public bool enabled = true;
        public MotionFamily from, to;
        [Tooltip("-1 means either stance.")] public int stance = -1;
        public MotionGait gait;
        public MotionDirection direction;
        public MotionMode fromMode, toMode;
        public int priority;
        [Min(0)] public float blendSeconds = 0.18f;
        public AnimationCurve weight = AnimationCurve.EaseInOut(0, 0, 1, 1);
        public bool preserveCyclePhase = true;
        [Range(0, 1)] public float targetPhase;
        [Range(0, 1)] public float interruptAfter;
        [Tooltip("Optional stable entry ID, never a filename or Animator path.")] public string bridgeEntry;
        [Min(0.01f)] public float bridgeSeconds = 0.25f;
        [Min(0)] public float bridgeOutSeconds = 0.12f;
        public int Specificity => (from != MotionFamily.Any ? 1 : 0) + (to != MotionFamily.Any ? 1 : 0)
            + (stance >= 0 ? 1 : 0) + (gait != MotionGait.Any ? 1 : 0) + (direction != MotionDirection.Any ? 1 : 0)
            + (fromMode != MotionMode.Any ? 1 : 0) + (toMode != MotionMode.Any ? 1 : 0);
        public bool Matches(MotionFamily source, MotionFamily target, WeaponStance set, MotionGait speed, MotionDirection heading) => enabled
            && (from == MotionFamily.Any || from == source) && (to == MotionFamily.Any || to == target)
            && (stance < 0 || stance == (int)set) && (gait == MotionGait.Any || gait == speed)
            && (direction == MotionDirection.Any || direction == heading);
        public bool MatchesModes(MotionMode before, MotionMode after) => (fromMode == MotionMode.Any || fromMode == before) && (toMode == MotionMode.Any || toMode == after);
    }

    [CreateAssetMenu(menuName = "MY Project/Animation/Motion Library (No Wires)")]
    public sealed partial class MotionLibrary : ScriptableObject
    {
        public GameObject model;
        public LocomotionProfile relaxedMovement, readyMovement;
        public MotionRecipeTemplates templates;
        public List<MotionEntry> entries = new List<MotionEntry>();
        public List<MotionRecipe> overrides = new List<MotionRecipe>();
        [Min(0)] public float defaultBlend = 0.18f;
        [Header("Jump — movement tuning, no aerial combat permissions")]
        public KeyCode jumpKey = KeyCode.C;
        [Min(0.01f)] public float jumpHeight = 1.3f;
        [Min(0.01f)] public float takeoffSeconds = 0.12f;
        [Range(0, 1)] public float airControl = 0.35f;
        [Min(0)] public float apexSpeed = 0.8f;
        [Header("Optional idle variation")]
        public bool idleVariation;
        [Min(1)] public float idleVariationInterval = 6;
        [Header("Authored speed matching (opt-in per clip)")]
        [Min(0.01f)] public float minimumPlaybackScale = 0.5f;
        [Min(0.01f)] public float maximumPlaybackScale = 1.5f;
        public LocomotionProfile Movement(WeaponStance stance) => stance == WeaponStance.Sheathed ? relaxedMovement : readyMovement;
        public MotionEntry ById(string id) => string.IsNullOrEmpty(id) ? null : entries.Find(e => e != null && e.id == id && e.enabled);

        public MotionEntry Find(WeaponStance stance, MotionSlot slot, MotionGait gait, MotionDirection direction, out bool approximate)
            => Find(stance, slot, gait, direction, MotionMode.Any, -1, -1, out approximate);

        public MotionEntry Find(WeaponStance stance, MotionSlot slot, MotionGait gait, MotionDirection direction, MotionMode mode, float actualSpeed, float angle, out bool approximate)
        {
            MotionEntry best = null; int score = -1; approximate = false;
            foreach (var entry in entries)
            {
                if (entry == null || !entry.enabled || entry.stance != stance || entry.slot != slot || entry.clip == null) continue;
                if (entry.gait != MotionGait.Any && entry.gait != gait || entry.direction != MotionDirection.Any && entry.direction != direction) continue;
                if (entry.mode != MotionMode.Any && entry.mode != mode || !entry.Applicable(actualSpeed, angle)) continue;
                int candidate = (entry.mode != MotionMode.Any ? 4 : 0) + (entry.gait == gait ? 2 : 0) + (entry.direction == direction ? 1 : 0);
                if (candidate <= score) continue;
                score = candidate; best = entry;
            }
            // An authored Any variant is explicit sharing, not a missing resource fallback.
            if (best != null) return best;
            approximate = true;
            return null;
        }

        public MotionRecipe Resolve(MotionFamily from, MotionFamily to, WeaponStance stance, MotionGait gait, MotionDirection direction, out string reason)
            => Resolve(from, to, stance, gait, direction, MotionMode.Any, MotionMode.Any, out reason);

        public MotionRecipe Resolve(MotionFamily from, MotionFamily to, WeaponStance stance, MotionGait gait, MotionDirection direction, MotionMode beforeMode, MotionMode afterMode, out string reason)
        {
            MotionRecipe best = null; int bestRank = int.MinValue; bool conflict = false; string origin = "Default";
            void Scan(List<MotionRecipe> list, int layer, string label)
            {
                if (list == null) return;
                foreach (var recipe in list)
                {
                    if (recipe == null || !recipe.Matches(from, to, stance, gait, direction) || !recipe.MatchesModes(beforeMode, afterMode)) continue;
                    int rank = layer * 100000 + Mathf.Clamp(recipe.priority, -1000, 1000) * 10 + recipe.Specificity;
                    if (rank > bestRank) { best = recipe; bestRank = rank; conflict = false; origin = label; }
                    else if (rank == bestRank) conflict = true;
                }
            }
            if (templates != null) Scan(templates.recipes, 0, "Template");
            Scan(overrides, 1, "Character override");
            reason = conflict ? "CONFLICT: equally ranked recipes; using safe default blend" : best == null ? "Default blend" : origin + ": " + best.label;
            return conflict ? null : best;
        }

        public IEnumerable<string> Validate()
        {
            if (!Finite(minimumPlaybackScale) || !Finite(maximumPlaybackScale) || minimumPlaybackScale <= 0 || maximumPlaybackScale < minimumPlaybackScale)
                yield return "Invalid playback scale range";
            if (!Finite(defaultBlend) || defaultBlend < 0 || !Finite(jumpHeight) || jumpHeight <= 0
                || !Finite(takeoffSeconds) || takeoffSeconds <= 0 || !Unit(airControl) || !Finite(apexSpeed) || apexSpeed < 0
                || !Finite(idleVariationInterval) || idleVariationInterval < 1) yield return "Invalid movement/transition timing";
            foreach (var movement in new[] { relaxedMovement, readyMovement })
            {
                if (movement == null) continue;
                bool valid = true;
                foreach (float value in new[] { movement.walkSpeed, movement.runSpeed, movement.sprintSpeed, movement.acceleration, movement.deceleration,
                    movement.startDuration, movement.stopDuration, movement.pivotDuration, movement.turn90Duration, movement.landDuration,
                    movement.idleTurnDuration, movement.idlePivotDuration, movement.idleTurnAngle,
                    movement.releaseDelay, movement.targetFacingSpeed, movement.strafeSpeed, movement.maximumYawRate, movement.yawAcceleration, movement.yawDeceleration })
                    if (!Finite(value) || value < 0) valid = false;
                if (movement.walkSpeed > movement.runSpeed || movement.runSpeed > movement.sprintSpeed || !Unit(movement.backwardSpeedScale)) valid = false;
                if (!Unit(movement.turnInterrupt) || movement.idleTurnAngle < 5 || movement.idleTurnAngle > 135
                    || movement.idleTurnDuration <= 0 || movement.idlePivotDuration <= 0 || movement.turn90Angle > movement.pivotAngle) valid = false;
                foreach (var curve in new[] { movement.accelerationBySpeed, movement.decelerationBySpeed, movement.turnSpeedScale, movement.turnProgress })
                {
                    if (curve == null || curve.length == 0) { valid = false; continue; }
                    for (int i = 0; i <= 32; i++) { float value = curve.Evaluate(i / 32f); if (!Finite(value) || value < 0) valid = false; }
                }
                if (!valid) yield return "Invalid movement tuning: " + movement.name;
            }
            var ids = new HashSet<string>(); var keys = new HashSet<string>();
            foreach (var entry in entries)
            {
                if (entry == null) { yield return "Null motion entry"; continue; }
                if (string.IsNullOrWhiteSpace(entry.id) || !ids.Add(entry.id)) yield return "Duplicate/empty entry ID: " + entry.id;
                string key = entry.stance + "/" + entry.mode + "/" + entry.slot + "/" + entry.gait + "/" + entry.direction;
                if (entry.enabled && !keys.Add(key)) yield return "Ambiguous enabled slot: " + key;
                if (!Finite(entry.speed) || entry.speed <= 0 || !Unit(entry.inPoint) || !Unit(entry.outPoint) || !Unit(entry.phaseOffset) || entry.outPoint <= entry.inPoint)
                    yield return "Invalid clip range/speed: " + key;
                if (!Finite(entry.minimumSpeed) || !Finite(entry.maximumSpeed) || entry.minimumSpeed < 0 || entry.maximumSpeed < entry.minimumSpeed
                    || !Finite(entry.minimumAngle) || !Finite(entry.maximumAngle) || entry.minimumAngle < 0 || entry.maximumAngle > 180 || entry.maximumAngle < entry.minimumAngle
                    || !Finite(entry.stageSeconds) || entry.stageSeconds < 0 || !Finite(entry.referenceSpeed) || entry.referenceSpeed < 0
                    || entry.matchPlaybackToSpeed && entry.referenceSpeed <= 0) yield return "Invalid applicability/speed metadata: " + key;
                if (entry.contactAuthored && (!ValidContact(entry.leftContact) || !ValidContact(entry.rightContact))) yield return "Invalid contact curves: " + key;
            }
            var allRecipes = new List<MotionRecipe>(overrides);
            if (templates != null) allRecipes.AddRange(templates.recipes);
            foreach (var recipe in allRecipes)
            {
                if (recipe == null) { yield return "Null recipe"; continue; }
                if (string.IsNullOrWhiteSpace(recipe.id) || !ids.Add(recipe.id)) yield return "Duplicate/empty recipe ID";
                if (!Finite(recipe.blendSeconds) || recipe.blendSeconds < 0 || !Unit(recipe.targetPhase) || !Unit(recipe.interruptAfter)
                    || !Finite(recipe.bridgeSeconds) || recipe.bridgeSeconds <= 0 || !Finite(recipe.bridgeOutSeconds) || recipe.bridgeOutSeconds < 0
                    || recipe.stance < -1 || recipe.stance > 1 || !ValidWeight(recipe.weight)) yield return "Invalid blend: " + recipe.label;
                if (!string.IsNullOrEmpty(recipe.bridgeEntry) && ById(recipe.bridgeEntry)?.clip == null) yield return "Missing bridge: " + recipe.label;
            }
        }
        private static bool ValidWeight(AnimationCurve curve)
        {
            if (curve == null || curve.length < 2 || Mathf.Abs(curve.Evaluate(0)) > 0.001f || Mathf.Abs(curve.Evaluate(1) - 1) > 0.001f) return false;
            foreach (var key in curve.keys) if (!Finite(key.time) || !Finite(key.value)) return false;
            for (int i = 0; i <= 32; i++) if (!Unit(curve.Evaluate(i / 32f))) return false;
            return true;
        }
        private static bool Unit(float value) => Finite(value) && value >= 0 && value <= 1;
        private static bool ValidContact(AnimationCurve curve)
        { if (curve == null || curve.length == 0) return false; for (int i = 0; i <= 64; i++) if (!Unit(curve.Evaluate(i / 64f))) return false; return true; }
        private static bool Finite(float value) => !float.IsNaN(value) && !float.IsInfinity(value);
    }
}
