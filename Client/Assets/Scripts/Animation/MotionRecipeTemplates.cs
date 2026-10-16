using System.Collections.Generic;
using UnityEngine;

namespace Afauxzhub.Project.Animation
{
    [CreateAssetMenu(menuName = "MY Project/Animation/Transition Templates")]
    public sealed class MotionRecipeTemplates : ScriptableObject
    {
        public List<MotionRecipe> recipes = new List<MotionRecipe>();
    }
}
