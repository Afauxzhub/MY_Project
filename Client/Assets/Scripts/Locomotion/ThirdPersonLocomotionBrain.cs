using Afauxzhub.CharacterLocomotion;
using UnityEngine;

namespace Afauxzhub.Project.Locomotion
{
    public sealed class ThirdPersonLocomotionBrain : MonoBehaviour
    {
        [Header("Adapters")]
        [SerializeField] private MovementInputSource inputSource;
        [SerializeField] private FixedFollowCameraReference cameraReference;
        [SerializeField] private CharacterControllerMotor motor;
        [SerializeField] private LocomotionProfile profile;

        [Header("Runtime intent (read only)")]
        [SerializeField] private Vector2 input;
        [SerializeField] private Vector3 desiredDirection;
        [SerializeField] private Vector3 solvedDirection;
        [SerializeField] private float speed;
        [SerializeField] private float headingError;
        [SerializeField] private float yawRate;
        [SerializeField] private float turnBlend;
        [SerializeField] private TurnIntent turn;
        [SerializeField] private StartDirection startDirection;

        private readonly HeadingSolver headingSolver = new HeadingSolver();

        public bool IsConfigured => inputSource != null
            && cameraReference != null
            && motor != null
            && profile != null;

        public string ConfigurationStatus => $"input={inputSource != null}, camera={cameraReference != null}, "
            + $"motor={motor != null}, profile={profile != null}";

        public void Configure(
            MovementInputSource movementInput,
            FixedFollowCameraReference movementCamera,
            CharacterControllerMotor movementMotor,
            LocomotionProfile locomotionProfile)
        {
            inputSource = movementInput;
            cameraReference = movementCamera;
            motor = movementMotor;
            profile = locomotionProfile;
        }

        private void OnEnable()
        {
            if (motor != null)
            {
                headingSolver.Reset(motor.Facing);
            }
        }

        private void Update()
        {
            if (!IsConfigured)
            {
                return;
            }

            input = inputSource.ReadMoveInput();
            bool hasMovementIntent = CameraRelativeMovement.TryGetWorldDirection(
                input,
                cameraReference.Forward,
                cameraReference.Right,
                profile.inputDeadZone,
                out desiredDirection);

            speed = hasMovementIntent
                ? profile.runSpeed * Mathf.Clamp01(input.magnitude)
                : 0f;

            LocomotionIntent intent = headingSolver.Step(
                motor.Facing,
                desiredDirection,
                speed,
                Time.deltaTime,
                profile);

            solvedDirection = intent.SolvedDirection;
            headingError = intent.HeadingError;
            yawRate = intent.YawRate;
            turnBlend = intent.TurnBlend;
            turn = intent.Turn;
            startDirection = intent.StartDirection;

            motor.ApplyMovement(intent.SolvedDirection, intent.Speed, hasMovementIntent, Time.deltaTime);
        }

        private void OnDrawGizmosSelected()
        {
            Vector3 origin = transform.position + Vector3.up * 1.2f;
            Gizmos.color = Color.cyan;
            Gizmos.DrawRay(origin, desiredDirection * 2f);
            Gizmos.color = Color.yellow;
            Gizmos.DrawRay(origin, solvedDirection * 2f);
        }
    }
}
