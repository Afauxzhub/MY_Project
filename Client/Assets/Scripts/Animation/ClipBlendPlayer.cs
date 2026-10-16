using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Animations;
using UnityEngine.Playables;

namespace Afauxzhub.Project.Animation
{
    public struct MotionSample
    {
        public string id;
        public AnimationClip clip;
        public float weight, normalizedTime;
        public MotionSample(string id, AnimationClip clip, float weight, float normalizedTime)
        { this.id = id; this.clip = clip; this.weight = weight; this.normalizedTime = normalizedTime; }
    }

    /// <summary>Same explicitly sampled mixer for isolated editor preview and runtime. No controller/state paths.</summary>
    public sealed class ClipBlendPlayer : IDisposable
    {
        // Retain the dominant outgoing poses under repeated interruption; never evict live targets.
        public const int MaximumOutgoingVoices = 16;
        private sealed class Voice
        {
            public AnimationClipPlayable playable;
            public AnimationClip clip;
            public string id;
            public float weight, sourceWeight, targetWeight;
            public double seconds;
            public bool target;
        }
        private readonly List<Voice> voices = new List<Voice>();
        private PlayableGraph graph;
        private AnimationMixerPlayable mixer;
        private Animator animator;
        private RuntimeAnimatorController previousController;
        private bool previousRootMotion;
        private bool previousFireEvents;
        private float elapsed, duration;
        private AnimationCurve curve;
        public string Key { get; private set; }
        public float BlendProgress => duration <= 0 ? 1 : Mathf.Clamp01(elapsed / duration);
        public int VoiceCount => voices.Count;
        public float WeightSum { get { float sum = 0; foreach (var v in voices) sum += v.weight; return sum; } }
        public bool IsValid => graph.IsValid();
        // Diagnostics subscribe to actual pose evaluation, not a slower Editor repaint/update loop.
        public event Action<ClipBlendPlayer> Evaluated;

        public ClipBlendPlayer(Animator target)
        {
            if (target == null) throw new ArgumentNullException(nameof(target));
            animator = target; previousController = target.runtimeAnimatorController;
            previousRootMotion = target.applyRootMotion; previousFireEvents = target.fireEvents;
            target.runtimeAnimatorController = null;
            // Events are evaluated by the independent action clock, never by arbitrary source Clip events.
            target.fireEvents = false;
            target.applyRootMotion = false; // This backend currently advertises procedural Motor only.
            graph = PlayableGraph.Create("No-wires animation / " + target.name);
            graph.SetTimeUpdateMode(DirectorUpdateMode.Manual);
            mixer = AnimationMixerPlayable.Create(graph, 0);
            var output = AnimationPlayableOutput.Create(graph, "Pose", target);
            output.SetSourcePlayable(mixer);
            graph.Play();
        }

        public void SetTarget(string key, IList<MotionSample> samples, float blend, AnimationCurve weights = null)
        {
            bool changed = key != Key;
            if (changed)
            {
                Key = key; elapsed = 0; duration = Mathf.Max(0, blend); curve = weights;
                foreach (var voice in voices) { voice.sourceWeight = voice.weight; voice.target = false; voice.targetWeight = 0; }
            }
            foreach (var voice in voices) if (voice.target) voice.targetWeight = 0;
            float sum = 0; foreach (var s in samples) if (s.clip != null) sum += Mathf.Max(0, s.weight);
            foreach (var sample in samples)
            {
                if (sample.clip == null || sample.weight <= 0) continue;
                // Only reuse current target voices: restarting the same action owns a new clock.
                Voice voice = voices.Find(v => v.target && v.id == sample.id && v.clip == sample.clip);
                if (voice == null)
                {
                    voice = new Voice { id = sample.id, clip = sample.clip, target = true, playable = AnimationClipPlayable.Create(graph, sample.clip) };
                    voice.playable.SetApplyFootIK(false); voice.playable.SetApplyPlayableIK(false); voice.playable.SetSpeed(0);
                    int port = voices.Count; voices.Add(voice); mixer.SetInputCount(voices.Count); graph.Connect(voice.playable, 0, mixer, port);
                }
                voice.targetWeight += Mathf.Max(0, sample.weight) / Mathf.Max(0.00001f, sum);
                voice.seconds = Mathf.Clamp01(sample.normalizedTime) * sample.clip.length;
                voice.playable.SetTime(voice.seconds);
            }
            if (changed && voices.TrueForAll(v => v.sourceWeight <= 0)) duration = 0;
        }

        public void Evaluate(float deltaTime)
        {
            if (!graph.IsValid()) return;
            elapsed += Mathf.Max(0, deltaTime);
            float t = BlendProgress;
            float w = t >= 1 ? 1 : t <= 0 ? 0 : Mathf.Clamp01(curve != null ? curve.Evaluate(t) : t);
            int outgoing = 0;
            foreach (var v in voices) if (!v.target || v.targetWeight <= 0) outgoing++;
            while (outgoing > MaximumOutgoingVoices)
            {
                int weakest = -1;
                for (int i = 0; i < voices.Count; i++)
                    if ((!voices[i].target || voices[i].targetWeight <= 0) && (weakest < 0 || voices[i].sourceWeight < voices[weakest].sourceWeight)) weakest = i;
                if (weakest < 0) break;
                Remove(weakest); outgoing--;
            }
            // Pruning outgoing tails must not reduce the sum of pose weights.
            float sourceSum = 0; foreach (var v in voices) sourceSum += v.sourceWeight;
            if (sourceSum > 0) foreach (var v in voices) v.sourceWeight /= sourceSum;
            for (int i = 0; i < voices.Count; i++)
            {
                var v = voices[i]; v.weight = v.sourceWeight * (1 - w) + v.targetWeight * w;
                mixer.SetInputWeight(i, v.weight);
            }
            // Retire zero-weight sources, keeping the graph bounded during rapid interruptions.
            for (int i = voices.Count - 1; i >= 0; i--)
                if ((!voices[i].target || voices[i].targetWeight <= 0) && voices[i].weight < 0.00001f) Remove(i);
            float total = WeightSum;
            if (total > 0)
                for (int i = 0; i < voices.Count; i++) { voices[i].weight /= total; mixer.SetInputWeight(i, voices[i].weight); }
            graph.Evaluate(0);
            Evaluated?.Invoke(this);
        }
        private void Remove(int index)
        {
            int last = voices.Count - 1;
            graph.Disconnect(mixer, index); graph.DestroyPlayable(voices[index].playable);
            if (index != last)
            {
                graph.Disconnect(mixer, last); voices[index] = voices[last];
                graph.Connect(voices[index].playable, 0, mixer, index); mixer.SetInputWeight(index, voices[index].weight);
            }
            voices.RemoveAt(last); mixer.SetInputCount(voices.Count);
        }
        public string Describe()
        {
            var result = new System.Text.StringBuilder();
            foreach (var v in voices) if (v.weight > 0.001f) result.AppendLine($"{v.clip.name}  {v.weight:P0}  {v.seconds:F3}s{(v.target ? " target" : " outgoing")}");
            return result.ToString();
        }
        public double TimeFor(string id, bool target)
        { var v = voices.Find(voice => voice.id == id && voice.target == target); return v != null ? v.seconds : -1; }
        public void CopyPoseSamples(List<MotionSample> destination)
        {
            destination.Clear();
            foreach (var v in voices) if (v.weight > 0.0001f && v.clip != null)
                destination.Add(new MotionSample(v.id, v.clip, v.weight, (float)(v.seconds / Mathf.Max(0.0001f, v.clip.length))));
        }
        public void Dispose()
        {
            if (graph.IsValid()) graph.Destroy(); voices.Clear();
            if (animator != null) { animator.runtimeAnimatorController = previousController; animator.applyRootMotion = previousRootMotion; animator.fireEvents = previousFireEvents; }
            animator = null;
        }
    }
}
