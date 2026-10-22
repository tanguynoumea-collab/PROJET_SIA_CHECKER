using System.IO;
using System.Text.Json;
using System.Text.Json.Nodes;
using SiaCheck.Viewer.Models;
using SiaCheck.Viewer.Services;
using SiaCheck.Viewer.ViewModels;

namespace SiaCheck.Viewer.Tests;

/// <summary>Document synthétique augmenté de sujets, comme le produit <c>sia-check --viewer-json</c> en V2.</summary>
internal static class SubjectFixture
{
    public const string Abords = """
        {"id": "S1", "titre": "Abords", "cause": "abords", "action": "corriger", "origine": "ia", "certitude": "vrai sujet",
         "explication": "Dalle sur sous-sol.", "points": ["A1|ERR|N00||SEP", "R3|ERR|N00||SEP"], "m2": 45,
         "corrections": [
           {"id": "abords-ERR-N00", "op": "découper", "cible": {"ids": ["err-n00-sep"]}, "vers": "SA", "aire": 45.0,
            "explication": "45 m² au contact du terrain.", "sujet": "S1", "origine": "ia", "statut": "proposée", "m2": 45.0,
            "polygone": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1]]]},
            "trace": {"z": 0.0, "v": [0, 0, 1, 0, 1, 1], "i": [0, 1, 2]}},
           {"id": "abords-OK-N01", "op": "exclure", "cible": {"ids": ["ok-n01-sep"]}, "explication": "SEP entière.",
            "sujet": "S1", "origine": "règle", "statut": "proposée", "m2": 20.0}]}
        """;

    public const string Sc = """
        {"id": "sc-implicite", "titre": "Surface de construction implicite", "cause": "sc", "action": "aucune",
         "explication": "", "points": ["R1|ERR|N00||SP"], "m2": 0, "corrections": []}
        """;

    public static ViewerDocument Doc(string? log = null, string? before = null)
    {
        var root = JsonNode.Parse(File.ReadAllText(Fixture.File("synth.viewer.json")))!.AsObject();
        root["subjects"] = new JsonArray(JsonNode.Parse(Abords), JsonNode.Parse(Sc));
        if (log is not null) root["corrections_log"] = JsonNode.Parse(log);
        if (before is not null)
            foreach (var lv in root["levels"]!.AsArray())
                if ((string?)lv!["building"] == "ERR" && (string?)lv["level"] == "N00") lv["before"] = JsonNode.Parse(before);
        return JsonSerializer.Deserialize<ViewerDocument>(root.ToJsonString())!;
    }

    public static MainViewModel Loaded(TempDir tmp, ViewerDocument? doc = null)
    {
        var vm = new MainViewModel(new FakeShell(), new AppPaths(tmp.Path, tmp.Path), new AppSettings(), enginePath: null)
        {
            AiSearchBaseDir = tmp.Path,
        };
        vm.LoadDocument(tmp.Path, doc ?? Doc());
        return vm;
    }
}

public class CorrectionJournalTests
{
    private static Correction Proposal(string id = "c1", string status = Correction.Proposed) =>
        JsonSerializer.Deserialize<Correction>($$$"""
            {"id": "{{{id}}}", "op": "exclure", "cible": {"ids": ["s1"]}, "statut": "{{{status}}}", "origine": "règle",
             "explication": "x", "polygone": {"type": "Polygon"}}
            """)!;

    [Fact]
    public void Decision_overlays_proposal_and_round_trips_unknown_fields()
    {
        using var tmp = new TempDir();
        var path = Path.Combine(tmp.Path, "j.json");
        var j = CorrectionJournal.Open(path, "P");
        var c = Proposal();
        c.Status = Correction.Accepted;
        j.Decide(c);
        var again = CorrectionJournal.Open(path, "P");
        Assert.Equal(Correction.Accepted, again.Overlay(Proposal()).Status);
        Assert.Contains("polygone", File.ReadAllText(path));                     // champ inconnu de l'app conservé
        using var doc = JsonDocument.Parse(File.ReadAllText(path));               // format lu par sia-check --corrections
        Assert.Equal("acceptée", doc.RootElement.GetProperty("corrections")[0].GetProperty("statut").GetString());
    }

    [Fact]
    public void Back_to_proposed_removes_the_decision_and_manual_edits_win()
    {
        using var tmp = new TempDir();
        var j = CorrectionJournal.Open(Path.Combine(tmp.Path, "j.json"), "P");
        var c = Proposal();
        c.Status = Correction.Accepted;
        j.Decide(c);
        c.Status = Correction.Proposed;
        j.Decide(c);
        Assert.False(j.HasDecisions);
        var m = Proposal();
        m.Origin = "manuel";
        m.Area = 12.5;
        j.Decide(m);
        Assert.Equal(12.5, j.Overlay(Proposal()).Area);                           // la proposition ne l'écrase pas
    }

    [Fact]
    public void Pending_counts_changes_since_last_analysis()
    {
        using var tmp = new TempDir();
        var j = CorrectionJournal.Open(Path.Combine(tmp.Path, "j.json"), "P");
        j.Decide(Proposal("a", Correction.Accepted));
        j.Decide(Proposal("b", Correction.Accepted));
        j.Decide(Proposal("r", Correction.Rejected));                             // un rejet ne change pas le moteur
        Assert.Equal(2, j.PendingCount);
        j.MarkAnalysed();
        Assert.Equal(0, CorrectionJournal.Open(Path.Combine(tmp.Path, "j.json"), "P").PendingCount);
        j.Decide(Proposal("a", Correction.Proposed));                             // retirée : à « désappliquer »
        Assert.Equal(1, j.PendingCount);
    }

    [Fact]
    public void Orphans_are_decisions_without_proposal()
    {
        using var tmp = new TempDir();
        var j = CorrectionJournal.Open(Path.Combine(tmp.Path, "j.json"), "P");
        j.Decide(Proposal("gone", Correction.Accepted));
        Assert.Equal(["gone"], j.Orphans(["other"]).Select(c => c.Id));
    }
}

public class SubjectsViewModelTests
{
    [Fact]
    public void Subjects_tab_opens_by_default_sorted_with_links_to_points()
    {
        using var tmp = new TempDir();
        var vm = SubjectFixture.Loaded(tmp);
        Assert.True(vm.ShowSubjects);
        Assert.Equal(["S1", "sc-implicite"], vm.Subjects.Select(s => s.Id));    // « corriger » avant « aucune »
        var s1 = vm.Subjects[0];
        Assert.Equal("S1", s1.ShortId);
        Assert.Equal("", vm.Subjects[1].ShortId);                                // sujet du moteur : lu par son titre
        Assert.Contains("err-n00-sep", s1.SurfaceIds);
        var point = vm.Issues.First(i => i.Key == "A1|ERR|N00||SEP");
        Assert.Equal("S1", point.SubjectId);
        vm.ShowPointsTabCommand.Execute(null);
        vm.ShowSubjectOfCommand.Execute(point);
        Assert.True(vm.ShowSubjects);
        Assert.Same(s1, vm.SelectedSubject);
    }

    [Fact]
    public void Accept_all_persists_and_counts_on_analyse_button()
    {
        using var tmp = new TempDir();
        var vm = SubjectFixture.Loaded(tmp);
        vm.SelectedSubject = vm.Subjects[0];
        vm.AcceptAllCorrectionsCommand.Execute(null);
        Assert.Equal(2, vm.SelectedSubject.AcceptedCount);
        Assert.Equal("Analyser · 2", vm.AnalyseLabel);
        // Rouverture : décisions reprises du journal.
        var again = SubjectFixture.Loaded(tmp);
        Assert.All(again.Subjects[0].Corrections, c => Assert.Equal(CorrectionDecision.Accepted, c.Decision));
        Assert.Equal(CorrectionState.Accepted, again.Subjects[0].Corrections[0].State);
    }

    [Fact]
    public void Keys_set_one_correction_and_reject_strikes_it_out()
    {
        using var tmp = new TempDir();
        var vm = SubjectFixture.Loaded(tmp);
        vm.SelectedSubject = vm.Subjects[0];
        vm.SelectedCorrection = vm.SelectedSubject.Corrections[1];
        vm.SetCorrectionDecisionCommand.Execute("rejected");
        Assert.True(vm.SelectedCorrection!.IsRejected);
        Assert.Equal(45.0, vm.SelectedSubject.M2);                               // le rejet sort de la surface en jeu
        Assert.Equal("Analyser", vm.AnalyseLabel);                               // un rejet seul n'appelle pas d'analyse
    }

    [Fact]
    public void Edit_validates_area_then_becomes_manual_and_drops_the_trace()
    {
        using var tmp = new TempDir();
        var vm = SubjectFixture.Loaded(tmp);
        vm.SelectedSubject = vm.Subjects[0];
        var c = vm.SelectedCorrection = vm.SelectedSubject.Corrections[0];
        vm.EditCorrectionCommand.Execute(null);
        c.EditArea = "60";                                                       // > 50 m² de la SEP visée
        vm.CommitCorrectionEditCommand.Execute(null);
        Assert.True(c.IsEditing);
        Assert.True(c.HasEditError);
        c.EditArea = "40,5";
        vm.CommitCorrectionEditCommand.Execute(null);
        Assert.False(c.IsEditing);
        Assert.Equal(40.5, c.Model.Area);
        Assert.Equal("manuel", c.Model.Origin);
        Assert.True(c.Model.NeedsRetrace);
        Assert.False(c.HasTrace);
        Assert.Equal(40.5, SubjectFixture.Loaded(tmp).Subjects[0].Corrections[0].Model.Area);   // gardée au journal
    }

    [Fact]
    public void Applied_and_failed_corrections_come_from_the_engine_log()
    {
        using var tmp = new TempDir();
        var log = """
            [{"id": "abords-ERR-N00", "statut": "acceptée", "application": "appliquée", "surfaces": 1, "m2": 45, "raison": ""},
             {"id": "abords-OK-N01", "statut": "acceptée", "application": "cible introuvable", "surfaces": 0, "m2": 0, "raison": ""}]
            """;
        var j = CorrectionJournal.Open(new AppPaths(tmp.Path, tmp.Path).CorrectionsFile(tmp.Path), "Synth");
        foreach (var s in SubjectFixture.Doc().Subjects[0].Corrections) { s.Status = Correction.Accepted; j.Decide(s); }
        var vm = SubjectFixture.Loaded(tmp, SubjectFixture.Doc(log));
        var cs = vm.Subjects[0].Corrections;
        Assert.Equal(CorrectionState.Applied, cs[0].State);
        Assert.Equal(CorrectionState.Failed, cs[1].State);
        Assert.Equal(1, vm.AppliedCorrections);
        Assert.Equal("1 correction appliquée", vm.AppliedText);
    }

    [Fact]
    public void Balance_row_shows_the_residual_before_corrections()
    {
        using var tmp = new TempDir();
        var before = """{"values": {"SP": 100, "SEP": 50}, "r1": {"diff": 35, "verdict": "ERREUR"}, "r3": {"diff": 120, "verdict": "ERREUR"}}""";
        var vm = SubjectFixture.Loaded(tmp, SubjectFixture.Doc(before: before));
        vm.BalanceBuilding = "ERR";
        var row = vm.BalanceRows.First(r => r.Level == "N00");
        Assert.True(row.HasChange);
        Assert.Equal("120,00", row.ChangeBefore);
        Assert.Equal(50, row.SepBefore);
    }

    [Fact]
    public void Old_documents_without_subjects_keep_the_points_tab()
    {
        using var tmp = new TempDir();
        var vm = new MainViewModel(new FakeShell(), new AppPaths(tmp.Path, tmp.Path), new AppSettings(), enginePath: null) { AiSearchBaseDir = tmp.Path };
        vm.LoadDocument(tmp.Path, Fixture.Synth());
        Assert.False(vm.HasSubjects);
        Assert.False(vm.ShowSubjects);
        Assert.Equal("Analyser", vm.AnalyseLabel);
    }
}
