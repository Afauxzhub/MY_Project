using UnityEngine;

namespace Afauxzhub.CharacterLocomotion
{
    [CreateAssetMenu(
        fileName = "LocomotionProfile",
        menuName = "Afauxzhub/Locomotion/Profile")]
    public sealed class LocomotionProfile : ScriptableObject
    {
        [Header("Input")]
        [Min(0f)] public float inputDeadZone = 0.1f;

        [Header("Speed")]
        [Min(0f)] public float runSpeed = 5f;
        [Min(0f)] public float sprintSpeed = 8f;
        [Min(0f)] public float walkSpeed = 2f;
        [Min(0.01f)] public float acceleration = 12f;
        [Min(0.01f)] public float deceleration = 16f;
        public AnimationCurve accelerationBySpeed = AnimationCurve.Linear(0, 1, 1, 0.5f);
        public AnimationCurve decelerationBySpeed = AnimationCurve.Linear(0, 1, 1, 1);

        [Header("Movement phases (seconds; tuning data)")]
        [Min(0.01f)] public float startDuration = 0.25f;
        [Min(0.01f)] public float stopDuration = 0.3f;
        [Min(0.01f)] public float pivotDuration = 0.45f;
        [Min(0.01f)] public float turn90Duration = 0.3f;
        [Min(0.01f)] public float landDuration = 0.2f;
        [Range(90, 180)] public float pivotAngle = 140f;
        [Range(45, 135)] public float turn90Angle = 75f;
        [Min(0)] public float turnMinimumSpeed = 1f;
        [Min(0)] public float releaseDelay = 0.08f;
        public AnimationCurve turnProgress = AnimationCurve.EaseInOut(0, 0, 1, 1);
        public AnimationCurve turnSpeedScale = new AnimationCurve(new Keyframe(0, 0.4f), new Keyframe(0.5f, 0.15f), new Keyframe(1, 1));
        [Header("Stationary facing turns (no movement / no IK)")]
        public bool enableTurnInPlace = true;
        [Range(5, 135)] public float idleTurnAngle = 60;
        [Min(0.01f)] public float idleTurnDuration = 0.35f;
        [Min(0.01f)] public float idlePivotDuration = 0.5f;
        [Range(0, 1)] public float turnInterrupt = 0.25f;

        [Header("Target facing locomotion")]
        [Min(0)] public float strafeSpeed = 3f;
        [Range(0, 1)] public float backwardSpeedScale = 0.7f;
        [Min(0)] public float targetFacingSpeed = 540f;
        [Tooltip("Enforce speed/radius for moving arc turns; sharp pivots have their own phase.")]
        public bool constrainArcRadius;

        [Header("Heading")]
        [Tooltip("Wide turns use this radius in metres.")]
        [Min(0.1f)] public float wideTurnRadius = 5f;
        [Tooltip("Sharp turns approach this minimum radius in metres.")]
        [Min(0.1f)] public float minimumTurnRadius = 1.5f;
        [Tooltip("Heading error at which the solver begins approaching the minimum radius.")]
        [Range(0f, 180f)] public float sharpTurnStartAngle = 35f;
        [Tooltip("Heading error at which the solver may fully use the minimum radius.")]
        [Range(0f, 180f)] public float sharpTurnFullAngle = 90f;
        [Min(0.01f)] public float headingCatchUpTime = 0.2f;
        [Min(0f)] public float maximumYawRate = 360f;
        [Min(0f)] public float yawAcceleration = 1200f;
        [Min(0f)] public float yawDeceleration = 1600f;

        [Header("Animation intent")]
        [Tooltip("Yaw rate below this value is treated as visually straight locomotion.")]
        [Min(0f)] public float turnEnterYawRate = 12f;
        [Tooltip("Hysteresis exit threshold for the turn intent.")]
        [Min(0f)] public float turnExitYawRate = 5f;
        [Tooltip("Maximum absolute yaw rate represented by a full turn blend value.")]
        [Min(0.1f)] public float fullTurnYawRate = 180f;

        private void OnValidate()
        {
            minimumTurnRadius = Mathf.Max(0.1f, minimumTurnRadius);
            wideTurnRadius = Mathf.Max(minimumTurnRadius, wideTurnRadius);
            sharpTurnFullAngle = Mathf.Max(sharpTurnStartAngle + 0.1f, sharpTurnFullAngle);
            turnEnterYawRate = Mathf.Max(turnExitYawRate, turnEnterYawRate);
        }
    }
}
