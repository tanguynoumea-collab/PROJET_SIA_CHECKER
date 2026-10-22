using System.IO;
using System.Text;
using SiaCheck.Viewer.Services;
using SiaCheck.Viewer.ViewModels;

namespace SiaCheck.Viewer.Tests;

internal static class Verdicts
{
    public static string Json(string project, string date, params (string Key, string Verdict, string? Subject)[] points) =>
        System.Text.Json.JsonSerializer.Serialize(new AiVerdictFile
        {
            Project = project, AnalysisDate = date, ReviewDate = date, Model = "test",
            Points = points.ToDictionary(p => p.Key, p => new AiVerdict { Verdict = p.Verdict, Subject = p.Subject, Reason = $"raison {p.Key}" }),
        });

    public static void Write(string dir, string file, string json)
    {
        Directory.CreateDirectory(dir);
        File.WriteAllText(Path.Combine(dir, file), json);
    }
}

public class AiVerdictLoadingTests
{
    /// <summary>Le fichier de L'Orée commité dans docs/revue-ia, tel que produit dans Claude Code.</summary>
    private static string RepoReviewDir()
    {
        for (var d = new DirectoryInfo(AppContext.BaseDirectory); d is not null; d = d.Parent)
            if (Directory.Exists(Path.Combine(d.FullName, "docs", "revue-ia"))) return Path.Combine(d.FullName, "docs", "revue-ia");
        throw new DirectoryNotFoundException("docs/revue-ia introuvable");
    }

    [Fact]
    public void Loads_the_loree_review_written_in_claude_code()
    {
        using var tmp = new TempDir();
        var review = AiReviewFiles.FindLatest("L OREE", AiReviewFiles.SearchDirs(tmp.Path, AppContext.BaseDirectory));
        Assert.NotNull(review);
        Assert.Equal(155, review.Data.Points.Count);
        Assert.Equal(2, review.Data.Version);
        Assert.Equal("garder", (string?)review.Data.Subjects!["S2"]!["par_defaut"]);
        Assert.NotNull(review.ReportPath);
        var s1 = review.Get("A1|B03|N00||SEP")!;
        Assert.Equal(AiVerdictKind.TrueIssue, s1.Kind);
        Assert.Equal("S1", s1.Subject);
        Assert.Equal(AiVerdictKind.Aggregate, review.Get("R1|*|*||SP")!.Kind);
        Assert.Contains(review.Data.Points.Values, v => v.Kind == AiVerdictKind.FalsePositive);
        Assert.DoesNotContain(review.Data.Points.Values, v => v.Kind == AiVerdictKind.Unknown);
    }

    [Fact]
    public void Prefix_matches_hand_written_file_names()
    {
        Assert.Equal("L_OREE", AiReviewFiles.Prefix("L OREE"));
        Assert.Equal("Les_Tilleuls_2", AiReviewFiles.Prefix(" Les Tilleuls-2 "));
        Assert.True(File.Exists(Path.Combine(RepoReviewDir(), "L_OREE_2026-10-22.verdicts.json")));
    }

    [Fact]
    public void Latest_date_wins_then_app_folder()
    {
        using var app = new TempDir();
        using var repo = new TempDir();
        Verdicts.Write(app.Path, "P_2026-10-20.verdicts.json", Verdicts.Json("P", "2026-10-20", ("k", "vrai sujet", "S1")));
        Verdicts.Write(repo.Path, "P_2026-10-22.verdicts.json", Verdicts.Json("P", "2026-10-22", ("k", "faux positif", null)));
        Verdicts.Write(app.Path, "P_2026-10-22.verdicts.json", Verdicts.Json("P", "2026-10-22", ("k", "à confirmer", null)));
        var review = AiReviewFiles.FindLatest("P", [app.Path, repo.Path])!;
        Assert.Equal(AiVerdictKind.ToConfirm, review.Get("k")!.Kind);
    }

    [Fact]
    public void Other_projects_and_unreadable_files_are_skipped()
    {
        using var tmp = new TempDir();
        Verdicts.Write(tmp.Path, "P_2026-10-19.verdicts.json", Verdicts.Json("P", "2026-10-19", ("k", "vrai sujet", "S1")));
        Verdicts.Write(tmp.Path, "P_2026-10-21.verdicts.json", "{ pas du json");
        Verdicts.Write(tmp.Path, "P_X_2026-10-22.verdicts.json", Verdicts.Json("P X", "2026-10-22", ("k", "faux positif", null)));
        Verdicts.Write(tmp.Path, "P_2026-10-23.verdicts.json", Verdicts.Json("Autre", "2026-10-23", ("k", "faux positif", null)));
        var review = AiReviewFiles.FindLatest("P", [tmp.Path])!;
        Assert.EndsWith("P_2026-10-19.verdicts.json", review.VerdictsPath);
        Assert.Null(review.ReportPath);
    }

    [Fact]
    public void Saved_review_is_found_again_with_its_report()
    {
        using var tmp = new TempDir();
        AiReviewFiles.Save(tmp.Path, "L OREE", "2026-10-22", "# Revue\n", new AiVerdictFile
        {
            Project = "L OREE", ReviewDate = "2026-10-22",
            Points = new() { ["k"] = new AiVerdict { Verdict = "vrai sujet", Subject = "S1", Reason = "écart à 1 943 m²" } },
        });
        var review = AiReviewFiles.FindLatest("L OREE", [tmp.Path])!;
        Assert.Equal("écart à 1 943 m²", review.Get("k")!.Reason);
        Assert.Equal("# Revue\n", File.ReadAllText(review.ReportPath!));
        Assert.Contains("écart", File.ReadAllText(review.VerdictsPath));   // accents écrits tels quels
    }
}

public class ApiKeyStoreTests
{
    private const string Key = "sk-ant-api03-ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";

    [Fact]
    public void Key_round_trips_and_is_never_written_in_clear()
    {
        using var tmp = new TempDir();
        var store = new ApiKeyStore(Path.Combine(tmp.Path, "k.bin"));
        Assert.False(store.HasKey);
        store.Save($"  {Key}\n");
        Assert.Equal(Key, store.Load());
        var bytes = File.ReadAllBytes(store.Path);
        Assert.DoesNotContain("sk-ant", Encoding.UTF8.GetString(bytes));
        Assert.DoesNotContain("sk-ant", Encoding.Unicode.GetString(bytes));
        Assert.Equal(Key, new ApiKeyStore(store.Path).Load());
    }

    [Fact]
    public void Clear_removes_the_key()
    {
        using var tmp = new TempDir();
        var store = new ApiKeyStore(Path.Combine(tmp.Path, "k.bin"));
        store.Save(Key);
        store.Clear();
        Assert.False(store.HasKey);
        Assert.Null(store.Load());
    }

    [Fact]
    public void Tampered_file_reads_as_no_key()
    {
        using var tmp = new TempDir();
        var store = new ApiKeyStore(Path.Combine(tmp.Path, "k.bin"));
        File.WriteAllBytes(store.Path, [1, 2, 3, 4]);
        Assert.Null(store.Load());
    }

    [Theory]
    [InlineData("")]
    [InlineData("sk-ant abc")]
    public void Rejects_blank_or_spaced_key(string key)
    {
        using var tmp = new TempDir();
        Assert.Throws<ArgumentException>(() => new ApiKeyStore(Path.Combine(tmp.Path, "k.bin")).Save(key));
    }

    [Fact]
    public void Mask_shows_only_prefix_and_last_four()
    {
        Assert.Equal("sk-ant-…6789", ApiKeyStore.Mask(Key));
        Assert.DoesNotContain("ABCD", ApiKeyStore.Mask(Key));
    }

    [Fact]
    public void Default_key_file_lives_outside_the_repository()
    {
        var path = AppPaths.Default.ApiKeyFile;
        Assert.StartsWith(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), path);
    }
}

public class AiResponseTests
{
    private static readonly string[] Keys = ["R1|B|N00||SP", "R3|B|N00||SEP", "R1|*|*||SP"];

    [Fact]
    public void Parses_report_and_verdicts_and_fills_forgotten_points()
    {
        var text = """
            Voici la revue.
            <rapport>
            # Revue IA
            | a | b |
            </rapport>
            <verdicts>
            ```json
            {"R1|B|N00||SP": {"verdict_ia": "faux positif", "sujet": null, "raison": "SC 15 %, dans la plage."},
             "R3|B|N00||SEP": {"verdict_ia": "Vrai sujet", "sujet": " S1 ", "raison": "1 943 m² sur sous-sol."},
             "R9|X|Y||Z": {"verdict_ia": "vrai sujet", "sujet": "S2", "raison": "inventé"}}
            ```
            </verdicts>
            """;
        var o = AiReviewParser.Parse(text, Keys);
        Assert.StartsWith("# Revue IA", o.ReportMarkdown);
        Assert.Equal(AiVerdictKind.FalsePositive, o.Points["R1|B|N00||SP"].Kind);
        Assert.Equal("vrai sujet", o.Points["R3|B|N00||SEP"].Verdict);
        Assert.Equal("S1", o.Points["R3|B|N00||SEP"].Subject);
        Assert.Equal(["R1|*|*||SP"], o.MissingKeys);
        Assert.Equal(AiVerdictKind.ToConfirm, o.Points["R1|*|*||SP"].Kind);
        Assert.Equal(["R9|X|Y||Z"], o.UnknownKeys);
        Assert.Equal(3, o.Points.Count);
    }

    [Fact]
    public void Subjects_block_is_kept_and_optional()
    {
        const string head = """<rapport># R</rapport><verdicts>{"R1|B|N00||SP": {"verdict_ia": "faux positif", "raison": "r"}}</verdicts>""";
        Assert.Null(AiReviewParser.Parse(head, Keys).Subjects);                                   // réponse v1
        var o = AiReviewParser.Parse(head + """
            <sujets>
            ```json
            {"S2": {"titre": "Toitures", "base": ["toitures"], "par_defaut": "garder",
                    "decisions": [{"id": "toitures-E09-N04", "decision": "rejeter", "explication": "toiture-jardin"}]}}
            ```
            </sujets>
            """, Keys);
        Assert.Equal("rejeter", (string?)o.Subjects!["S2"]!["decisions"]![0]!["decision"]);
        Assert.Throws<AiReviewException>(() => AiReviewParser.Parse(head + "<sujets>[1, 2]</sujets>", Keys));
        Assert.Throws<AiReviewException>(() => AiReviewParser.Parse(head + "<sujets>{oups</sujets>", Keys));
    }

    [Fact]
    public void Saved_review_keeps_subjects()
    {
        using var tmp = new TempDir();
        var subjects = System.Text.Json.Nodes.JsonNode.Parse("""{"S1": {"titre": "Abords", "decisions": []}}""")!.AsObject();
        var saved = AiReviewFiles.Save(tmp.Path, "P", "2026-10-22", "# R\n", new AiVerdictFile
        {
            Project = "P", AnalysisDate = "2026-10-22", ReviewDate = "2026-10-22", Version = 2, Subjects = subjects,
            Points = new() { ["k"] = new AiVerdict { Verdict = "vrai sujet", Subject = "S1", Reason = "r" } },
        });
        var back = AiReviewFiles.Load(saved.VerdictsPath);
        Assert.Equal("Abords", (string?)back.Subjects!["S1"]!["titre"]);
        Assert.Contains("\"sujets\"", File.ReadAllText(saved.VerdictsPath));
    }

    [Fact]
    public void Missing_tags_or_bad_json_are_reported()
    {
        Assert.Throws<AiReviewException>(() => AiReviewParser.Parse("<verdicts>{}</verdicts>", Keys));
        Assert.Throws<AiReviewException>(() => AiReviewParser.Parse("<rapport>x</rapport>", Keys));
        Assert.Throws<AiReviewException>(() => AiReviewParser.Parse("<rapport>x</rapport><verdicts>{oups</verdicts>", Keys));
    }

    [Fact]
    public void Cost_estimate_brackets_the_loree_review()
    {
        // L'Orée : 155 points, ~14 500 jetons de texte en sortie (rapport, décisions, verdicts).
        var (min, max) = AiPricing.OutputTokens(155);
        Assert.InRange(14_500, min - 500, max);
        Assert.True(max <= AiPricing.MaxOutputTokens);
        Assert.Equal(0.24m + 0.20m, AiPricing.Cost(60_000, 10_000));
    }

    [Fact]
    public void Prompt_embeds_procedure_example_and_evidence()
    {
        var evidence = """{"project": "P", "issues": [{"key": "a"}, {"key": "b"}]}""";
        var p = AiReviewPrompt.Build("P", "2026-10-22", "2026-10-22", evidence);
        Assert.Equal(2, p.IssueCount);
        Assert.Contains("# Revue IA d'une analyse sia-check", p.System);   // SKILL.md
        Assert.Contains("L'Orée", p.System);                               // exemple de rapport
        Assert.Contains("<verdicts>", p.System);
        Assert.Contains("<sujets>", p.System);
        Assert.Contains(evidence, p.User);
    }
}

public class AiReviewViewModelTests
{
    private static MainViewModel Loaded(TempDir tmp, string verdictsJson)
    {
        var paths = new AppPaths(tmp.Path, tmp.Path);
        Verdicts.Write(paths.AiReviewDir(tmp.Path), "Synth_2026-10-22.verdicts.json", verdictsJson);
        File.WriteAllText(Path.Combine(paths.AiReviewDir(tmp.Path), "Synth_2026-10-22.md"), "# Revue de Synth\n");
        var vm = new MainViewModel(new FakeShell(), paths, new AppSettings(), enginePath: null) { AiSearchBaseDir = tmp.Path };
        vm.LoadDocument(tmp.Path, Fixture.Synth());
        vm.StatusFilter = "all";
        return vm;
    }

    [Fact]
    public void Verdicts_show_on_issues_and_filter_the_list()
    {
        using var tmp = new TempDir();
        var vm = Loaded(tmp, Verdicts.Json("Synth", "2026-10-22", ("R3|ERR|N00||SEP", "vrai sujet", "S1"), ("A1|ERR|N00||SEP", "faux positif", null)));
        Assert.True(vm.HasAiReview);
        Assert.Equal("IA 22.10 · 1 sujet", vm.AiSummary);
        var item = vm.Issues.Single(i => i.Key == "R3|ERR|N00||SEP");
        Assert.Equal("S1 · vrai sujet", item.AiTag);
        Assert.Equal("raison R3|ERR|N00||SEP", item.AiReason);
        vm.AiFilter = "true";
        Assert.Equal([item], vm.IssuesView.Cast<IssueItem>());
        vm.AiFilter = "none";
        Assert.DoesNotContain(vm.IssuesView.Cast<IssueItem>(), i => i.HasAi);
        vm.ShowAiReportCommand.Execute(null);
        Assert.True(vm.IsAiReportOpen);
        Assert.Equal("# Revue de Synth\n", vm.AiReportMarkdown);
    }

    [Fact]
    public void Applying_false_positives_keeps_manual_statuses()
    {
        using var tmp = new TempDir();
        var vm = Loaded(tmp, Verdicts.Json("Synth", "2026-10-22", ("R3|ERR|N00||SEP", "faux positif", null), ("A1|ERR|N00||SEP", "faux positif", null)));
        var seen = vm.Issues.Single(i => i.Key == "A1|ERR|N00||SEP");
        seen.Status = ReviewStatus.Seen;
        Assert.Equal(1, vm.AiFalsePositiveCount);
        vm.ApplyAiFalsePositivesCommand.Execute(null);
        var fp = vm.Issues.Single(i => i.Key == "R3|ERR|N00||SEP");
        Assert.Equal(ReviewStatus.FalsePositive, fp.Status);
        Assert.StartsWith("Revue IA : ", fp.Comment);
        Assert.Equal(ReviewStatus.Seen, seen.Status);
        Assert.Equal(0, vm.AiFalsePositiveCount);
        // Persisté dans le ReviewStore : survit à la réouverture.
        var store = ReviewStore.Open(new AppPaths(tmp.Path, tmp.Path).ReviewFile(tmp.Path), tmp.Path);
        Assert.Equal(ReviewStatus.FalsePositive, store.Get("R3|ERR|N00||SEP").Status);
        Assert.StartsWith("Revue IA : ", store.Get("R3|ERR|N00||SEP").Comment);
    }

    [Fact]
    public void No_review_means_no_ai_noise()
    {
        using var tmp = new TempDir();
        var vm = new MainViewModel(new FakeShell(), new AppPaths(tmp.Path, tmp.Path), new AppSettings(), enginePath: null) { AiSearchBaseDir = tmp.Path };
        vm.LoadDocument(tmp.Path, Fixture.Synth());
        Assert.False(vm.HasAiReview);
        Assert.DoesNotContain(vm.Issues, i => i.HasAi);
        Assert.False(vm.CanStartAiReview);
    }
}
