using UnityEngine;

namespace Afauxzhub.Project.Locomotion
{
    /// <summary>
    /// Project input boundary. Locomotion consumers receive intent without knowing
    /// which keyboard, gamepad, or input package produced it.
    /// </summary>
    public abstract class MovementInputSource : MonoBehaviour
    {
        public abstract Vector2 ReadMoveInput();
    }
}
