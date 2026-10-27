using System.IO;
using System.Windows.Media;
using System.Windows.Media.Media3D;
using SiaCheck.Viewer.Models;
using SiaCheck.Viewer.Scene;
using SiaCheck.Viewer.Services;
using SiaCheck.Viewer.ViewModels;

namespace SiaCheck.Viewer.Tests;

public sealed class TempDir : IDisposable
{
    public string Path { get; } = Directory.CreateTempSubdirectory("siacheck-").FullName;
    public void Dispose() => Directory.Delete(Path, recursive: true);
}

internal static class Fixture
{
    public static string File(string name) => Path.Combine(AppContext.BaseDirectory, "Fixtures", name);
    public static ViewerDocument Synth() => ViewerDocument.Load(File("synth.viewer.json"));
}

public class ContractTests
{
    [Fact]
    public void Loads_document_produced_by_python_engine()
    {
        var doc = Fixture.Synth();
        Assert.Equal("Synth", doc.Project);
        Assert.Equal(61, doc.Surfaces.Count);
        Assert.Equal(3, doc.Surfaces.Count(s => s.Mesh is not null));
        Assert.Contains(doc.Issues, i => i.Key == "R3|ERR|N00||SEP" && i.SurfaceIds.Contains("err-n00-sep"));
        Assert.Equal("#B1005D", doc.Categories.Single(c => c.Code == "SP").Color);
        var lv = doc.Levels.Single(l => l is { Building: "ERR", Level: "N00" });
        Assert.Equal(100, lv.Value("SP"));
        Assert.Equal("ERREUR", lv.R1!.Verdict);
    }

    [Fact]
    public void Rejects_other_format_version()
    {
        using var tmp = new TempDir();
        var path = Path.Combine(tmp.Path, "v9.json");
        File.WriteAllText(path, """{"format":"sia-check-viewer","version":9}""");
        var ex = Assert.Throws<InvalidDataException>(() => ViewerDocument.Load(path));
        Assert.Contains("version 9", ex.Message);
    }
}

public class ReviewStoreTests
{
    private static Issue MakeIssue(string key) => new() { Key = key, Rule = "R1", Verdict = "ERREUR", Building = "B", Level = "N00", Message = "m" };

    [Fact]
    public void Status_and_comment_survive_reopening()
    {
        using var tmp = new TempDir();
        var path = Path.Combine(tmp.Path, "p.review.json");
        ReviewStore.Open(path, "X").Set("k1", ReviewStatus.FalsePositive, "SC réelle", MakeIssue("k1"), "2026-10-21");
        var again = ReviewStore.Open(path, "X").Get("k1");
        Assert.Equal(ReviewStatus.FalsePositive, again.Status);
        Assert.Equal("SC réelle", again.Comment);
    }

    [Fact]
    public void Tracked_issue_absent_from_new_analysis_is_resolved()
    {
        using var tmp = new TempDir();
        var store = ReviewStore.Open(Path.Combine(tmp.Path, "p.json"), "X");
        store.Set("k1", ReviewStatus.Seen, "", MakeIssue("k1"), "2026-10-21");
        store.Set("k2", ReviewStatus.Seen, "", MakeIssue("k2"), "2026-10-21");
        var resolved = store.Reconcile([MakeIssue("k2"), MakeIssue("k3")], "2026-10-22");
        Assert.Equal(["k1"], resolved.Select(r => r.Key));
    }

    [Fact]
    public void Untouched_issue_has_default_status()
    {
        using var tmp = new TempDir();
        Assert.Equal(ReviewStatus.ToReview, ReviewStore.Open(Path.Combine(tmp.Path, "p.json"), "X").Get("nope").Status);
    }

    [Fact]
    public void Corrupted_file_is_kept_aside_not_lost()
    {
        using var tmp = new TempDir();
        var path = Path.Combine(tmp.Path, "p.json");
        File.WriteAllText(path, "{ pas du json");
        ReviewStore.Open(path, "X");
        Assert.True(File.Exists(path + ".corrompu"));
    }
}

public class AppPathsTests
{
    [Fact]
    public void Slug_is_readable_and_distinguishes_homonyms()
    {
        var a = AppPaths.Slug(@"C:\Projets\L OREE");
        var b = AppPaths.Slug(@"D:\Archives\L OREE");
        Assert.StartsWith("L_OREE-", a);
        Assert.NotEqual(a, b);
        Assert.EndsWith(a[^8..], AppPaths.Slug(@"c:\projets\l oree\"));
    }

    [Fact]
    public void Default_settings_round_trip()
    {
        using var tmp = new TempDir();
        var paths = new AppPaths(tmp.Path, tmp.Path);
        new AppSettings().Save(paths);
        Assert.Null(AppSettings.Load(paths).Window.Left);
    }

    [Fact]
    public void Recents_are_most_recent_first_and_capped()
    {
        var s = new AppSettings();
        for (var i = 0; i < 10; i++) s.Touch($@"C:\p{i}", $"p{i}", DateTime.Now, i);
        s.Touch(@"C:\p3", "p3", DateTime.Now, 3);
        Assert.Equal(AppSettings.MaxRecents, s.Recents.Count);
        Assert.Equal("p3", s.Recents[0].Name);
    }
}

public class EngineTests
{
    [Fact]
    public void Error_message_is_last_error_line()
    {
        var run = new EngineRun(2, "INFO ÉTAPE 1/3 lecture\nERROR fichier introuvable : x.tgm\n");
        Assert.False(run.Succeeded);
        Assert.Equal("fichier introuvable : x.tgm", run.ErrorMessage);
    }

    [Theory]
    [InlineData(0, true)]
    [InlineData(1, true)]   // écarts trouvés : l'analyse a réussi
    [InlineData(2, false)]
    public void Exit_codes(int code, bool ok) => Assert.Equal(ok, new EngineRun(code, "").Succeeded);
}

public class SceneTests
{
    private static SceneController Scene(ViewerDocument doc) => new(doc, new SiaPalette(doc.Categories), Colors.Gray);

    [Fact]
    public void Builds_one_level_group_per_level_with_geometry()
    {
        var scene = Scene(Fixture.Synth());
        Assert.Equal(3, scene.SurfacesWithGeometry);
        Assert.Equal(2, scene.Root.Children.Count);   // ERR·N00 et OK·N01
    }

    [Fact]
    public void Focus_returns_bounds_and_click_maps_back_to_surface()
    {
        var scene = Scene(Fixture.Synth());
        var bounds = scene.Focus(["err-n00-seu", "inexistant"]);
        Assert.NotNull(bounds);
        Assert.Equal(10, bounds!.Value.X, 3);
        Assert.True(scene.IsFocused);
        var focusModel = ((Model3DGroup)scene.Root.Children[0]).Children.OfType<GeometryModel3D>().First();
        Assert.Equal("err-n00-seu", scene.SurfaceAt(focusModel, 2));
    }

    [Fact]
    public void Focus_cuts_levels_above_the_focused_altitude()
    {
        var doc = Fixture.Synth();
        // ERR·N00 (rang 0) a une géométrie ; on ajoute un niveau supérieur ERR·N01 avec maillage.
        doc.Surfaces.Add(new Surface
        {
            Id = "upper", Building = "ERR", Level = "N01", Category = "SUP", Code = "SUP", Kind = "leaf",
            Mesh = new MeshData { Vertices = [0, 0, 3, 1, 0, 3, 1, 1, 3], Indices = [0, 1, 2] },
        });
        var scene = Scene(doc);
        Assert.Equal(3, scene.Root.Children.Count);
        scene.Focus(["err-n00-sep"]);
        Assert.Equal(2, scene.Root.Children.Count);   // ERR·N01 (z = 3) coupé ; OK·N01 (z = 0,03) conservé en fantôme
        scene.ClearFocus();
        Assert.Equal(3, scene.Root.Children.Count);
    }

    [Fact]
    public void Explode_moves_upper_levels_only()
    {
        var scene = Scene(Fixture.Synth());
        scene.SetExplode(5);
        var b = scene.Bounds(["ok-n01-sup"])!.Value;
        Assert.Equal(0.03, b.Z, 3);   // seul niveau de son bâtiment : ordinal 0
    }

    [Fact]
    public void Hidden_layers_and_filters_remove_groups()
    {
        var scene = Scene(Fixture.Synth());
        scene.SetVisibleCodes(["SUP"]);
        Assert.Single(scene.Root.Children);
        scene.SetVisibleCodes(["SUP", "SEP", "SEU"]);
        scene.SetFilter(["ERR"], null);
        Assert.Single(scene.Root.Children);
    }
}

public class ExtrusionTests
{
    [Fact]
    public void Boundary_of_two_triangle_square_is_its_four_sides()
    {
        // Carré 0-1-2-3 en deux triangles : la diagonale 0-2 est intérieure, elle ne fait pas de chant.
        var edges = SceneController.BoundaryEdges([0, 1, 2, 0, 2, 3]).ToList();
        Assert.Equal(4, edges.Count);
        Assert.DoesNotContain(edges, e => (e.A, e.B) is (0, 2) or (2, 0));
    }

    [Fact]
    public void Slabs_have_top_and_edge_models_per_category()
    {
        var doc = Fixture.Synth();
        var scene = new SceneController(doc, new SiaPalette(doc.Categories), Colors.Gray);
        var err = (Model3DGroup)scene.Root.Children[0];
        var models = err.Children.OfType<GeometryModel3D>().ToList();
        Assert.Equal(4, models.Count);   // SEP et SEU : dessus + chants
        var edge = (MeshGeometry3D)models[1].Geometry;
        Assert.Equal(16, edge.Positions.Count);   // 4 côtés × 4 sommets
        Assert.Equal(0.03 - 0.15, edge.Positions.Min(p => p.Z), 3);
    }
}

internal sealed class FakeShell : IShell
{
    public List<string> Notes { get; } = [];
    public string? FolderAnswer { get; set; }
    public string? PickFolder(string title, string? initial) => FolderAnswer;
    public string? PickSaveFile(string title, string fileName, string filter) => null;
    public string? PickOpenFile(string title, string filter) => null;
    public void Notify(string message, bool isError = false) => Notes.Add(message);
    public bool ConfirmAnswer { get; set; } = true;
    public Task<bool> ConfirmAsync(string title, string message, string yes, string no) => Task.FromResult(ConfirmAnswer);
    public string[]? AskAnswer { get; set; }
    public Task<string[]?> AskAsync(string title, string message, IReadOnlyList<(string Label, string Value)> fields, string ok) =>
        Task.FromResult(AskAnswer);
    public MdpProject? IdentityAnswer { get; set; }
    public IdentityMode? IdentityMode { get; private set; }
    public Task<MdpProject?> AskIdentityAsync(MdpProject initial, IdentityLists lists, IdentityMode mode, string ok)
    {
        IdentityMode = mode;
        return Task.FromResult(IdentityAnswer);
    }
    /// <summary>Réponse de la fiche projet : appelée avec la fiche proposée (null = annuler).</summary>
    public Func<ProjectSheet, ProjectSheet?> SheetAnswer { get; set; } = _ => null;
    public ProjectSheet? SheetShown { get; private set; }
    public SheetCheck? LastCheck { get; private set; }
    public int SheetCount { get; private set; }
    public Task<ProjectSheet?> AskProjectSheetAsync(ProjectSheet initial, IdentityLists lists, bool creating, Func<ProjectSheet, SheetCheck> check)
    {
        SheetShown = initial;
        SheetCount++;
        var answer = SheetAnswer(initial);
        LastCheck = answer is null ? null : check(answer);
        return Task.FromResult(answer);
    }
    public void OpenFile(string path) { }
    public void Frame(Rect3D? bounds) { }
    public void ApplyTheme(string theme) { }
    public Color GhostColor => Colors.Gray;
    public Color AccentColor => Colors.SlateBlue;
}

public class InteractionTests
{
    private static MainViewModel Loaded(TempDir tmp)
    {
        var vm = new MainViewModel(new FakeShell(), new AppPaths(tmp.Path, tmp.Path), new AppSettings(), enginePath: null);
        vm.LoadDocument(tmp.Path, Fixture.Synth());
        vm.StatusFilter = "all";
        return vm;
    }

    [Fact]
    public void Clicking_the_focused_issue_again_leaves_isolation()
    {
        using var tmp = new TempDir();
        var vm = Loaded(tmp);
        var item = vm.Issues.Single(i => i.Key == "R3|ERR|N00||SEP");
        vm.ToggleFocusCommand.Execute(item);
        Assert.True(vm.IsFocused);
        Assert.True(item.IsFocused);
        vm.ToggleFocusCommand.Execute(item);
        Assert.False(vm.IsFocused);
        Assert.False(item.IsFocused);
        Assert.Null(vm.FocusedIssue);
    }

    [Fact]
    public void Clicking_another_issue_moves_isolation()
    {
        using var tmp = new TempDir();
        var vm = Loaded(tmp);
        var a = vm.Issues.Single(i => i.Key == "R3|ERR|N00||SEP");
        var b = vm.Issues.Single(i => i.Key == "A1|ERR|N00||SEP");
        vm.ToggleFocusCommand.Execute(a);
        vm.ToggleFocusCommand.Execute(b);
        Assert.True(vm.IsFocused);
        Assert.False(a.IsFocused);
        Assert.Same(b, vm.FocusedIssue);
    }

    [Fact]
    public void Clicked_surface_marks_and_lists_the_issues_that_cite_it()
    {
        using var tmp = new TempDir();
        var vm = Loaded(tmp);
        IssueItem? scrolledTo = null;
        vm.LinkedIssuesChanged += i => scrolledTo = i;
        vm.SelectSurface("err-n00-seu");
        var linked = vm.Issues.Where(i => i.IsLinked).Select(i => i.Rule).ToHashSet();
        Assert.Contains("R3", linked);
        Assert.Contains("A1", linked);
        Assert.Equal(vm.SelectedSurface!.Issues.Count, vm.Issues.Count(i => i.IsLinked));
        Assert.NotNull(scrolledTo);
        vm.SelectSurface(null);
        Assert.DoesNotContain(vm.Issues, i => i.IsLinked);
    }

    [Fact]
    public void Issues_carry_title_and_hint()
    {
        using var tmp = new TempDir();
        var vm = Loaded(tmp);
        var item = vm.Issues.Single(i => i.Key == "R3|ERR|N00||SEP");
        Assert.Equal("Surface externe non classée", item.Title);
        Assert.True(item.HasHint);
        Assert.Contains("À vérifier", item.Tooltip);
    }

    [Fact]
    public void Layers_carry_sia_label_for_tooltip()
    {
        using var tmp = new TempDir();
        var vm = Loaded(tmp);
        var sup = vm.Layers.Single(l => l.Code == "SUP");
        Assert.Equal("SUP · Surface utile principale (SIA 416 §2.1.1.1)", sup.Title);
        Assert.True(sup.HasDefinition);
    }
}

public class BalanceTests
{
    [Fact]
    public void Rows_share_building_scale()
    {
        var doc = Fixture.Synth();
        var lv = doc.Levels.Single(l => l is { Building: "ERR", Level: "N00" });
        var row = new BalanceRow(lv, 100);
        Assert.True(row.HasFloor);
        Assert.Equal(35, row.R1Diff, 3);
        Assert.Contains("A1", row.Alerts);
    }
}

public class IssueItemTests
{
    [Theory]
    [InlineData("*", "*", null, "Projet")]
    [InlineData("B03", "*", null, "B03 · tous niveaux")]
    [InlineData("B03", "N00", null, "B03·N00")]
    [InlineData("B03", "N01", "B03_N01_Apart-07", "B03·N01 · Apart-07")]
    public void Location_label(string b, string l, string? lot, string expected)
    {
        var item = new IssueItem(new Issue { Key = "k", Building = b, Level = l, Lot = lot }, new ReviewEntry());
        Assert.Equal(expected, item.Location);
    }
}

public class RatioTests
{
    [Fact]
    public void Ratios_are_read_with_project_scope()
    {
        var doc = Fixture.Synth();
        var sn = doc.Ratios.Single(r => r.Building == "OK" && r.Id == "SN/SP");
        Assert.Equal(0.9, sn.Value!.Value, 6);
        Assert.Equal("haut", sn.Status);
        Assert.True(sn.HasReference);
        Assert.Contains(doc.Ratios, r => r.Building == Ratio.AllBuildings);
    }

    [Fact]
    public void Row_judges_building_and_formats_swiss()
    {
        var doc = Fixture.Synth();
        var row = new RatioRow(doc.Ratios.Single(r => r.Building == Ratio.AllBuildings && r.Id == "SN/SP"),
                               doc.Ratios.Single(r => r.Building == "OK" && r.Id == "SN/SP"));
        Assert.Equal("0,900", row.BuildingText);
        Assert.Equal("0,780–0,880", row.ReferenceText);
        Assert.True(row.IsOutside);
        Assert.Contains("non normatif", row.Tooltip);
    }

    [Fact]
    public void Area_per_lot_is_informative()
    {
        var doc = Fixture.Synth();
        var lot = doc.Ratios.Single(r => r.Building == "OK" && r.Id == "SNH/lot");
        var row = new RatioRow(lot, null);
        Assert.Equal("80,0 m²", row.ProjectText);
        Assert.Equal("indicatif", row.ReferenceText);
        Assert.False(row.IsOutside);
        Assert.Null(SiaCheck.Viewer.Controls.RatioGauge.Domain(row));
    }

    [Fact]
    public void Gauge_domain_covers_reference_and_values()
    {
        var doc = Fixture.Synth();
        var row = new RatioRow(doc.Ratios.Single(r => r.Building == Ratio.AllBuildings && r.Id == "SN/SP"),
                               doc.Ratios.Single(r => r.Building == "OK" && r.Id == "SN/SP"));
        var (min, max) = SiaCheck.Viewer.Controls.RatioGauge.Domain(row)!.Value;
        Assert.True(min < 0.78 && max > 0.9);
    }

    [Fact]
    public void Older_documents_without_ratios_still_load()
    {
        using var tmp = new TempDir();
        var path = Path.Combine(tmp.Path, "old.viewer.json");
        var json = System.Text.Json.Nodes.JsonNode.Parse(System.IO.File.ReadAllText(Fixture.File("synth.viewer.json")))!.AsObject();
        json.Remove("ratios");
        System.IO.File.WriteAllText(path, json.ToJsonString());
        Assert.Empty(ViewerDocument.Load(path).Ratios);
    }
}

public class EngineStampTests
{
    [Fact]
    public void Dev_engine_is_as_new_as_the_repository_sources()
    {
        using var tmp = new TempDir();
        var exe = Path.Combine(tmp.Path, ".venv", "Scripts", "sia-check.exe");
        var py = Path.Combine(tmp.Path, "src", "sia_check", "viewer.py");
        Directory.CreateDirectory(Path.GetDirectoryName(exe)!);
        Directory.CreateDirectory(Path.GetDirectoryName(py)!);
        File.WriteAllText(exe, "");
        File.WriteAllText(py, "");
        File.SetLastWriteTime(exe, new DateTime(2026, 10, 1));
        File.SetLastWriteTime(py, new DateTime(2026, 10, 26, 13, 55, 0));
        Assert.Equal(new DateTime(2026, 10, 26, 13, 55, 0), AnalysisService.ModifiedOf(exe));
        var installed = Path.Combine(tmp.Path, "engine", "sia-check.exe");   // moteur livré : l'exécutable fait foi
        Directory.CreateDirectory(Path.GetDirectoryName(installed)!);
        File.WriteAllText(installed, "");
        File.SetLastWriteTime(installed, new DateTime(2026, 10, 2));
        Assert.Equal(new DateTime(2026, 10, 2), AnalysisService.ModifiedOf(installed));
    }
}
