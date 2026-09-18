using UnityEngine;

namespace Afauxzhub.CharacterLocomotion
{
    public static class CameraRelativeMovement
    {
        public static bool TryGetWorldDirection(
            Vector2 input,
            Vector3 cameraForward,
            Vector3 cameraRight,
            float deadZone,
            out Vector3 direction)
        {
            direction = Vector3.zero;
            if (input.sqrMagnitude <= deadZone * deadZone)
            {
                return false;
            }

            cameraForward.y = 0f;
            cameraRight.y = 0f;
            if (cameraForward.sqrMagnitude <= 0.0001f || cameraRight.sqrMagnitude <= 0.0001f)
            {
                cameraForward = Vector3.forward;
                cameraRight = Vector3.right;
            }
            else
            {
                cameraForward.Normalize();
                cameraRight.Normalize();
            }

            direction = cameraForward * input.y + cameraRight * input.x;
            direction.y = 0f;
            if (direction.sqrMagnitude <= 0.0001f)
            {
                return false;
            }

            direction.Normalize();
            return true;
        }

        public static StartDirection ClassifyStartDirection(Vector3 facing, Vector3 desiredDirection)
        {
            facing.y = 0f;
            desiredDirection.y = 0f;
            if (facing.sqrMagnitude <= 0.0001f || desiredDirection.sqrMagnitude <= 0.0001f)
            {
                return StartDirection.Forward;
            }

            float angle = Vector3.SignedAngle(facing, desiredDirection, Vector3.up);
            int sector = Mathf.RoundToInt(angle / 45f);
            sector = (sector % 8 + 8) % 8;
            switch (sector)
            {
                case 1: return StartDirection.ForwardRight;
                case 2: return StartDirection.Right;
                case 3: return StartDirection.BackwardRight;
                case 4: return StartDirection.Backward;
                case 5: return StartDirection.BackwardLeft;
                case 6: return StartDirection.Left;
                case 7: return StartDirection.ForwardLeft;
                default: return StartDirection.Forward;
            }
        }
    }
}
