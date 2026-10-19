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
        private double cycleAge;
        public float Cycle => Mathf.Repeat((float)(cycleAge % 1), 1);
        private RootMotionFrame pendingCompletion, completedFrame;
        private CombatActionController subscribedCombat;
        public RootMotionFrame CompletionFrame => completedFrame;
        public RootMotionFrame RootFrame
        {
            get
            {
                var result = Player != null ? Player.RootFrame : default;
                result.localDelta += completedFrame.localDelta; result.yaw += completedFrame.yaw;
                result.positionWeight = Mathf.Max(result.positionWeight, completedFrame.positionWeight);
                result.rotationWeight = Mathf.Max(result.rotationWeight, completedFrame.rotationWeight);
                result.verticalWeight = Mathf.Max(result.verticalWeight, completedFrame.verticalWeight);
                return result;
            }
        }
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
        private bool rebaseActionOnNextSample;
        private float lastActionBlendOut;
        private float startAngle;
        private LocomotionPhase previousPhase;
        private float stopPhase;
        private bool idleVariationActive;

        public bool Ready => enabled && library != null && driver != null;
        public void Ensure()
        {
            if (subscribedCombat != driver?.combat)
            {
                if (subscribedCombat != null) subscribedCombat.Ended -= ActionEnded;
                subscribedCombat = driver?.combat;
                if (subscribedCombat != null) subscribedCombat.Ended += ActionEnded;
            }
            if (WorkingLibrary == null && library != null) ApplyDraft(library);
            if (Player == null && driver != null && driver.animator != null)
            { Player = new ClipBlendPlayer(driver.animator); rebaseActionOnNextSample = true; }
        }
        private void ActionEnded(ActionDefinition action, bool interrupted)
        {
            // Combat owns the end boundary. Consume only the unsampled final fraction, never the
            // rest of an interrupted animation; gameplay windows/timing are not delayed for animation.
            if (!interrupted && acting && Player != null)
                pendingCompletion = Player.CompleteRootSample(action.id, action.NormalizedTime(action.duration));
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
            void Release(UnityEngine.Object value) { if (Application.isPlaying) Destroy(value); else DestroyImmediate(value); }
            Release(WorkingLibrary.relaxedMovement); Release(WorkingLibrary.readyMovement); Release(WorkingLibrary.templates); Release(WorkingLibrary); WorkingLibrary = null;
        }
        private void OnDisable()
        {
            if (subscribedCombat != null) subscribedCombat.Ended -= ActionEnded;
            subscribedCombat = null; pendingCompletion = completedFrame = default;
            Player?.Dispose(); Player = null; requestKey = null;
        }
        private void OnDestroy() => DestroyWorking();

        public void Tick(ActionDefinition action, LocomotionProfile movement, float dt)
        {
            Ensure(); if (Player == null || WorkingLibrary == null) return;
            if (driver.combat != null && driver.combat.suspended) return;
            completedFrame = pendingCompletion; pendingCompletion = default;
            if (action == null && !acting && driver.CompletedMotionPhase && !(Player.Key?.EndsWith("/bridge", StringComparison.Ordinal) ?? false)) completedFrame = Player.CompleteOneShots();
            var lib = WorkingLibrary;
            samples.Clear(); missing.Clear();
            if (action != null)
            {
                if (!acting || actionSequence != driver.combat.Sequence)
                { actionSequence = driver.combat.Sequence; requestKey = null; }
                acting = true; lastActionBlendOut = action.blendOut; Family = MotionFamily.Action;
                var root = new RootMotionSettings { enabled = action.movement == MovementAuthority.RootMotion,
                    rotation = action.applyRootRotation, vertical = action.rootMotion != null && action.rootMotion.vertical,
                    scale = action.rootMotionScale, track = action.rootMotion?.track };
                samples.Add(new MotionSample(action.id, action.clip, 1, action.NormalizedTime(driver.combat.TimeInAction))
                    { rootMotion = root, rootHasStart = true, rootInitialPhase = action.NormalizedTime(rebaseActionOnNextSample ? driver.combat.TimeInAction : 0) });
                rebaseActionOnNextSample = false;
                Player.SetTarget("action/" + actionSequence, samples, action.blendIn);
                Player.Evaluate(dt); Player.CopyPoseSamples(poseSamples); Support = lib.Support(poseSamples);
                Decision = "Combat permission accepted / " + action.id; Missing = action.clip == null ? "Combat clip missing: " + action.id : ""; return;
            }
            rebaseActionOnNextSample = false;
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
                if (activeRecipe != null && !activeRecipe.preserveCyclePhase) cycleAge = activeRecipe.targetPhase;
                requestKey = key; Family = family;
            }
            requestTime += dt;
            if (activeRecipe != null) blend = activeRecipe.blendSeconds;
            if (acting) { blend = lastActionBlendOut; acting = false; }
            var bridge = activeRecipe != null ? lib.ById(activeRecipe.bridgeEntry) : null;
            if (bridge?.clip != null && requestTime < activeRecipe.bridgeSeconds)
            {
                AddEntry(bridge, 1, requestTime / Mathf.Max(0.01f, activeRecipe.bridgeSeconds), false);
                if (samples.Count > 0) { var first = samples[0]; first.rootHasStart = true; first.rootInitialPhase = 0; samples[0] = first; }
                Player.SetTarget(key + "/bridge", samples, blend, activeRecipe.weight);
            }
            else
            {
                if (bridge != null)
                {
                    if (!bridgeFinished) completedFrame = Player.CompleteOneShots();
                    blend = activeRecipe.bridgeOutSeconds; bridgeFinished = true;
                }
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
                    if (vary != idleVariationActive) { cycleAge = 0; idleVariationActive = vary; }
                    Add(vary ? MotionSlot.IdleVariation : MotionSlot.Idle, MotionGait.Any, MotionDirection.Any, 1, cycleAge, true);
                    AdvanceCycle(dt);
                }
                else
                {
                    bool loop = family == MotionFamily.Air;
                    float phaseTime = driver.PhaseNormalized;
                    if (activeRecipe != null && !activeRecipe.preserveCyclePhase) phaseTime = Mathf.Lerp(activeRecipe.targetPhase, 1, phaseTime);
                    Add(SelectedSlot, gait, family == MotionFamily.Start ? direction : MotionDirection.Any, 1, loop ? cycleAge : phaseTime, loop);
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
            double step = dt * PlaybackScale / Mathf.Max(0.1f, duration / Mathf.Max(0.001f, weight));
            cycleAge += step;
            // Select weights at the current phase, then sample the END of this frame's interval.
            // Sampling before advancing delays root travel by a frame: after a hitch, a tiny frame
            // would receive the previous long frame's displacement and an invalid Motor velocity.
            for (int i = 0; i < samples.Count; i++)
            {
                var sample = samples[i];
                if (!sample.rootLoop) continue;
                sample.rootHasStart = true; sample.rootInitialPhase = sample.rootPhase;
                sample.rootPhase += step;
                sample.normalizedTime = Mathf.Lerp(sample.rootStart, sample.rootEnd, Mathf.Repeat((float)(sample.rootPhase % 1), 1));
                samples[i] = sample;
            }
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
                Add(slots[low], gait, MotionDirection.Any, weight * (1 - (angle - Mathf.Floor(angle))), cycleAge, true);
                Add(slots[high], gait, MotionDirection.Any, weight * (angle - Mathf.Floor(angle)), cycleAge, true);
            }
            else if (gait == MotionGait.Walk) Add(MotionSlot.Walk, gait, MotionDirection.Any, weight, cycleAge, true);
            else
            {
                float turn = Mathf.Clamp(driver.TurnBlend, -1, 1), t = Mathf.Abs(turn);
                MotionSlot straight = gait == MotionGait.Sprint ? MotionSlot.Sprint : MotionSlot.Run;
                MotionSlot arc = gait == MotionGait.Sprint ? turn < 0 ? MotionSlot.SprintLeft : MotionSlot.SprintRight : turn < 0 ? MotionSlot.ArcLeft : MotionSlot.ArcRight;
                if (gait == MotionGait.Sprint || t <= 0.5f)
                { float a = gait == MotionGait.Sprint ? t : t * 2; Add(straight, gait, MotionDirection.Any, weight * (1 - a), cycleAge, true); Add(arc, gait, MotionDirection.Any, weight * a, cycleAge, true); }
                else
                { Add(arc, gait, MotionDirection.Any, weight * (2 - t * 2), cycleAge, true); Add(turn < 0 ? MotionSlot.ArcSharpLeft : MotionSlot.ArcSharpRight, gait, MotionDirection.Any, weight * (t * 2 - 1), cycleAge, true); }
            }
        }
        private void Add(MotionSlot slot, MotionGait gait, MotionDirection direction, float weight, double time, bool loop)
        {
            if (weight < 0.0001f) return;
            var entry = Find(slot, gait, direction);
            bool poseOnlyFallback = false;
            if (entry == null)
            {
                if (slot == MotionSlot.Start && direction != MotionDirection.Forward)
                    entry = Find(slot, gait, MotionDirection.Forward);
                if (entry == null && (slot == MotionSlot.Walk || slot == MotionSlot.Sprint || slot >= MotionSlot.ArcLeft && slot <= MotionSlot.SprintRight))
                    entry = Find(MotionSlot.Run, MotionGait.Any, MotionDirection.Any);
                if (entry == null) entry = Find(MotionSlot.Idle, MotionGait.Any, MotionDirection.Any);
                // Missing directional locomotion may borrow a pose, not an unrelated trajectory.
                // In particular a rooted Idle must not consume movement ownership for missing Strafe.
                poseOnlyFallback = entry != null && (entry.slot == MotionSlot.Idle
                    || slot == MotionSlot.Start && direction != MotionDirection.Forward);
                missing.Add(slot + (direction != MotionDirection.Any ? "/" + direction : "") + " → " + (entry != null ? entry.slot.ToString() : "NO CLIP"));
            }
            if (entry != null)
            {
                AddEntry(entry, weight, time, loop);
                if (poseOnlyFallback) { var sample = samples[samples.Count - 1]; sample.rootMotion = null; samples[samples.Count - 1] = sample; }
            }
        }
        private void AddEntry(MotionEntry entry, float weight, double time, bool loop)
        {
            var sample = entry.Sample(time, weight, loop);
            if (loop) { sample.rootHasStart = true; sample.rootInitialPhase = sample.rootPhase; }
            samples.Add(sample);
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
