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
