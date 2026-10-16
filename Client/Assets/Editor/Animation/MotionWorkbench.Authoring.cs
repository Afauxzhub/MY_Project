using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Afauxzhub.Project.Animation;
using UnityEditor;
using UnityEngine;

namespace Afauxzhub.Project.Editor.Animation
{
    public sealed partial class MotionWorkbench
    {
        [SerializeField] private MotionMode previewFromMode = MotionMode.Free, previewToMode = MotionMode.Free;
        [SerializeField] private DefaultAsset scanFolder;
        [SerializeField] private string scanPrefix = "";
        [SerializeField] private WeaponStance scanStance;
        private bool allowOverwrite;
        private readonly List<MotionCandidate> candidates = new List<MotionCandidate>();
        [NonSerialized] private MotionCoverageReport coverageSnapshot;
        private int coveragePage;
        private bool coverageMissingOnly = true;
        private void DrawCoverageMatrix()
        {
            bool refresh = GUILayout.Button("刷新资源审核表（当前草稿快照）");
            if (coverageSnapshot?.rows == null || refresh) { coverageSnapshot = MotionAuthoringTools.Coverage(draft); coveragePage = 0; }
            coverageMissingOnly = EditorGUILayout.Toggle("仅未赋基础槽", coverageMissingOnly);
            var rows = coverageSnapshot.rows.Where(r => !coverageMissingOnly || !r.optional && string.IsNullOrEmpty(r.clip)).ToArray();
            int pages = Mathf.Max(1, Mathf.CeilToInt(rows.Length / 10f)); coveragePage = Mathf.Clamp(coveragePage, 0, pages - 1);
            using (new EditorGUILayout.HorizontalScope())
            {
                if (GUILayout.Button("上一页")) coveragePage = Mathf.Max(0, coveragePage - 1);
                GUILayout.Label($"{coveragePage + 1}/{pages} · {rows.Length} 项");
                if (GUILayout.Button("下一页")) coveragePage = Mathf.Min(pages - 1, coveragePage + 1);
            }
            foreach (var row in rows.Skip(coveragePage * 10).Take(10))
            {
                EditorGUILayout.LabelField(row.selector, EditorStyles.miniLabel);
                using (new EditorGUILayout.HorizontalScope())
                {
                    EditorGUILayout.LabelField((row.optional ? "可选 / " : "基础 / ") + row.status);
                    if (GUILayout.Button("定位", GUILayout.Width(50)))
                    {
                        int index = draft.entries.FindIndex(e => e != null && MotionCatalog.Selector(e) == row.selector);
                        if (index < 0) message = "该槽尚未写入旧库，请在动作库显式补齐新版本动作槽。";
                        else { selectedEntry = index; stance = draft.entries[index].stance; search = ""; tab = 0; }
                    }
                }
            }
        }
        private void DrawTrim(string label, MotionEntry entry)
        {
            float min = entry.inPoint, max = entry.outPoint;
            EditorGUILayout.MinMaxSlider(new GUIContent(label), ref min, ref max, 0, 1);
            if (min != entry.inPoint || max != entry.outPoint)
            {
                Undo.RecordObject(draft, "Trim motion reference");
                entry.inPoint = Mathf.Clamp(min, 0, 0.999f); entry.outPoint = Mathf.Max(entry.inPoint + 0.001f, max);
            }
            EditorGUILayout.LabelField($"{entry.clip.name}: {entry.inPoint * entry.clip.length:F3}s — {entry.outPoint * entry.clip.length:F3}s（仅引用区间，原动画不改）", EditorStyles.miniLabel);
        }
        private void DrawEntryReview(MotionEntry entry)
        {
            EditorGUILayout.HelpBox(MotionAuthoringTools.Status(draft, entry), MessageType.None);
            using (new EditorGUILayout.HorizontalScope())
            {
                using (new EditorGUI.DisabledScope(entry.clip == null))
                    if (GUILayout.Button("标为已人工审核"))
                    {
                        var audit = MotionAuthoringTools.Audit(draft.model, entry.clip);
                        if (!audit.Compatible) message = audit.ToString();
                        else { Undo.RecordObject(draft, "Review animation binding"); entry.review = MotionReview.Approved; entry.reviewedFingerprint = MotionAuthoringTools.Fingerprint(draft.model, entry.clip); message = "记录人工审核；重新发布或更换模型后会提示复核。"; }
                    }
                if (GUILayout.Button("标为临时替代")) { Undo.RecordObject(draft, "Mark placeholder"); entry.review = MotionReview.Placeholder; entry.reviewedFingerprint = ""; }
                if (GUILayout.Button("待审核")) { Undo.RecordObject(draft, "Reset review"); entry.review = MotionReview.Pending; entry.reviewedFingerprint = ""; }
            }
        }
        private void DrawBatch()
        {
            EditorGUILayout.HelpBox("仅扫描候选，不自动写槽。按文件夹 + 动作套分批；名称需等于槽建议名（可去掉前缀），也可在槽的 Match Name 指定精确名称。重名必须手选。", MessageType.Info);
            scanFolder = (DefaultAsset)EditorGUILayout.ObjectField("动画文件夹", scanFolder, typeof(DefaultAsset), false);
            scanStance = (WeaponStance)EditorGUILayout.EnumPopup("本批动作套", scanStance);
            scanPrefix = EditorGUILayout.TextField("去掉文件名前缀", scanPrefix);
            if (GUILayout.Button("扫描候选（不修改草稿）"))
            {
                try { candidates.Clear(); candidates.AddRange(MotionAuthoringTools.Propose(draft, MotionAuthoringTools.Scan(AssetDatabase.GetAssetPath(scanFolder)), scanStance, scanPrefix)); message = "找到 " + candidates.Count + " 个候选槽；逐项勾选后确认。"; }
                catch (Exception e) { message = e.Message; }
            }
            allowOverwrite = EditorGUILayout.Toggle("允许替换已有引用", allowOverwrite);
            foreach (var row in candidates)
            {
                using (new EditorGUILayout.VerticalScope(EditorStyles.helpBox))
                {
                    row.apply = EditorGUILayout.ToggleLeft(MotionCatalog.Selector(row.entry), row.apply);
                    int next = EditorGUILayout.Popup("候选", row.selected + 1, new[] { "未选择 / 重名待确认" }.Concat(row.choices.Select(c => c.name + " | " + AssetDatabase.GetAssetPath(c))).ToArray());
                    row.selected = next - 1;
                    EditorGUILayout.LabelField("原引用", row.entry.clip == null ? "空" : row.entry.clip.name);
                    if (row.Clip != null && GUILayout.Button("检查此候选绑定")) message = MotionAuthoringTools.Audit(draft.model, row.Clip).ToString();
                }
            }
            if (GUILayout.Button("确认勾选项 → 写入草稿"))
            {
                try { message = "已填 " + MotionAuthoringTools.Apply(draft, candidates, allowOverwrite) + " 项；仍待人工预览审核，尚未保存源库。"; candidates.Clear(); }
                catch (Exception e) { message = e.Message; }
            }
        }
        private void DrawCoverageExport()
        {
            if (GUILayout.Button("导出当前草稿资源需求（JSON + TXT）"))
            {
                string path = EditorUtility.SaveFilePanel("Export motion requirements", "", source.name + "-requirements", "json");
                if (string.IsNullOrEmpty(path)) return;
                // Export is intentionally outside imported Assets; reports can contain local reference paths.
                string assets = Path.GetFullPath(Application.dataPath).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
                if (Path.GetFullPath(path).StartsWith(assets, StringComparison.OrdinalIgnoreCase)) { message = "请导出到 Assets 外的本地报告目录。"; return; }
                var report = MotionAuthoringTools.Coverage(draft);
                File.WriteAllText(path, JsonUtility.ToJson(report, true)); File.WriteAllText(Path.ChangeExtension(path, ".txt"), MotionAuthoringTools.CoverageText(report));
                message = "已导出 " + report.rows.Length + " 条需求（基础 / 可选分开）；没有写源库。";
            }
        }
        private void DrawHelp()
        {
            EditorGUILayout.HelpBox("1. 首次 / 换角色：New Character Lab (No Wires)，选择模型、可选配置模板及新目录。每个角色有独立库和移动参数。默认不复制旧角色动画。", MessageType.Info);
            if (GUILayout.Button("新建独立角色测试配置")) MotionCharacterWizard.Open();
            EditorGUILayout.HelpBox("2. 新动画：先按资产工作流发布到项目；不要编辑 Generated 源曲线。在动作库选 Sheathed（放松）或 Drawn（战斗），给 Clip 拖引用；也可批量扫描候选。Mode=Any 共享，自由/靶向需要区别时新增 Free / Targeting 变体。", MessageType.Info);
            EditorGUILayout.HelpBox("3. 衔接：选择上一/下一动画，默认显示实际命中的配方。先复制继承模板为角色覆盖，再拖黄色融合线或编辑 Weight 曲线。可拖裁剪入出点、逐帧查看；Bridge 是可选过渡动作。", MessageType.Info);
            EditorGUILayout.HelpBox("4. 运动参数控制速度/加减速/角速度；Stage Seconds 覆盖阶段时长，0 继承。Reference Speed 配合 Match Playback 调步频。Contact Authored + 左右脚曲线用于停步脚选择，曲线横轴是原 Clip 归一化时间，不是 IK 锁脚。", MessageType.Info);
            EditorGUILayout.HelpBox("5. 保存差异才写资产；应用到 Play 只改本次运行副本。先退出其他测试场景，再打开新场景 Play。WASD 移动 / Ctrl 走 / Shift 冲刺 / F2 测试切套 / Tab 靶向 / Q E 原地转向 / C 跳；V 请求收放动作（需资源）。缺动画时诊断会显示回退，不能视为美术验收。", MessageType.Info);
            EditorGUILayout.HelpBox("6. 完成预览与真实测试后标记人工审核；重新发布同路径动画会要求复核。运行 / 覆盖可导出需求。Root Motion、动态锁脚和脚滑修正仍是后续验收，不在本轮程序位移闭环中。", MessageType.Warning);
        }
    }
}
