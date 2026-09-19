using UnityEngine;

namespace Afauxzhub.Project.Locomotion
{
    /// <summary>
    /// The sole runtime owner of the player root's final position and rotation.
    /// All other systems submit intent to this component.
    /// </summary>
    [RequireComponent(typeof(CharacterController))]
    public sealed class CharacterControllerMotor : MonoBehaviour
    {
        [SerializeField] private CharacterController characterController;
        [SerializeField, Min(0f)] private float gravity = 20f;
        [SerializeField, Min(0f)] private float groundedPull = 2f;

        private float verticalSpeed;

        public Vector3 Facing => transform.forward;
        public Vector3 Velocity { get; private set; }
        public bool IsGrounded => characterController != null && characterController.isGrounded;
        public bool IsConfigured => characterController != null;

        public void Configure(CharacterController controller, float gravityAcceleration, float groundedDownwardSpeed)
        {
            characterController = controller;
            gravity = Mathf.Max(0f, gravityAcceleration);
            groundedPull = Mathf.Max(0f, groundedDownwardSpeed);
        }

        private void Reset()
        {
            characterController = GetComponent<CharacterController>();
        }

        public void ApplyMovement(Vector3 solvedDirection, float speed, bool hasMovementIntent, float deltaTime)
        {
            if (characterController == null)
            {
                throw new MissingComponentException("CharacterControllerMotor requires a configured CharacterController.");
            }

            if (deltaTime <= 0f)
            {
                return;
            }

            solvedDirection.y = 0f;
            bool hasSolvedDirection = solvedDirection.sqrMagnitude > 0.0001f;
            if (hasSolvedDirection)
            {
                solvedDirection.Normalize();
                transform.rotation = Quaternion.LookRotation(solvedDirection, Vector3.up);
            }

            if (characterController.isGrounded && verticalSpeed < 0f)
            {
                verticalSpeed = -groundedPull;
            }
            else
            {
                verticalSpeed -= gravity * deltaTime;
            }

            Vector3 horizontalVelocity = hasMovementIntent && hasSolvedDirection
                ? solvedDirection * Mathf.Max(0f, speed)
                : Vector3.zero;
            Velocity = horizontalVelocity + Vector3.up * verticalSpeed;
            characterController.Move(Velocity * deltaTime);
        }
    }
}
