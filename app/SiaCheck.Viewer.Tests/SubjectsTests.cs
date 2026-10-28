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

public class ModifiedAfterDoneTests
{
    [Fact]
    public async Task A_decision_on_a_done_project_asks_for_republication_later()
    {
        using var tmp = new TempDir();
        var shell = new FakeShell { ConfirmAnswer = false };
        var vm = new MainViewModel(shell, new AppPaths(tmp.Path, tmp.Path), new AppSettings(), enginePath: null) { AiSearchBaseDir = tmp.Path };
        vm.LoadDocument(tmp.Path, SubjectFixture.Doc());
        var registry = new ProjectRegistry(new AppPaths(tmp.Path, tmp.Path).ProjectsFile);
        registry.SetStatus(tmp.Path, ProjectStatus.Done);
        vm.LoadDocument(tmp.Path, SubjectFixture.Doc());
        Assert.True(vm.IsProjectDone);

        vm.Subjects.Single(s => s.Id == "S1").Corrections[0].Decision = CorrectionDecision.Accepted;   // une modification
        Assert.True(vm.IsProjectModified);
        Assert.Equal(("Traité · modifié", ProjectStatus.DoneModified), (vm.ProjectStatusLabel, registry.StatusOf(tmp.Path)));

        await vm.ToggleProjectStatusCommand.ExecuteAsync(null);                  // « Plus tard » : rien n'est republié
        Assert.True(vm.IsProjectModified);
        vm.Subjects.Single(s => s.Id == "S1").Corrections[1].Decision = CorrectionDecision.Rejected;   // on continue
        Assert.Equal(ProjectStatus.DoneModified, registry.StatusOf(tmp.Path));
    }

    [Fact]
    public void An_in_progress_project_stays_in_progress_when_modified()
    {
        using var tmp = new TempDir();
        var vm = SubjectFixture.Loaded(tmp);
        vm.Subjects.Single(s => s.Id == "S1").Corrections[0].Decision = CorrectionDecision.Accepted;
        Assert.False(vm.IsProjectModified);
        Assert.Equal("En traitement", vm.ProjectStatusLabel);
    }
}

public class SubjectListTests
{
    private static ViewerDocument With(params string[] extra)
    {
        var root = JsonNode.Parse(JsonSerializer.Serialize(SubjectFixture.Doc()))!.AsObject();
        foreach (var s in extra) root["subjects"]!.AsArray().Add(JsonNode.Parse(s));
        return JsonSerializer.Deserialize<ViewerDocument>(root.ToJsonString())!;
    }

    [Fact]
    public void Empty_subjects_are_hidden_and_mdp_proposals_come_last()
    {
        using var tmp = new TempDir();
        var vm = SubjectFixture.Loaded(tmp, With(
            """{"id": "R3-SEP", "titre": "SEP non classée", "action": "à vérifier", "points": ["X|nulle|part||SEP"], "corrections": []}""",
            """{"id": "affectation", "titre": "Affectation (tableau MDP)", "action": "proposer", "points": [], "corrections": [{"id": "aff-1", "op": "renseigner", "cible": {"lot": "A"}, "statut": "proposée", "origine": "règle", "explication": "x"}]}"""));
        Assert.DoesNotContain(vm.Subjects, s => s.Id == "R3-SEP");                 // aucun point ouvert, aucune correction
        var mdp = vm.Subjects.Last();
        Assert.Equal(("affectation", "Tableau MDP", "MDP"), (mdp.Id, mdp.Group, mdp.OriginLabel));
        Assert.Equal("", vm.Subjects.First().Group);
    }

    [Fact]
    public void Subject_card_lists_its_open_points_and_opens_one()
    {
        using var tmp = new TempDir();
        var vm = SubjectFixture.Loaded(tmp);
        vm.SelectedSubject = vm.Subjects.Single(s => s.Id == "S1");
        Assert.True(vm.HasSelectedSubjectPoints);
        Assert.All(vm.SelectedSubjectPoints, p => Assert.Contains(p.Key, new[] { "A1|ERR|N00||SEP", "R3|ERR|N00||SEP" }));
        vm.OpenSubjectPointCommand.Execute(vm.SelectedSubjectPoints[0]);
        Assert.False(vm.ShowSubjects);                                           // onglet Points
        Assert.Same(vm.SelectedSubjectPoints[0], vm.SelectedIssue);
    }
}

public class CorrectionDestinationTests
{
    [Fact]
    public void Destination_reclassifies_the_part_and_survives_reload()
    {
        using var tmp = new TempDir();
        var vm = SubjectFixture.Loaded(tmp);
        var c = vm.Subjects.Single(s => s.Id == "S1").Corrections.Single(x => x.Id == "abords-ERR-N00");
        Assert.Contains(c.Destinations, d => d.Value == "SEU");                 // part de SEP : catégories externes
        c.Destination = "SEU";
        Assert.Equal(("découper", "SEU", "manuel"), (c.Model.Op, c.Model.To, c.Model.Origin));
        c.Destination = CorrectionItem.ExcludeChoice;
        Assert.Equal(("exclure", (string?)null), (c.Model.Op, c.Model.To));
        Assert.Equal(45.0, c.Model.Area);                                       // exclusion de la même part

        var again = SubjectFixture.Loaded(tmp).Subjects.Single(s => s.Id == "S1").Corrections.Single(x => x.Id == "abords-ERR-N00");
        Assert.Equal(CorrectionItem.ExcludeChoice, again.Destination);
        var whole = SubjectFixture.Loaded(tmp).Subjects.Single(s => s.Id == "S1").Corrections.Single(x => x.Id == "abords-OK-N01");
        Assert.False(whole.HasDestinations);                                    // SEP entière : pas de part à classer
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

public class SubjectPointsTests
{
    [Fact]
    public void Settled_subject_marks_its_points_seen_and_undoing_restores_them()
    {
        using var tmp = new TempDir();
        var vm = SubjectFixture.Loaded(tmp);
        var s1 = vm.Subjects.First(s => s.Id == "S1");
        var points = vm.Issues.Where(i => s1.Subject.Points.Contains(i.Key)).ToList();
        Assert.NotEmpty(points);
        vm.SelectedSubject = s1;
        vm.AcceptAllCorrectionsCommand.Execute(null);
        Assert.All(points, i => Assert.Equal(ReviewStatus.Seen, i.Status));
        Assert.All(points, i => Assert.StartsWith("Sujet réglé", i.Comment));
        Assert.Equal(0, s1.OpenPoints);

        vm.SelectedCorrection = s1.Corrections[0];
        vm.SetCorrectionDecisionCommand.Execute("proposed");                 // plus réglé : retour « À traiter »
        Assert.All(points, i => Assert.Equal(ReviewStatus.ToReview, i.Status));
        Assert.Equal(points.Count, s1.OpenPoints);
    }

    [Fact]
    public void Subject_without_corrections_can_mark_its_points()
    {
        using var tmp = new TempDir();
        var vm = SubjectFixture.Loaded(tmp);
        var sc = vm.Subjects.First(s => s.Id == "sc-implicite");
        Assert.False(sc.HasCorrections);
        Assert.Equal(1, sc.OpenPoints);
        vm.SelectedSubject = sc;
        vm.MarkSubjectPointsFalseCommand.Execute(null);
        Assert.Equal(ReviewStatus.FalsePositive, vm.Issues.First(i => i.Key == "R1|ERR|N00||SP").Status);
        Assert.Equal("1 faux positif", sc.PointsState);
    }

    /// <summary>Dossier Treegram minimal : un .tgm (et, au choix, un cache VWR).</summary>
    private static string TreegramFolder(TempDir tmp, string name, bool vwr = true)
    {
        var dir = Path.Combine(tmp.Path, name);
        Directory.CreateDirectory(dir);
        File.WriteAllText(Path.Combine(dir, $"{name}.tgm"), "");
        if (vwr) Directory.CreateDirectory(Path.Combine(dir, "VWR"));
        return dir;
    }

    [Fact]
    public async Task Mdp_identity_comes_from_the_sheet_without_asking()
    {
        using var tmp = new TempDir();
        var dir = TreegramFolder(tmp, "L OREE");
        var shell = new FakeShell();
        var settings = new AppSettings();
        settings.SetMdpProject(dir, new MdpProject { Id = "1778", Name = "L'Orée", Canton = "VD" });
        var vm = new MainViewModel(shell, new AppPaths(tmp.Path, tmp.Path), settings, enginePath: null);
        var hrs = await vm.AskMdpProjectAsync(dir + "/", "L OREE", IdentityMode.Export);
        Assert.Equal(("1778", "L'Orée", "VD"), (hrs!.Id, hrs.Name, hrs.Canton));
        Assert.Equal(0, shell.SheetCount);                                    // fiche connue : rien n'est redemandé
    }

    [Fact]
    public async Task Missing_id_opens_the_sheet_and_is_remembered()
    {
        using var tmp = new TempDir();
        var dir = TreegramFolder(tmp, "L OREE");
        var shell = new FakeShell { SheetAnswer = s => s with { Identity = new MdpProject { Id = "1778", Name = "L'Orée" } } };
        var settings = new AppSettings();
        var vm = new MainViewModel(shell, new AppPaths(tmp.Path, tmp.Path), settings, enginePath: null);
        Assert.Equal("1778", (await vm.AskMdpProjectAsync(dir, "L OREE", IdentityMode.Export))!.Id);
        Assert.Equal(("L OREE", 1), (shell.SheetShown!.Identity.Name, shell.SheetCount));   // nom proposé : le dossier
        Assert.Equal("1778", settings.FindMdpProject(dir)!.Id);
        shell.SheetAnswer = _ => null;
        settings.SetMdpProject(dir, new MdpProject { Name = "x" });
        Assert.Null(await vm.AskMdpProjectAsync(dir, "L OREE", IdentityMode.Export));       // fiche annulée : pas d'export
    }

    [Fact]
    public async Task Adding_to_the_base_needs_the_full_identity()
    {
        using var tmp = new TempDir();
        var dir = TreegramFolder(tmp, "L OREE");
        var shell = new FakeShell { SheetAnswer = s => s with { Identity = new MdpProject { Id = "1778", Name = "L'Orée", Canton = "VD" } } };
        var vm = new MainViewModel(shell, new AppPaths(tmp.Path, tmp.Path), new AppSettings(), enginePath: null);
        Assert.Null(await vm.AskMdpProjectAsync(dir, "L OREE", IdentityMode.Base));     // ni typologie ni intervention
        Assert.Contains(shell.Notes, n => n.Contains("typologie") && n.Contains("type d'intervention"));
        shell.SheetAnswer = s => s with { Identity = new MdpProject { Id = "1778", Name = "L'Orée", Canton = "VD", Typologie = "Santé",
                                                                      Intervention = "Nouvelle construction" } };
        Assert.NotNull(await vm.AskMdpProjectAsync(dir, "L OREE", IdentityMode.Base));
    }

    [Fact]
    public void Project_folder_is_checked()
    {
        using var tmp = new TempDir();
        Assert.False(ProjectFolder.Check("").FolderOk);
        Assert.Contains("introuvable", ProjectFolder.Check(Path.Combine(tmp.Path, "absent")).FolderMessage);
        Directory.CreateDirectory(Path.Combine(tmp.Path, "vide"));
        Assert.Contains("Aucun fichier .tgm", ProjectFolder.Check(Path.Combine(tmp.Path, "vide")).FolderMessage);
        var sans = TreegramFolder(tmp, "SANS", vwr: false);
        Assert.True(ProjectFolder.Check(sans) is { FolderOk: true, FolderWarning: true });       // sans VWR : sans 3D
        File.WriteAllText(Path.Combine(sans, "b.tgm"), "");
        Assert.Contains("2 fichiers .tgm", ProjectFolder.Check(sans).FolderMessage);
        Assert.True(ProjectFolder.Check(TreegramFolder(tmp, "OK")) is { FolderOk: true, FolderWarning: false });
        // projet généré depuis un IFC (V4) : sa géométrie est dans le fichier, pas de VWR attendu
        var gen = Directory.CreateDirectory(Path.Combine(tmp.Path, "GEN")).FullName;
        File.WriteAllText(Path.Combine(gen, "L OREE.siagen.json"), "{}");
        Assert.True(ProjectFolder.Check(gen) is { FolderOk: true, FolderWarning: false });
        Assert.Equal("L OREE", ProjectFolder.ProjectName(ProjectFolder.Sources(gen).Single()));
        File.WriteAllText(Path.Combine(gen, "L OREE.tgm"), "");
        Assert.Contains("2 fichiers .tgm", ProjectFolder.Check(gen).FolderMessage);
    }

    [Fact]
    public void Sheet_refuses_a_folder_taken_and_warns_on_a_shared_id()
    {
        using var tmp = new TempDir();
        var (a, b) = (TreegramFolder(tmp, "A"), TreegramFolder(tmp, "B"));
        var settings = new AppSettings();
        settings.Touch(a, "A", DateTime.Now, 0);
        settings.SetMdpProject(a, new MdpProject { Id = "1778", Name = "L'Orée" });
        var vm = new MainViewModel(new FakeShell(), new AppPaths(tmp.Path, tmp.Path), settings, enginePath: null);
        Assert.Contains("déjà celui de « L'Orée »", vm.CheckSheet(new ProjectSheet(a, new MdpProject()), null).FolderMessage);
        Assert.True(vm.CheckSheet(new ProjectSheet(a, new MdpProject()), a).CanSave);           // son propre dossier
        var twin = vm.CheckSheet(new ProjectSheet(b, new MdpProject { Id = "1778" }), null);
        Assert.True(twin.CanSave);
        Assert.Contains("L'ID 1778 est aussi celui de « L'Orée »", twin.IdWarning);
    }

    [Fact]
    public async Task Changing_the_folder_moves_the_project_data()
    {
        using var tmp = new TempDir();
        var (old, nouveau) = (TreegramFolder(tmp, "LIVRAISON 1"), TreegramFolder(tmp, "LIVRAISON 2"));
        var paths = new AppPaths(Path.Combine(tmp.Path, "roaming"), Path.Combine(tmp.Path, "local"));
        var settings = new AppSettings();
        settings.Touch(old, "LIVRAISON 1", DateTime.Now, 3);
        settings.SetMdpProject(old, new MdpProject { Id = "1778", Name = "L'Orée" });
        foreach (var f in new[] { paths.ReviewFile(old), paths.CorrectionsFile(old), paths.AnalysisFile(old) })
        {
            Directory.CreateDirectory(Path.GetDirectoryName(f)!);
            File.WriteAllText(f, "{}");
        }
        var shell = new FakeShell { SheetAnswer = s => s with { Folder = nouveau } };
        var vm = new MainViewModel(shell, paths, settings, enginePath: null);
        Assert.NotNull(await vm.EditSheetAsync(old, "LIVRAISON 1"));
        Assert.True(File.Exists(paths.ReviewFile(nouveau)) && File.Exists(paths.CorrectionsFile(nouveau)));
        Assert.False(File.Exists(paths.ReviewFile(old)) || File.Exists(paths.AnalysisFile(old)));   // analyse jetée : réanalyse
        Assert.Equal("1778", settings.FindMdpProject(nouveau)!.Id);
        Assert.Null(settings.FindMdpProject(old));
        Assert.Equal(ProjectFolder.Normalize(nouveau), settings.Recents.Single().Path);
        var row = vm.Recents.Single();
        Assert.Equal(("1778", "L'Orée", "Infos à compléter"), (row.IdText, row.DisplayName, row.Warning));
    }

    [Fact]
    public async Task Changing_the_folder_can_be_refused()
    {
        using var tmp = new TempDir();
        var (old, nouveau) = (TreegramFolder(tmp, "A"), TreegramFolder(tmp, "B"));
        var settings = new AppSettings();
        settings.SetMdpProject(old, new MdpProject { Id = "1" });
        var shell = new FakeShell { ConfirmAnswer = false, SheetAnswer = s => s with { Folder = nouveau } };
        var vm = new MainViewModel(shell, new AppPaths(tmp.Path, tmp.Path), settings, enginePath: null);
        Assert.Null(await vm.EditSheetAsync(old, "A"));
        Assert.NotNull(settings.FindMdpProject(old));
        Assert.Null(settings.FindMdpProject(nouveau));
    }

    [Fact]
    public async Task New_project_saves_its_sheet_before_the_analysis()
    {
        using var tmp = new TempDir();
        var dir = TreegramFolder(tmp, "OUCHY B");
        var settings = new AppSettings();
        var shell = new FakeShell { FolderAnswer = dir, SheetAnswer = s => s with { Identity = new MdpProject { Id = "1900", Typologie = "Santé" } } };
        var vm = new MainViewModel(shell, new AppPaths(tmp.Path, tmp.Path), settings, enginePath: null);
        await vm.NewProjectCommand.ExecuteAsync(null);
        Assert.Equal(("1900", "OUCHY B", "Santé"), (settings.FindMdpProject(dir)!.Id, settings.FindMdpProject(dir)!.Name,
                                                      settings.FindMdpProject(dir)!.Typologie));   // nom : celui du dossier
        Assert.Single(settings.Recents);
    }

    [Fact]
    public void Missing_folder_stays_listed_with_a_warning()
    {
        using var tmp = new TempDir();
        var settings = new AppSettings();
        settings.Touch(Path.Combine(tmp.Path, "DISPARU"), "DISPARU", DateTime.Now, 0);
        var vm = new MainViewModel(new FakeShell(), new AppPaths(tmp.Path, tmp.Path), settings, enginePath: null);
        Assert.Equal("Dossier introuvable", vm.Recents.Single().Warning);
    }

    [Fact]
    public void Identity_for_the_engine_keeps_only_filled_fields()
    {
        using var tmp = new TempDir();
        var path = ProjectIdentity.WriteEngineFile(new MdpProject { Id = " 1778 ", Typologie = "Santé" }, Path.Combine(tmp.Path, "id.json"));
        var json = System.Text.Json.JsonSerializer.Deserialize<Dictionary<string, string>>(File.ReadAllText(path))!;
        Assert.Equal(new Dictionary<string, string> { ["ID projet"] = "1778", ["Categorie d'Ouvrage"] = "Santé" }, json);
        Assert.Equal("Logement", ProjectIdentity.Short("Logement (100-90% SU)"));
        Assert.Equal("Log. mixte", ProjectIdentity.Short("Logement Mixte (>10% autres affectations)"));
        Assert.Equal("Non identifié", ProjectIdentity.Short(null));
    }
}

public class DeleteProjectTests
{
    [Fact]
    public async Task Delete_forgets_the_project_and_its_data_but_not_the_treegram_folder()
    {
        using var tmp = new TempDir();
        var project = Directory.CreateDirectory(Path.Combine(tmp.Path, "L OREE")).FullName;
        var paths = new AppPaths(Path.Combine(tmp.Path, "roaming"), Path.Combine(tmp.Path, "local"));
        var files = new[] { paths.ReviewFile(project), paths.CorrectionsFile(project), paths.AnalysisFile(project),
                            Path.Combine(paths.AiReviewDir(project), "r.md") };
        foreach (var f in files) { Directory.CreateDirectory(Path.GetDirectoryName(f)!); File.WriteAllText(f, "{}"); }
        var settings = new AppSettings();
        settings.Touch(project, "L OREE", DateTime.Today, 3);
        settings.SetMdpProject(project, new MdpProject { Id = "1778", Name = "L'Orée" });
        var shell = new FakeShell();
        var vm = new MainViewModel(shell, paths, settings, enginePath: null);

        shell.ConfirmAnswer = false;
        await vm.DeleteRecentCommand.ExecuteAsync(vm.Recents.Single());
        Assert.True(File.Exists(files[0]));                                     // annulé : rien n'est effacé

        shell.ConfirmAnswer = true;
        await vm.DeleteRecentCommand.ExecuteAsync(vm.Recents.Single());
        Assert.Empty(vm.Recents);
        Assert.All(files, f => Assert.False(File.Exists(f)));
        Assert.Null(settings.FindMdpProject(project));
        Assert.True(Directory.Exists(project));                                 // le dossier Treegram reste
        Assert.Empty(AppSettings.Load(paths).Recents);
    }
}

public class CorrectionPieceTests
{
    [Fact]
    public void Piece_number_follows_the_location()
    {
        var c = JsonSerializer.Deserialize<Correction>("""
            {"id": "abords-E09-N00-2", "op": "découper", "cible": {"ids": ["s"]}, "vers": "SA", "aire": 113.57,
             "morceau": "2/3", "groupe": "abords-E09-N00", "statut": "proposée", "origine": "règle", "explication": ""}
            """)!;
        var item = new CorrectionItem(c, null, new Surface { Id = "s", Building = "E09", Level = "N00", Category = "SEP" });
        Assert.Equal("E09·N00 2/3", item.Location);
        Assert.Contains("morceau", JsonSerializer.Serialize(c));                 // rendu tel quel au moteur
    }
}

public class ProjectStatusTests
{
    [Fact]
    public void Registry_creates_projects_in_progress_and_keeps_the_history()
    {
        using var tmp = new TempDir();
        var reg = new ProjectRegistry(Path.Combine(tmp.Path, "projets.json"));
        var r = reg.Touch(tmp.Path + "\\", "L OREE", DateTime.Today, 135);
        Assert.Equal(ProjectStatus.InProgress, r.Status);
        reg.SetStatus(tmp.Path, ProjectStatus.Done, "td");
        Assert.Equal(ProjectStatus.Done, reg.StatusOf(tmp.Path.ToUpperInvariant()));     // même dossier, autre écriture
        reg.Touch(tmp.Path, "L OREE", DateTime.Today, 12);                                // réanalyse : le statut reste
        var saved = reg.Find(tmp.Path)!;
        Assert.Equal(ProjectStatus.Done, saved.Status);
        Assert.Equal(12, saved.IssueCount);
        Assert.Equal([ProjectStatus.InProgress, ProjectStatus.Done], saved.History.Select(h => h.Status));
        // Format lu par n8n : codes stables et libellé
        var p = System.Text.Json.JsonDocument.Parse(File.ReadAllText(reg.FilePath)).RootElement.GetProperty("Projects")[0];
        Assert.Equal("traite", p.GetProperty("Status").GetString());
        Assert.Equal("Traité", p.GetProperty("StatusLabel").GetString());
        reg.Forget(tmp.Path);
        Assert.Null(reg.Find(tmp.Path));
    }

    [Fact]
    public async Task Toggle_asks_before_marking_done_with_work_left()
    {
        using var tmp = new TempDir();
        var shell = new FakeShell();
        var vm = new MainViewModel(shell, new AppPaths(tmp.Path, tmp.Path), new AppSettings(), enginePath: null)
        {
            AiSearchBaseDir = tmp.Path,
        };
        vm.LoadDocument(tmp.Path, SubjectFixture.Doc());
        Assert.False(vm.IsProjectDone);
        Assert.Equal("En traitement", vm.ProjectStatusLabel);
        Assert.True(vm.OpenIssuesToReview + vm.UndecidedCorrections > 0);

        shell.ConfirmAnswer = false;
        await vm.ToggleProjectStatusCommand.ExecuteAsync(null);
        Assert.False(vm.IsProjectDone);                                                   // annulé

        shell.ConfirmAnswer = true;
        await vm.ToggleProjectStatusCommand.ExecuteAsync(null);
        Assert.True(vm.IsProjectDone);
        Assert.Equal(ProjectStatus.Done, new ProjectRegistry(new AppPaths(tmp.Path, tmp.Path).ProjectsFile).StatusOf(tmp.Path));
        // validé : le MDP part vers la base ; sans moteur, le projet reste traité et le message le dit
        Assert.Contains(shell.Notes, n => n.Contains("passé en traité, MDP non ajouté à la base : moteur d'analyse introuvable"));

        await vm.ToggleProjectStatusCommand.ExecuteAsync(null);                           // retour sans question
        Assert.False(vm.IsProjectDone);
    }
}
