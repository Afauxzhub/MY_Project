using System;
using System.Collections.Generic;

namespace Afauxzhub.Project.Animation
{
    /// <summary>Seconds-based action clock, independent of blended Animator clips.</summary>
    public sealed class ActionClock
    {
        private struct Boundary
        {
            public double time;
            public int index;
            public int type; // exit, enter, cue (stable ordering at the same time)
        }
        private readonly List<Boundary> boundaries = new List<Boundary>();
        private readonly HashSet<int> active = new HashSet<int>();
        private int cursor;
        private int generation;
        private double duration;
        public double Time { get; private set; }
        public bool Finished { get; private set; } = true;
        public event Action<int, bool> WindowChanged;
        public event Action<int> Cue;
        public bool IsActive(int index) => active.Contains(index);

        public void Start(double length, IReadOnlyList<ActionWindow> windows, IReadOnlyList<float> cueTimes)
        {
            if (double.IsNaN(length) || double.IsInfinity(length) || length <= 0) throw new ArgumentOutOfRangeException(nameof(length));
            if (windows == null || cueTimes == null) throw new ArgumentNullException(windows == null ? nameof(windows) : nameof(cueTimes));
            int expectedGeneration = generation + 1;
            Stop();
            if (generation != expectedGeneration) return; // An exit callback already replaced this clock.
            duration = Math.Max(0.001, length);
            Time = 0;
            Finished = false;
            boundaries.Clear();
            cursor = 0;
            for (int i = 0; i < windows.Count; i++)
            {
                var w = windows[i];
                if (w == null || float.IsNaN(w.start) || float.IsNaN(w.end) || w.start < 0 || w.end <= w.start || w.end > duration + 0.00001) continue;
                boundaries.Add(new Boundary { time = w.start, index = i, type = 1 });
                boundaries.Add(new Boundary { time = Math.Min(duration, w.end), index = i, type = 0 });
            }
            for (int i = 0; i < cueTimes.Count; i++)
                if (cueTimes[i] >= 0 && cueTimes[i] < duration)
                    boundaries.Add(new Boundary { time = cueTimes[i], index = i, type = 2 });
            boundaries.Sort((a, b) => a.time != b.time ? a.time.CompareTo(b.time) : a.type != b.type ? a.type.CompareTo(b.type) : a.index.CompareTo(b.index));
            Advance(0);
        }

        public void Advance(double deltaTime)
        {
            if (Finished || deltaTime < 0 || double.IsNaN(deltaTime) || double.IsInfinity(deltaTime)) return;
            double target = Math.Min(duration, Time + deltaTime);
            int version = generation;
            while (cursor < boundaries.Count && boundaries[cursor].time <= target)
            {
                var b = boundaries[cursor++];
                Time = b.time;
                if (b.type == 2) Cue?.Invoke(b.index);
                else
                {
                    bool entered = b.type == 1;
                    if (entered) active.Add(b.index); else active.Remove(b.index);
                    WindowChanged?.Invoke(b.index, entered);
                }
                if (generation != version) return; // A callback interrupted or replaced the action.
            }
            Time = target;
            if (Time >= duration) { Finished = true; CloseWindows(); }
        }

        public void Stop()
        {
            generation++;
            Finished = true;
            CloseWindows();
        }

        private void CloseWindows()
        {
            if (active.Count == 0) return;
            var exiting = new List<int>(active);
            exiting.Sort();
            active.Clear();
            int version = generation;
            foreach (int i in exiting)
            {
                WindowChanged?.Invoke(i, false);
                if (generation != version) return; // Do not report stale indices against a newly started action.
            }
        }
    }
}
