using UnityEngine;

namespace Afauxzhub.CharacterLocomotion
{
    public enum StartDirection
    {
        Forward,
        ForwardLeft,
        Left,
        BackwardLeft,
        Backward,
        BackwardRight,
        Right,
        ForwardRight,
    }

    public enum TurnIntent
    {
        Straight,
        Left,
        Right,
    }

    public readonly struct LocomotionIntent
    {
        public LocomotionIntent(
            Vector3 desiredDirection,
            Vector3 solvedDirection,
            float speed,
            float headingError,
            float yawRate,
            float turnBlend,
            TurnIntent turn,
            StartDirection startDirection)
        {
            DesiredDirection = desiredDirection;
            SolvedDirection = solvedDirection;
            Speed = speed;
            HeadingError = headingError;
            YawRate = yawRate;
            TurnBlend = turnBlend;
            Turn = turn;
            StartDirection = startDirection;
        }

        public Vector3 DesiredDirection { get; }
        public Vector3 SolvedDirection { get; }
        public float Speed { get; }
        public float HeadingError { get; }
        public float YawRate { get; }
        public float TurnBlend { get; }
        public TurnIntent Turn { get; }
        public StartDirection StartDirection { get; }
    }
}
