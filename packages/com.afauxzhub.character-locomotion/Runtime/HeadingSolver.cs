using UnityEngine;

namespace Afauxzhub.CharacterLocomotion
{
    /// <summary>
    /// Stateful heading solver. It owns direction math only; input, collision movement,
    /// camera follow and animation playback remain adapters outside this class.
    /// </summary>
    public sealed class HeadingSolver
    {
        private Vector3 solvedDirection;
        private float commandedYawRate;
        private bool turnIntentActive;

        public Vector3 SolvedDirection => solvedDirection;
        public float CommandedYawRate => commandedYawRate;

        public void Reset(Vector3 facing)
        {
            facing.y = 0f;
            solvedDirection = facing.sqrMagnitude > 0.0001f
                ? facing.normalized
                : Vector3.forward;
            commandedYawRate = 0f;
            turnIntentActive = false;
        }

        public LocomotionIntent Step(
            Vector3 currentFacing,
            Vector3 desiredDirection,
            float speed,
            float deltaTime,
            LocomotionProfile profile)
        {
            if (profile == null)
            {
                throw new System.ArgumentNullException(nameof(profile));
            }

            if (solvedDirection.sqrMagnitude <= 0.0001f)
            {
                Reset(currentFacing);
            }

            desiredDirection.y = 0f;
            if (desiredDirection.sqrMagnitude <= 0.0001f || deltaTime <= 0f)
            {
                commandedYawRate = Mathf.MoveTowards(
                    commandedYawRate,
                    0f,
                    profile.yawDeceleration * Mathf.Max(0f, deltaTime));
                return BuildIntent(currentFacing, solvedDirection, solvedDirection, speed, 0f, profile);
            }

            desiredDirection.Normalize();
            float headingError = Vector3.SignedAngle(solvedDirection, desiredDirection, Vector3.up);
            float absoluteError = Mathf.Abs(headingError);

            float sharpWeight = Mathf.SmoothStep(
                0f,
                1f,
                Mathf.InverseLerp(
                    profile.sharpTurnStartAngle,
                    profile.sharpTurnFullAngle,
                    absoluteError));
            float radius = Mathf.Lerp(profile.wideTurnRadius, profile.minimumTurnRadius, sharpWeight);
            float radiusYawRate = SpeedAndRadiusToYawRate(speed, radius);
            float catchUpYawRate = absoluteError / Mathf.Max(0.01f, profile.headingCatchUpTime);
            float allowedYawRate = Mathf.Min(
                profile.maximumYawRate,
                Mathf.Max(radiusYawRate, catchUpYawRate));
            float targetYawRate = Mathf.Clamp(
                headingError / Mathf.Max(0.01f, profile.headingCatchUpTime),
                -allowedYawRate,
                allowedYawRate);

            bool accelerating = Mathf.Abs(commandedYawRate) <= 0.001f
                || (Mathf.Abs(targetYawRate) > Mathf.Abs(commandedYawRate)
                    && Mathf.Sign(targetYawRate) == Mathf.Sign(commandedYawRate));
            float yawAcceleration = accelerating
                ? profile.yawAcceleration
                : profile.yawDeceleration;
            commandedYawRate = Mathf.MoveTowards(
                commandedYawRate,
                targetYawRate,
                yawAcceleration * deltaTime);

            float step = Mathf.Clamp(
                headingError,
                -Mathf.Abs(commandedYawRate) * deltaTime,
                Mathf.Abs(commandedYawRate) * deltaTime);
            solvedDirection = Quaternion.AngleAxis(step, Vector3.up) * solvedDirection;
            solvedDirection.y = 0f;
            solvedDirection.Normalize();

            float appliedYawRate = step / deltaTime;
            return BuildIntent(
                currentFacing,
                desiredDirection,
                solvedDirection,
                speed,
                appliedYawRate,
                profile);
        }

        public static float SpeedAndRadiusToYawRate(float speed, float radius)
        {
            return Mathf.Max(0f, speed) / Mathf.Max(0.1f, radius) * Mathf.Rad2Deg;
        }

        private LocomotionIntent BuildIntent(
            Vector3 currentFacing,
            Vector3 desiredDirection,
            Vector3 resultDirection,
            float speed,
            float appliedYawRate,
            LocomotionProfile profile)
        {
            float absoluteYawRate = Mathf.Abs(appliedYawRate);
            if (turnIntentActive)
            {
                turnIntentActive = absoluteYawRate > profile.turnExitYawRate;
            }
            else
            {
                turnIntentActive = absoluteYawRate >= profile.turnEnterYawRate;
            }

            TurnIntent turn = TurnIntent.Straight;
            if (turnIntentActive)
            {
                turn = appliedYawRate < 0f ? TurnIntent.Left : TurnIntent.Right;
            }

            float headingError = Vector3.SignedAngle(resultDirection, desiredDirection, Vector3.up);
            float turnBlend = turnIntentActive
                ? Mathf.Clamp01(absoluteYawRate / profile.fullTurnYawRate)
                : 0f;
            return new LocomotionIntent(
                desiredDirection,
                resultDirection,
                speed,
                headingError,
                appliedYawRate,
                turnBlend,
                turn,
                CameraRelativeMovement.ClassifyStartDirection(currentFacing, desiredDirection));
        }
    }
}
