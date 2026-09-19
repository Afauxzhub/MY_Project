using System;
using System.IO;
using System.Reflection;
using Afauxzhub.AnimationPipeline.Editor;
using UnityEditor;
using UnityEngine;

namespace Afauxzhub.Project.Editor
{
    public static class AnimationNamingValidation
    {
        [Serializable] private sealed class Case
        {
            public string name;
            public string character;
            public string set;
            public string action;
            public string folder;
        }
        [Serializable] private sealed class Fixture
        {
            public Case[] personal;
            public string[] invalid;
            public string[] legacy;
            public string[] cinematic;
        }

        [MenuItem("Tools/MY Project/Validate Animation Naming")]
        public static void Validate()
        {
            string root = Directory.GetParent(Directory.GetParent(Application.dataPath).FullName).FullName;
            var fixture = JsonUtility.FromJson<Fixture>(File.ReadAllText(Path.Combine(root, "tests/fixtures/animation-naming.json")));
            var settings = AnimationPipelineSettings.instance;
            if (!settings.MirrorPersonalAnimationFolders) throw new InvalidOperationException("Personal folder mirroring is disabled.");
            // Exercise the actual exporter path decision, not only the standalone naming helper.
            Type exporter = typeof(AnimationPipelineSettings).Assembly.GetType("Afauxzhub.AnimationPipeline.Editor.AnimationClipExporter", true);
            MethodInfo buildFolder = exporter.GetMethod("BuildOutputFolder", BindingFlags.Static | BindingFlags.NonPublic);
            foreach (Case item in fixture.personal)
            {
                if (!PersonalAnimationNaming.TryParse(item.name, out string character, out string set, out string action)
                    || character != item.character || set != item.set || action != item.action)
                    throw new InvalidOperationException("Personal name mismatch: " + item.name);
                string input = settings.SourceRoot + "/" + item.folder + "/" + item.name + ".fbx";
                string expectedFolder = settings.OutputRoot + "/" + item.folder;
                string actualFolder = (string)buildFolder.Invoke(null, new object[] { input, settings });
                if (actualFolder != expectedFolder || PersonalAnimationNaming.GetOutputPath(settings.SourceRoot, settings.OutputRoot, input)
                    != expectedFolder + "/" + item.name + ".anim")
                    throw new InvalidOperationException("Export/Max locate mismatch: " + input);
            }
            foreach (string name in fixture.invalid)
                if (PersonalAnimationNaming.TryParse(name, out _, out _, out _))
                    throw new InvalidOperationException("Invalid name accepted: " + name);
            foreach (string name in fixture.legacy)
            {
                string[] parts = name.Split('_');
                string actual = (string)buildFolder.Invoke(null, new object[] { settings.SourceRoot + "/Role/Role_Player/" + name + ".fbx", settings });
                if (actual != settings.OutputRoot + "/" + parts[0] + "_" + parts[1])
                    throw new InvalidOperationException("Legacy output changed: " + name);
            }
            foreach (string name in fixture.cinematic)
                if (PersonalAnimationNaming.TryParse(name, out _, out _, out _))
                    throw new InvalidOperationException("Cinematic name misclassified: " + name);
            try
            {
                PersonalAnimationNaming.GetOutputPath(settings.SourceRoot, settings.OutputRoot, settings.SourceRoot + "/../Player_Run.fbx");
                throw new InvalidOperationException("Path escape was accepted.");
            }
            catch (ArgumentException) { }
            AssetWorkflowValidation.Validate();
            Debug.Log("[MY_Project AnimationNaming] PASS: shared naming fixture, actual exporter routing, legacy fallback, and path safety. Real FBX acceptance remains separate.");
        }
    }
}
