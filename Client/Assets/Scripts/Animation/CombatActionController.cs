using System;
using System.Collections.Generic;
using UnityEngine;

namespace Afauxzhub.Project.Animation
{
    /// <summary>Implement in the game for resource payment, cooldowns and skill-link policy.</summary>
    public interface ICombatActionGate
    {
        bool TryCommit(ActionDefinition action, out string reason);
    }

    [DefaultExecutionOrder(-80)]
    public sealed class CombatActionController : MonoBehaviour
    {
        public CharacterAnimationProfile profile;
        [Tooltip("Must implement ICombatActionGate. Paid actions fail closed if missing.")]
        public MonoBehaviour permissionGate;
        public bool suspended;
        public float playbackRate = 1;
        public ActionDefinition Current { get; private set; }
        public float TimeInAction => (float)clock.Time;
        public ActionPhase Phase { get; private set; }
        public string LastDecision { get; private set; } = "Ready";
        public int Sequence { get; private set; }
        // Movement adapter may fail closed while airborne. Resolved reactions remain authoritative.
        public bool LocomotionInputBlocked { get; set; }
        public event Action<ActionDefinition, ActionDefinition> Changed;
        public event Action<ActionDefinition, ActionWindow, bool> WindowChanged;
        public event Action<ActionDefinition, ActionCue> Cue;
        public event Action<ActionDefinition, bool> Ended;
        private readonly ActionClock clock = new ActionClock();
        private ActionDefinition buffered;
        private float bufferRemaining;
        private bool configuredClock;
        private bool mutating;

        private void Awake() => BindClock();
        private void BindClock()
        {
            if (configuredClock) return;
            configuredClock = true;
            clock.WindowChanged += (i, enter) =>
            {
                var a = Current;
                if (a != null && i < a.windows.Count) WindowChanged?.Invoke(a, a.windows[i], enter);
                // Buffered requests can consume a narrow cancel window even if it ends before this frame does.
                if (enter && Current == a && buffered != null && bufferRemaining > 0 && !mutating) TryStart(buffered, false, false);
            };
            clock.Cue += i => { var a = Current; if (a != null && i < a.cues.Count) Cue?.Invoke(a, a.cues[i]); };
        }

        public bool IsOpen(WindowKind kind)
        {
            if (suspended || Current == null) return false;
            for (int i = 0; i < Current.windows.Count; i++)
                if (Current.windows[i] != null && Current.windows[i].kind == kind && clock.IsActive(i)) return true;
            return false;
        }

        public bool Request(ActionDefinition action, bool buffer = true) => TryStart(action, false, buffer);
        public bool ApplyCombatResult(ActionDefinition reaction) => TryStart(reaction, true, false);

        private bool TryStart(ActionDefinition action, bool resolvedInterrupt, bool buffer)
        {
            BindClock();
            if (mutating) { LastDecision = "Reentrant transition rejected; defer requests until after Ended/Changed callbacks"; return false; }
            if (action == null) { LastDecision = "Action slot not assigned"; return false; }
            if (suspended) { LastDecision = "Combat suspended"; return false; }
            if (LocomotionInputBlocked && !resolvedInterrupt) { LastDecision = "Airborne action policy not configured"; return false; }
            if (action.clip == null) { LastDecision = "Missing clip: " + action.id; return false; }
            foreach (string problem in action.Validate()) { LastDecision = "Invalid action: " + problem; return false; }
            if (!ActionRules.CanRequest(Current != null ? Current.kind : (ActionKind?)null, action.kind, IsOpen, resolvedInterrupt))
            {
                LastDecision = "Blocked by phase/window: " + action.id;
                if (buffer && !ActionRules.IsReaction(action.kind) && action.kind != ActionKind.Counter)
                { buffered = action; bufferRemaining = profile != null ? profile.inputBufferSeconds : 0.15f; }
                return false;
            }
            if (ActionRules.NeedsGate(action.kind))
            {
                var gate = permissionGate as ICombatActionGate;
                if (gate == null) { LastDecision = "Missing combat payment/permission adapter"; return false; }
                if (!gate.TryCommit(action, out string reason)) { LastDecision = reason; return false; }
            }
            mutating = true;
            try
            {
                var previous = Current;
                clock.Stop();
                if (previous != null) Ended?.Invoke(previous, true);
                Current = action; buffered = null; Sequence++;
                Phase = ActionRules.IsReaction(action.kind) ? ActionPhase.Reaction : ActionPhase.Startup;
                LastDecision = "Accepted: " + action.id;
                Changed?.Invoke(previous, action);
                var cues = new List<float>();
                foreach (var c in action.cues) cues.Add(c != null ? c.time : -1);
                clock.Start(action.duration, action.windows, cues);
                return true;
            }
            finally { mutating = false; }
        }

        private void Update()
        {
            if (suspended) { Phase = ActionPhase.Suspended; return; }
            if (Current == null) Phase = ActionPhase.Free;
            if (Current != null)
            {
                float dt = UnityEngine.Time.deltaTime * Mathf.Max(0, playbackRate);
                // A held action stops just before its final boundary so held windows remain active.
                if (Current.hold) dt = Mathf.Min(dt, Mathf.Max(0, Current.duration - 0.0001f - TimeInAction));
                clock.Advance(dt);
                if (Current != null)
                {
                    Phase = Current.kind == ActionKind.Death ? ActionPhase.Dead : ActionRules.IsReaction(Current.kind) ? ActionPhase.Reaction
                        : Current.hold && TimeInAction >= Current.duration - 0.001f ? ActionPhase.Hold
                        : TimeInAction < Current.activeStart ? ActionPhase.Startup : TimeInAction < Current.recoveryStart ? ActionPhase.Active : ActionPhase.Recovery;
                    if (clock.Finished && Current.kind != ActionKind.Death) Finish(false);
                }
            }
            if (buffered != null)
            {
                var next = buffered;
                bufferRemaining -= UnityEngine.Time.deltaTime;
                if (bufferRemaining <= 0) buffered = null;
                else TryStart(next, false, false);
            }
        }

        public void ReleaseHeldAction()
        {
            if (suspended || Current == null || !Current.hold || ActionRules.IsReaction(Current.kind)) return;
            var release = Current.onRelease;
            Finish(false);
            if (release != null) Request(release, false);
        }

        private void Finish(bool interrupted)
        {
            if (mutating) return;
            mutating = true;
            try
            {
                var previous = Current;
                clock.Stop(); Current = null; Phase = ActionPhase.Free;
                if (previous != null) { Ended?.Invoke(previous, interrupted); Changed?.Invoke(previous, null); }
            }
            finally { mutating = false; }
        }

        private void OnDisable() { Finish(true); buffered = null; }
    }
}
