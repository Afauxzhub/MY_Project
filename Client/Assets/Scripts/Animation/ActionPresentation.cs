using System;
using System.Collections.Generic;
using UnityEngine;

namespace Afauxzhub.Project.Animation
{
    /// <summary>Presentation only. Hit shapes below are debug geometry, never a damage resolver.</summary>
    public sealed class ActionPresentation : MonoBehaviour
    {
        public CombatActionController combat;
        public Transform skeletonRoot;
        public bool showHitShapes = true;
        public event Action<float> CameraImpulse;
        public event Action<string> Marker;
        private sealed class Spawned { public GameObject gameObject; public float remaining; }
        private readonly List<Spawned> spawned = new List<Spawned>();
        private bool paused;
        private CombatActionController bound;
        private void OnEnable() => Bind();
        private void Start() => Bind();
        private void Bind()
        {
            if (bound == combat) return;
            Unbind(); bound = combat;
            if (bound == null) return;
            bound.Cue += OnCue; bound.Ended += OnEnded;
        }
        private void Unbind()
        {
            if (bound != null) { bound.Cue -= OnCue; bound.Ended -= OnEnded; }
            bound = null;
        }
        private void OnDisable() { Unbind(); Clear(); }
        private void OnEnded(ActionDefinition action, bool interrupted) => Clear();
        private void Update()
        {
            bool freeze = combat != null && combat.suspended;
            for (int i = spawned.Count - 1; i >= 0; i--)
            {
                var item = spawned[i];
                if (item.gameObject == null) { spawned.RemoveAt(i); continue; }
                if (freeze != paused)
                {
                    foreach (var ps in item.gameObject.GetComponentsInChildren<ParticleSystem>()) { if (freeze) ps.Pause(false); else ps.Play(false); }
                    foreach (var sound in item.gameObject.GetComponentsInChildren<AudioSource>()) { if (freeze) sound.Pause(); else sound.UnPause(); }
                }
                if (!freeze) item.remaining -= Time.deltaTime;
                if (item.remaining <= 0) { Destroy(item.gameObject); spawned.RemoveAt(i); }
            }
            paused = freeze;
        }
        private void Clear()
        {
            foreach (var instance in spawned) if (instance.gameObject != null) Destroy(instance.gameObject);
            spawned.Clear();
        }
        private void OnCue(ActionDefinition action, ActionCue cue)
        {
            var root = skeletonRoot != null ? skeletonRoot : transform;
            var socket = string.IsNullOrEmpty(cue.socketPath) ? root : root.Find(cue.socketPath);
            if (socket == null) { Debug.LogWarning("Missing action socket: " + cue.socketPath, this); return; }
            if (cue.kind == CueKind.Effect && cue.effect != null)
            {
                var go = Instantiate(cue.effect, socket);
                go.transform.localPosition = cue.offset;
                go.transform.localRotation = Quaternion.identity;
                spawned.Add(new Spawned { gameObject = go, remaining = Mathf.Max(0.01f, cue.lifetime) });
            }
            else if (cue.kind == CueKind.Sound && cue.sound != null)
            {
                var go = new GameObject("Action sound"); go.transform.position = socket.TransformPoint(cue.offset);
                var source = go.AddComponent<AudioSource>(); source.clip = cue.sound; source.spatialBlend = 1; source.Play();
                spawned.Add(new Spawned { gameObject = go, remaining = cue.sound.length + 0.1f });
            }
            else if (cue.kind == CueKind.CameraImpulse) CameraImpulse?.Invoke(cue.intensity);
            else if (cue.kind == CueKind.Marker) Marker?.Invoke(cue.id);
        }
        private void OnDrawGizmos()
        {
            if (!showHitShapes || combat == null || combat.Current == null) return;
            var root = skeletonRoot != null ? skeletonRoot : transform;
            var original = Gizmos.matrix;
            foreach (var shape in combat.Current.hitShapes)
            {
                if (shape == null) continue;
                var w = combat.Current.windows.Find(x => x != null && x.id == shape.windowId);
                if (w == null || !w.Contains(combat.TimeInAction)) continue;
                var bone = string.IsNullOrEmpty(shape.bonePath) ? root : root.Find(shape.bonePath);
                if (bone == null) continue;
                Gizmos.matrix = bone.localToWorldMatrix * Matrix4x4.TRS(shape.center, Quaternion.Euler(shape.euler), Vector3.one);
                Gizmos.color = new Color(1, 0.3f, 0.2f, 0.8f); Gizmos.DrawWireCube(Vector3.zero, shape.halfExtents * 2);
            }
            Gizmos.matrix = original;
        }
    }
}
