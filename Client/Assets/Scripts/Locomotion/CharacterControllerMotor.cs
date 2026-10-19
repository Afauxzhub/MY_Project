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
        [SerializeField, Min(0f), Tooltip("Maximum downward correction from a grounded frame; never used while rising or after leaving a ledge.")]
        private float groundSnapDistance = 0.35f;
        private readonly RaycastHit[] groundHits = new RaycastHit[16];

        private float verticalSpeed;

        public Vector3 Facing => transform.forward;
        public Vector3 Velocity { get; private set; }
        public bool IsGrounded => characterController != null && characterController.isGrounded;
        public bool IsConfigured => characterController != null;
        public float VerticalSpeed => verticalSpeed;
        public CollisionFlags LastCollision { get; private set; }

        public bool TryJump(float height)
        {
            if (!IsGrounded || verticalSpeed > 0 || gravity <= 0 || float.IsNaN(gravity) || float.IsInfinity(gravity) || height <= 0 || float.IsNaN(height) || float.IsInfinity(height)) return false;
            verticalSpeed = Mathf.Sqrt(2 * gravity * height);
            return true;
        }

        public void ApplyDisplacement(Vector3 horizontalDelta, Quaternion facing, float deltaTime, float authoredVerticalWeight = 0)
        {
            if (characterController == null || deltaTime <= 0 || float.IsNaN(deltaTime) || float.IsInfinity(deltaTime)) return;
            transform.rotation = facing;
            authoredVerticalWeight = Mathf.Clamp01(authoredVerticalWeight);
            bool canSnap = characterController.isGrounded && verticalSpeed <= 0 && authoredVerticalWeight <= 0;
            float verticalDelta;
            if (characterController.isGrounded && verticalSpeed < 0)
            { verticalSpeed = -groundedPull; verticalDelta = verticalSpeed * deltaTime; }
            else
            {
                // Integrate constant gravity analytically: the jump apex should not depend on frame rate.
                verticalDelta = verticalSpeed * deltaTime - 0.5f * gravity * deltaTime * deltaTime;
                verticalSpeed -= gravity * deltaTime;
            }
            Vector3 before = transform.position;
            LastCollision = characterController.Move(horizontalDelta + Vector3.up * (verticalDelta * (1 - authoredVerticalWeight)));
            // Returning to physics inherits collision-resolved vertical motion, never a hidden gravity debt.
            if (authoredVerticalWeight > 0) verticalSpeed = (transform.position.y - before.y) / deltaTime;
            if (canSnap && !characterController.isGrounded && groundSnapDistance > 0)
            {
                // Sweep the lower capsule, not a point ray: handles slope contact without
                // pretending a nearby floor is ground after a real ledge departure.
                var bounds = characterController.bounds;
                float radius = Mathf.Min(bounds.extents.x, bounds.extents.z);
                float lift = Mathf.Max(0.05f, characterController.skinWidth);
                Vector3 lowerSphere = new Vector3(bounds.center.x, bounds.min.y + radius, bounds.center.z);
                int count = Physics.SphereCastNonAlloc(lowerSphere + Vector3.up * lift,
                    Mathf.Max(0.01f, radius - 0.01f), Vector3.down, groundHits,
                    lift + groundSnapDistance, Physics.DefaultRaycastLayers, QueryTriggerInteraction.Ignore);
                float nearest = float.PositiveInfinity;
                for (int i = 0; i < count; i++)
                {
                    var hit = groundHits[i];
                    if (hit.collider == characterController || hit.collider.transform.IsChildOf(transform)
                        || Physics.GetIgnoreLayerCollision(gameObject.layer, hit.collider.gameObject.layer)
                        || Physics.GetIgnoreCollision(characterController, hit.collider)
                        || Vector3.Angle(hit.normal, Vector3.up) > characterController.slopeLimit) continue;
                    nearest = Mathf.Min(nearest, hit.distance);
                }
                // A saturated query fails closed rather than selecting an arbitrary hidden surface.
                if (count < groundHits.Length && !float.IsInfinity(nearest))
                    LastCollision |= characterController.Move(Vector3.down * Mathf.Max(0, nearest - lift + characterController.skinWidth));
            }
            if ((LastCollision & CollisionFlags.Above) != 0 && verticalSpeed > 0) verticalSpeed = 0;
            if (characterController.isGrounded && verticalSpeed < 0) verticalSpeed = -groundedPull;
            Velocity = (transform.position - before) / deltaTime;
        }

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

            Vector3 horizontalVelocity = hasMovementIntent && hasSolvedDirection
                ? solvedDirection * Mathf.Max(0f, speed)
                : Vector3.zero;
            ApplyDisplacement(horizontalVelocity * deltaTime, transform.rotation, deltaTime);
        }
    }
}
