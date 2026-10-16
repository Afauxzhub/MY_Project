using System;

namespace Afauxzhub.CharacterLocomotion
{
    public enum LocomotionPhase { Idle, Start, Move, Accelerate, Decelerate, Stop, PivotLeft, PivotRight, Turn90Left, Turn90Right, Strafe, Fall, Land, JumpTakeoff, JumpRise, JumpApex,
        TurnInPlaceLeft, TurnInPlaceRight, PivotInPlaceLeft, PivotInPlaceRight }

    /// <summary>Engine-independent phase and speed model; all times are profile data.</summary>
    public sealed class LocomotionDynamics
    {
        public LocomotionPhase Phase { get; private set; }
        public float Speed { get; private set; }
        public float PhaseTime { get; private set; }
        public float LatchedTurnAngle { get; private set; }
        private bool groundedLast = true;
        private float releaseTime;
        public bool Turning => Phase == LocomotionPhase.PivotLeft || Phase == LocomotionPhase.PivotRight || Phase == LocomotionPhase.Turn90Left || Phase == LocomotionPhase.Turn90Right;
        public bool TurningInPlace => Phase == LocomotionPhase.TurnInPlaceLeft || Phase == LocomotionPhase.TurnInPlaceRight || Phase == LocomotionPhase.PivotInPlaceLeft || Phase == LocomotionPhase.PivotInPlaceRight;
        public void CancelTurn() { if (Turning || TurningInPlace) Set(Speed > 0.01f ? LocomotionPhase.Move : LocomotionPhase.Idle); }

        public void Reset() { Phase = LocomotionPhase.Idle; Speed = 0; PhaseTime = 0; releaseTime = 0; groundedLast = true; }
        public void Step(float targetSpeed, float headingError, bool targeting, bool grounded, float dt,
            float acceleration, float deceleration, float startDuration, float stopDuration, float pivotDuration,
            float turnDuration, float pivotAngle, float turnAngle, float turnMinSpeed, float releaseDelay, float landDuration, bool targetingPhases = false,
            bool idleTurnEnabled = false, float idleTurnAngle = 60, float idleTurnDuration = 0.35f, float idlePivotDuration = 0.5f, float turnInterrupt = 0.25f)
        {
            if (dt <= 0 || float.IsNaN(dt) || float.IsInfinity(dt)) return;
            PhaseTime += dt;
            bool moving = targetSpeed > 0.01f;
            releaseTime = moving ? 0 : releaseTime + dt;
            float rate = targetSpeed > Speed ? acceleration : deceleration;
            Speed = Approach(Speed, Math.Max(0, targetSpeed), Math.Max(0, rate) * dt);
            if (!grounded) { Set(LocomotionPhase.Fall); groundedLast = false; return; }
            if (!groundedLast) { groundedLast = true; Set(LocomotionPhase.Land); return; }
            if (Phase == LocomotionPhase.Land && PhaseTime < landDuration) return;
            if (TurningInPlace)
            {
                float length = Math.Abs(LatchedTurnAngle) >= pivotAngle ? idlePivotDuration : idleTurnDuration;
                if (!idleTurnEnabled) { Set(moving ? LocomotionPhase.Start : LocomotionPhase.Idle); return; }
                if (moving && PhaseTime >= length * turnInterrupt) { Set(LocomotionPhase.Start); return; }
                if (PhaseTime < length) { Speed = 0; return; }
                Set(moving ? LocomotionPhase.Start : LocomotionPhase.Idle); return;
            }
            if (idleTurnEnabled && !moving && Speed < 0.05f && Phase == LocomotionPhase.Idle && Math.Abs(headingError) >= idleTurnAngle)
            {
                LatchedTurnAngle = headingError; Speed = 0;
                Set(Math.Abs(headingError) >= pivotAngle ? headingError < 0 ? LocomotionPhase.PivotInPlaceLeft : LocomotionPhase.PivotInPlaceRight
                    : headingError < 0 ? LocomotionPhase.TurnInPlaceLeft : LocomotionPhase.TurnInPlaceRight);
                return;
            }
            if (targeting && !targetingPhases) { Set(moving || Speed > 0.01f ? LocomotionPhase.Strafe : LocomotionPhase.Idle); return; }
            if (!targeting && Turning)
            {
                float length = Math.Abs(LatchedTurnAngle) >= pivotAngle ? pivotDuration : turnDuration;
                if (targetingPhases && PhaseTime >= length * turnInterrupt && (!moving || Math.Abs(headingError) >= turnAngle && Math.Sign(headingError) != Math.Sign(LatchedTurnAngle)))
                { Set(moving ? LocomotionPhase.Move : LocomotionPhase.Stop); return; }
                if (PhaseTime < length) return;
                Set(moving ? LocomotionPhase.Move : LocomotionPhase.Stop);
                return; // The motor commits the final turn pose before another turn is considered.
            }
            if (!targeting && moving && (Speed >= turnMinSpeed || Phase == LocomotionPhase.Idle) && Math.Abs(headingError) >= turnAngle)
            {
                LatchedTurnAngle = headingError;
                Set(Math.Abs(headingError) >= pivotAngle
                    ? headingError < 0 ? LocomotionPhase.PivotLeft : LocomotionPhase.PivotRight
                    : headingError < 0 ? LocomotionPhase.Turn90Left : LocomotionPhase.Turn90Right);
                return;
            }
            if (!moving)
            {
                if (releaseTime < releaseDelay && Phase != LocomotionPhase.Idle) return;
                if (Phase != LocomotionPhase.Stop && Phase != LocomotionPhase.Idle) Set(LocomotionPhase.Stop);
                if (Speed <= 0.01f && (Phase != LocomotionPhase.Stop || PhaseTime >= stopDuration)) Set(LocomotionPhase.Idle);
                return;
            }
            if (Phase == LocomotionPhase.Idle || Phase == LocomotionPhase.Stop) { Set(LocomotionPhase.Start); return; }
            if (Phase == LocomotionPhase.Start && PhaseTime < startDuration) return;
            Set(Math.Abs(targetSpeed - Speed) < 0.05f ? targeting ? LocomotionPhase.Strafe : LocomotionPhase.Move : targetSpeed > Speed ? LocomotionPhase.Accelerate : LocomotionPhase.Decelerate);
        }
        private void Set(LocomotionPhase next) { if (next != Phase) { Phase = next; PhaseTime = 0; } }
        private static float Approach(float current, float target, float delta) => Math.Abs(target - current) <= delta ? target : current + Math.Sign(target - current) * delta;
    }
}
