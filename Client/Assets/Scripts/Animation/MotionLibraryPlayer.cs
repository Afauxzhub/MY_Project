using System;
using System.Collections.Generic;
using Afauxzhub.CharacterLocomotion;
using UnityEngine;

namespace Afauxzhub.Project.Animation
{
    /// <summary>Runtime adapter. Working copies keep Play tweaks away from the source library.</summary>
    public sealed class MotionLibraryPlayer : MonoBehaviour
    {
        public MotionLibrary library;
        public AnimatedCharacterDriver driver;
        public MotionLibrary WorkingLibrary { get; private set; }
        public ClipBlendPlayer Player { get; private set; }
        public string Decision { get; private set; }
        public string Missing { get; private set; }
        public float Cycle { get; private set; }
        public int Revision { get; private set; }
        public MotionFamily Family { get; private set; }
        public MotionSlot SelectedSlot { get; private set; }
        public MotionSupport Support { get; private set; }
        public MotionSlot StopChoice { get; private set; } = MotionSlot.StopLeft;
        public float PlaybackScale { get; private set; } = 1;
        private readonly List<MotionSample> poseSamples = new List<MotionSample>();
        private MotionMode currentMode = MotionMode.Free;
        private readonly List<MotionSample> samples = new List<MotionSample>();
        private readonly HashSet<string> missing = new HashSet<string>();
        private string requestKey;
        private MotionRecipe activeRecipe;
        private float requestTime;
        private bool bridgeFinished;
        private int actionSequence = -1;
        private bool acting;
        private float lastActionBlendOut;
        private float startAngle;
        private LocomotionPhase previousPhase;
        private float stopPhase;
        private bool idleVariationActive;

        public bool Ready => enabled && library != null && driver != null;
        public void Ensure()
        {
            if (WorkingLibrary == null && library != null) ApplyDraft(library);
            if (Player == null && driver != null && driver.animator != null) Player = new ClipBlendPlayer(driver.animator);
        }
        public void ApplyDraft(MotionLibrary source)
        {
            if (source == null) return;
            var next = Instantiate(source); next.hideFlags = HideFlags.HideAndDontSave;
            if (source.relaxedMovement != null) { next.relaxedMovement = Instantiate(source.relaxedMovement); next.relaxedMovement.hideFlags = HideFlags.HideAndDontSave; }
            if (source.readyMovement != null) { next.readyMovement = Instantiate(source.readyMovement); next.readyMovement.hideFlags = HideFlags.HideAndDontSave; }
            if (source.templates != null) { next.templates = Instantiate(source.templates); next.templates.hideFlags = HideFlags.HideAndDontSave; }
            DestroyWorking(); WorkingLibrary = next; Revision++; requestKey = null;
        }
        private void DestroyWorking()
        {
            if (WorkingLibrary == null) return;
            Destroy(WorkingLibrary.relaxedMovement); Destroy(WorkingLibrary.readyMovement); Destroy(WorkingLibrary.templates); Destroy(WorkingLibrary); WorkingLibrary = null;
        }
        private void OnDisable() { Player?.Dispose(); Player = null; requestKey = null; }
        private void OnDestroy() => DestroyWorking();

        public void Tick(ActionDefinition action, LocomotionProfile movement, float dt)
        {
            Ensure(); if (Player == null || WorkingLibrary == null) return;
            if (driver.combat != null && driver.combat.suspended) return;
            var lib = WorkingLibrary;
            samples.Clear(); missing.Clear();
            if (action != null)
            {
                if (!acting || actionSequence != driver.combat.Sequence)
                { actionSequence = driver.combat.Sequence; requestKey = null; }
                acting = true; lastActionBlendOut = action.blendOut; Family = MotionFamily.Action;
                samples.Add(new MotionSample(action.id, action.clip, 1, action.NormalizedTime(driver.combat.TimeInAction)));
                Player.SetTarget("action/" + actionSequence, samples, action.blendIn);
                Player.Evaluate(dt); Player.CopyPoseSamples(poseSamples); Support = lib.Support(poseSamples);
                Decision = "Combat permission accepted / " + action.id; Missing = action.clip == null ? "Combat clip missing: " + action.id : ""; return;
            }
            var phase = driver.Phase;
            if (phase != previousPhase)
            {
                if (phase == LocomotionPhase.Start) startAngle = driver.StartAngle;
                if (phase == LocomotionPhase.Stop) { stopPhase = Cycle; StopChoice = Support.StopSlot(stopPhase); }
                previousPhase = phase;
            }
            var gait = driver.walk ? MotionGait.Walk : driver.sprint ? MotionGait.Sprint : MotionGait.Run;
            var direction = driver.Targeting && phase != LocomotionPhase.Start ? Direction(Mathf.Atan2(driver.LocalVelocity.x, driver.LocalVelocity.y) * Mathf.Rad2Deg)
                : phase == LocomotionPhase.Start ? Direction(startAngle) : Direction(driver.HeadingError);
            SelectedSlot = phase == LocomotionPhase.Stop ? StopChoice : SlotFor(phase, stopPhase);
            var family = FamilyFor(phase);
            var mode = driver.Mode;
            string key = driver.stance + "/" + mode + "/" + family + "/" + SelectedSlot + "/" + gait + "/" + Revision;
            if (family == MotionFamily.Start || family == MotionFamily.Strafe) key += "/" + direction;
            bool forced = acting || mode != currentMode || family == MotionFamily.Takeoff || family == MotionFamily.Air || family == MotionFamily.Land;
            if (key != requestKey && !forced && activeRecipe != null && Player.BlendProgress < activeRecipe.interruptAfter)
            { Player.Evaluate(dt); Decision = "Waiting for transition interrupt point: " + activeRecipe.label; return; }
            float blend = lib.defaultBlend;
            if (key != requestKey)
            {
                activeRecipe = lib.Resolve(Family, family, driver.stance, gait, direction, currentMode, mode, out var resolution);
                currentMode = mode;
                Decision = resolution; requestTime = 0; bridgeFinished = false;
                if (activeRecipe != null && !activeRecipe.preserveCyclePhase) Cycle = activeRecipe.targetPhase;
                requestKey = key; Family = family;
            }
            requestTime += dt;
            if (activeRecipe != null) blend = activeRecipe.blendSeconds;
            if (acting) { blend = lastActionBlendOut; acting = false; }
            var bridge = activeRecipe != null ? lib.ById(activeRecipe.bridgeEntry) : null;
            if (bridge?.clip != null && requestTime < activeRecipe.bridgeSeconds)
            {
                AddEntry(bridge, 1, requestTime / Mathf.Max(0.01f, activeRecipe.bridgeSeconds), false);
                Player.SetTarget(key + "/bridge", samples, blend, activeRecipe.weight);
            }
            else
            {
                if (bridge != null) { blend = activeRecipe.bridgeOutSeconds; bridgeFinished = true; }
                if (family == MotionFamily.Move || family == MotionFamily.Strafe || family == MotionFamily.Accelerate || family == MotionFamily.Decelerate)
                {
                    var dedicated = Find(SelectedSlot, gait, MotionDirection.Any);
                    if ((family == MotionFamily.Accelerate || family == MotionFamily.Decelerate) && dedicated?.clip != null)
                        AddEntry(dedicated, 1, Mathf.Clamp01(requestTime / Mathf.Max(0.01f, dedicated.clip.length * (dedicated.outPoint - dedicated.inPoint))), false);
                    else
                    {
                        if (family == MotionFamily.Accelerate || family == MotionFamily.Decelerate) missing.Add(SelectedSlot + " → gait blend (bridge missing)");
                        AddGait(movement, dt);
                    }
                }
                else if (family == MotionFamily.Idle)
                {
                    var variation = Find(MotionSlot.IdleVariation, MotionGait.Any, MotionDirection.Any);
                    bool vary = lib.idleVariation && variation?.clip != null && requestTime % (lib.idleVariationInterval + variation.CycleSeconds) > lib.idleVariationInterval;
                    if (vary != idleVariationActive) { Cycle = 0; idleVariationActive = vary; }
                    Add(vary ? MotionSlot.IdleVariation : MotionSlot.Idle, MotionGait.Any, MotionDirection.Any, 1, Cycle, true);
                    AdvanceCycle(dt);
                }
                else
                {
                    bool loop = family == MotionFamily.Air;
                    float phaseTime = driver.PhaseNormalized;
                    if (activeRecipe != null && !activeRecipe.preserveCyclePhase) phaseTime = Mathf.Lerp(activeRecipe.targetPhase, 1, phaseTime);
                    Add(SelectedSlot, gait, family == MotionFamily.Start ? direction : MotionDirection.Any, 1, loop ? Cycle : phaseTime, loop);
                    if (loop) AdvanceCycle(dt);
                }
                Player.SetTarget(key + (bridgeFinished ? "/after-bridge" : "") + (family == MotionFamily.Idle ? idleVariationActive ? "/variation" : "/idle" : ""), samples, blend, activeRecipe?.weight);
            }
            Player.Evaluate(dt);
            Player.CopyPoseSamples(poseSamples); Support = lib.Support(poseSamples);
            Missing = string.Join("; ", missing);
        }

        private void AddGait(LocomotionProfile p, float dt)
        {
            float speed = driver.Speed;
            if (speed <= p.walkSpeed) AddStride(MotionGait.Walk, 1, p);
            else if (speed < p.runSpeed)
            { float t = Mathf.InverseLerp(p.walkSpeed, p.runSpeed, speed); AddStride(MotionGait.Walk, 1 - t, p); AddStride(MotionGait.Run, t, p); }
            else
            { float t = Mathf.InverseLerp(p.runSpeed, Mathf.Max(p.runSpeed + 0.01f, p.sprintSpeed), speed); AddStride(MotionGait.Run, 1 - t, p); AddStride(MotionGait.Sprint, t, p); }
            AdvanceCycle(dt);
        }
        private void AdvanceCycle(float dt)
        {
            float duration = 0, weight = 0;
            foreach (var s in samples) if (s.clip != null) { duration += (WorkingLibrary.ById(s.id)?.CycleSeconds ?? s.clip.length) * s.weight; weight += s.weight; }
            float scale = 0;
            foreach (var s in samples) if (s.clip != null) scale += (WorkingLibrary.ById(s.id)?.PlaybackScale(driver.Speed, WorkingLibrary.minimumPlaybackScale, WorkingLibrary.maximumPlaybackScale) ?? 1) * s.weight;
            PlaybackScale = weight > 0 ? scale / weight : 1;
            Cycle = Mathf.Repeat(Cycle + dt * PlaybackScale / Mathf.Max(0.1f, duration / Mathf.Max(0.001f, weight)), 1);
        }
        private void AddStride(MotionGait gait, float weight, LocomotionProfile p)
        {
            if (weight < 0.0001f) return;
            if (driver.Targeting)
            {
                var v = driver.LocalVelocity;
                float angle = Mathf.Repeat(Mathf.Atan2(v.x, v.y) * Mathf.Rad2Deg + 360, 360) / 45;
                int low = Mathf.FloorToInt(angle) % 8, high = (low + 1) % 8;
                var slots = new[] { MotionSlot.StrafeForward, MotionSlot.StrafeForwardRight, MotionSlot.StrafeRight, MotionSlot.StrafeBackRight, MotionSlot.StrafeBack, MotionSlot.StrafeBackLeft, MotionSlot.StrafeLeft, MotionSlot.StrafeForwardLeft };
                Add(slots[low], gait, MotionDirection.Any, weight * (1 - (angle - Mathf.Floor(angle))), Cycle, true);
                Add(slots[high], gait, MotionDirection.Any, weight * (angle - Mathf.Floor(angle)), Cycle, true);
            }
            else if (gait == MotionGait.Walk) Add(MotionSlot.Walk, gait, MotionDirection.Any, weight, Cycle, true);
            else
            {
                float turn = Mathf.Clamp(driver.TurnBlend, -1, 1), t = Mathf.Abs(turn);
                MotionSlot straight = gait == MotionGait.Sprint ? MotionSlot.Sprint : MotionSlot.Run;
                MotionSlot arc = gait == MotionGait.Sprint ? turn < 0 ? MotionSlot.SprintLeft : MotionSlot.SprintRight : turn < 0 ? MotionSlot.ArcLeft : MotionSlot.ArcRight;
                if (gait == MotionGait.Sprint || t <= 0.5f)
                { float a = gait == MotionGait.Sprint ? t : t * 2; Add(straight, gait, MotionDirection.Any, weight * (1 - a), Cycle, true); Add(arc, gait, MotionDirection.Any, weight * a, Cycle, true); }
                else
                { Add(arc, gait, MotionDirection.Any, weight * (2 - t * 2), Cycle, true); Add(turn < 0 ? MotionSlot.ArcSharpLeft : MotionSlot.ArcSharpRight, gait, MotionDirection.Any, weight * (t * 2 - 1), Cycle, true); }
            }
        }
        private void Add(MotionSlot slot, MotionGait gait, MotionDirection direction, float weight, float time, bool loop)
        {
            if (weight < 0.0001f) return;
            var entry = Find(slot, gait, direction);
            if (entry == null)
            {
                if (slot == MotionSlot.Start && direction != MotionDirection.Forward)
                    entry = Find(slot, gait, MotionDirection.Forward);
                if (entry == null && (slot == MotionSlot.Walk || slot == MotionSlot.Sprint || slot >= MotionSlot.ArcLeft && slot <= MotionSlot.SprintRight))
                    entry = Find(MotionSlot.Run, MotionGait.Any, MotionDirection.Any);
                if (entry == null) entry = Find(MotionSlot.Idle, MotionGait.Any, MotionDirection.Any);
                missing.Add(slot + (direction != MotionDirection.Any ? "/" + direction : "") + " → " + (entry != null ? entry.slot.ToString() : "NO CLIP"));
            }
            if (entry != null) AddEntry(entry, weight, time, loop);
        }
        private void AddEntry(MotionEntry entry, float weight, float time, bool loop)
        {
            samples.Add(entry.Sample(time, weight, loop));
            if (entry.review == MotionReview.Placeholder) missing.Add(entry.slot + " uses explicitly marked placeholder");
        }
        private MotionEntry Find(MotionSlot slot, MotionGait gait, MotionDirection direction)
        {
            bool stage = Family != MotionFamily.Move && Family != MotionFamily.Strafe && Family != MotionFamily.Idle;
            return WorkingLibrary.Find(driver.stance, slot, gait, direction, driver.Mode,
                stage ? driver.SelectionSpeed : driver.Speed, stage ? driver.SelectionAngle : Mathf.Abs(driver.HeadingError), out _);
        }
        public static MotionFamily FamilyForSlot(MotionSlot slot)
        {
            if (slot >= MotionSlot.TurnInPlaceLeft && slot <= MotionSlot.PivotInPlaceRight) return MotionFamily.TurnInPlace;
            if (slot == MotionSlot.Idle || slot == MotionSlot.IdleVariation) return MotionFamily.Idle;
            if (slot == MotionSlot.StopLeft || slot == MotionSlot.StopRight) return MotionFamily.Stop;
            if (slot >= MotionSlot.StrafeForward && slot <= MotionSlot.StrafeBackRight) return MotionFamily.Strafe;
            if (Enum.TryParse(slot.ToString(), out LocomotionPhase phase)) return FamilyFor(phase);
            return MotionFamily.Move;
        }
        public static MotionDirection Direction(float angle) => (MotionDirection)(1 + ((Mathf.RoundToInt(Mathf.Repeat(angle, 360) / 45) + 8) % 8));
        public static MotionFamily FamilyFor(LocomotionPhase p)
        {
            if (MotionLibrary.IsInPlace(p)) return MotionFamily.TurnInPlace;
            switch (p)
            {
                case LocomotionPhase.Idle: return MotionFamily.Idle;
                case LocomotionPhase.Start: return MotionFamily.Start;
                case LocomotionPhase.Stop: return MotionFamily.Stop;
                case LocomotionPhase.Accelerate: return MotionFamily.Accelerate;
                case LocomotionPhase.Decelerate: return MotionFamily.Decelerate;
                case LocomotionPhase.Turn90Left: case LocomotionPhase.Turn90Right: return MotionFamily.Turn;
                case LocomotionPhase.PivotLeft: case LocomotionPhase.PivotRight: return MotionFamily.Pivot;
                case LocomotionPhase.Strafe: return MotionFamily.Strafe;
                case LocomotionPhase.JumpTakeoff: return MotionFamily.Takeoff;
                case LocomotionPhase.JumpRise: case LocomotionPhase.JumpApex: case LocomotionPhase.Fall: return MotionFamily.Air;
                case LocomotionPhase.Land: return MotionFamily.Land;
                default: return MotionFamily.Move;
            }
        }
        public static MotionSlot SlotFor(LocomotionPhase p, float stopPhase)
        {
            if (p == LocomotionPhase.Stop) return stopPhase < 0.5f ? MotionSlot.StopLeft : MotionSlot.StopRight;
            if (p == LocomotionPhase.Move) return MotionSlot.Run;
            if (p == LocomotionPhase.Strafe) return MotionSlot.StrafeForward;
            return Enum.TryParse(p.ToString(), out MotionSlot slot) ? slot : MotionSlot.Idle;
        }
    }
}
