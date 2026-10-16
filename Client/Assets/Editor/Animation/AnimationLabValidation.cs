using System;
using System.Linq;
using Afauxzhub.Project.Animation;
using UnityEditor;
using UnityEngine;
using Object = UnityEngine.Object;

namespace Afauxzhub.Project.Editor.Animation
{
    public static class AnimationLabValidation
    {
        [MenuItem("Tools/MY Project/Animation/Run Editor Logic Checks (no scene save)")]
        public static void Run()
        {
            if (Application.isPlaying) throw new InvalidOperationException("Run these checks outside Play Mode.");
            var action = ScriptableObject.CreateInstance<ActionDefinition>();
            var clip = new AnimationClip();
            GameObject skeleton = null, renderCopy = null;
            int assertions = 0;
            void Check(bool value, string message) { if (!value) throw new InvalidOperationException("Animation lab validation: " + message); assertions++; }
            try
            {
                action.clip = clip; action.kind = ActionKind.LightAttack;
                action.windows.Add(new ActionWindow { id = "evade", kind = WindowKind.CancelToEvade, start = 0.5f, end = 1 });
                action.windows.Add(new ActionWindow { id = "guard", kind = WindowKind.CancelToGuard, start = 0.6f, end = 1 });
                action.windows.Add(new ActionWindow { id = "skill", kind = WindowKind.CancelToSkill, start = 0.7f, end = 1 });
                Check(!action.Validate().Any(), "valid cancellation ordering should pass");
                action.windows[0].start = 0.4f; Check(action.Validate().Any(p => p.Contains("ATK-05")), "reject pre-recovery dodge");
                action.windows[0].start = 0.65f; Check(action.Validate().Any(p => p.Contains("ATK-06")), "reject guard earlier than dodge");
                action.windows[0].start = 0.5f; action.windows[2].start = 0.6f; Check(action.Validate().Any(p => p.Contains("ATK-07")), "skill must be strictly later");
                action.kind = ActionKind.LightHit; Check(action.Validate().Any(p => p.Contains("HIT-02")), "hit-stun cannot gain skill window");
                action.duration = float.NaN; Check(action.Validate().Any(p => p.Contains("Duration")), "NaN duration rejected");
                action.duration = 1; action.windows.Clear();
                action.windows.Add(new ActionWindow { id = "hit", kind = WindowKind.Hitbox, start = 0.4f, end = 0.6f });
                action.animationTime = AnimationCurve.Linear(0, 0, 1, 0.5f);
                Check(Mathf.Abs(action.NormalizedTime(0.5f) - 0.25f) < 0.0001f && action.WindowOpen(WindowKind.Hitbox, 0.5), "pose timing must not move gameplay windows");
                action.windows[0].start = 0.55f;
                Check(!action.WindowOpen(WindowKind.Hitbox, 0.5) && Mathf.Abs(action.NormalizedTime(0.5f) - 0.25f) < 0.0001f, "gameplay window editing must not retime the pose");
                skeleton = new GameObject("Transient IK test") { hideFlags = HideFlags.HideAndDontSave };
                var upper = new GameObject("Upper").transform; upper.SetParent(skeleton.transform); upper.position = new Vector3(0, 2, 0);
                var lower = new GameObject("Lower").transform; lower.SetParent(upper); lower.position = new Vector3(0, 1, 0.15f);
                var foot = new GameObject("Foot").transform; foot.SetParent(lower); foot.position = new Vector3(0, 0, 0);
                float first = Vector3.Distance(upper.position, lower.position), second = Vector3.Distance(lower.position, foot.position);
                var target = new Vector3(0.2f, 0.25f, 0.3f);
                GenericFootIK.SolveTwoBone(upper, lower, foot, target, Vector3.forward);
                Check(Vector3.Distance(foot.position, target) < 0.001f, "IK endpoint must meet reachable target");
                Check(Mathf.Abs(first - Vector3.Distance(upper.position, lower.position)) < 0.001f && Mathf.Abs(second - Vector3.Distance(lower.position, foot.position)) < 0.001f, "IK preserves bone lengths");
                Check(Mathf.Abs(GenericFootIK.RequiredPelvisDrop(-0.15f, 1, 0, 1, 0.2f) + 0.15f) < 0.0001f, "pelvis follows lower supported foot");
                Check(GenericFootIK.RequiredPelvisDrop(-0.5f, 1, 0, 1, 0.2f) == -0.2f, "pelvis drop is bounded");
                Check(GenericFootIK.RequiredPelvisDrop(-0.5f, 0, 0.1f, 1, 0.2f) == 0, "inactive swing foot cannot lower pelvis");
                Check(GenericFootIK.RequiredPelvisDrop(0.1f, 1, 0.2f, 1, 0.2f) == 0, "pelvis correction never raises body");
                Check(GenericFootIK.RequiredPelvisDrop(-0.1f, 1, -0.2f, 1, 0) == 0, "zero drop disables pelvis correction");
                skeleton.AddComponent<BoxCollider>(); skeleton.AddComponent<ActionPresentation>();
                renderCopy = RenderOnlyModel.Copy(skeleton);
                Check(renderCopy.GetComponentsInChildren<MonoBehaviour>(true).Length == 0, "preview must not copy gameplay scripts");
                Check(renderCopy.GetComponentsInChildren<Collider>(true).Length == 0, "preview must not copy physics colliders");
                Debug.Log($"Animation lab Editor checks: {assertions} passed. No scene or source asset saved. Animator transitions, import, particles and animation quality still require Play Mode / visual acceptance.");
            }
            finally
            {
                if (renderCopy != null) Object.DestroyImmediate(renderCopy);
                if (skeleton != null) Object.DestroyImmediate(skeleton);
                Object.DestroyImmediate(action); Object.DestroyImmediate(clip);
            }
        }
    }
}
