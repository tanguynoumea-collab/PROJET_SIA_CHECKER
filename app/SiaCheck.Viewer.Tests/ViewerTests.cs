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
