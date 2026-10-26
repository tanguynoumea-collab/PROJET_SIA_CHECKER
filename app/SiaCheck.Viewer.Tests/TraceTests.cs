using System.IO;
using System.Text.Json;
using System.Windows;
using SiaCheck.Viewer.Models;
using SiaCheck.Viewer.Scene;
using SiaCheck.Viewer.Services;
using SiaCheck.Viewer.ViewModels;

namespace SiaCheck.Viewer.Tests;

/// <summary>Surfaces carrées au maillage triangulé, comme celles du fichier visionneuse.</summary>
internal static class Plan
{
    public static Surface Square(string id, string code, double x0, double y0, double x1, double y1, string kind = "leaf", string level = "N00") =>
        JsonSerializer.Deserialize<Surface>(JsonSerializer.Serialize(new
        {
            id, building = "A", level, category = code, code, kind, status = "checked", area = (x1 - x0) * (y1 - y0),
            mesh = new { v = new[] { x0, y0, 0, x1, y0, 0, x1, y1, 0, x0, y1, 0 }, i = new[] { 0, 1, 2, 0, 2, 3 } },
        }))!;

    /// <summary>SEP 20 × 10 (200 m²) dont une terrasse SEU 5 × 10 à droite ; plancher SP au niveau inférieur.</summary>
    public static TraceSession Session(Correction? existing = null, double r3 = 150, double applied = 0)
    {
        var sep = Square("sep", "SEP", 0, 0, 20, 10, kind: "node");
        var seu = Square("seu", "SEU", 15, 0, 20, 10);
        var below = Square("sp-s01", "SP", 0, 0, 12, 10, kind: "node", level: "S01");
        return new TraceSession(sep, [sep, seu], [below], "SA", existing, r3, applied, new Tolerance { AbsM2 = 0.5, Rel = 0.005 });
    }

    public static void Rectangle(TraceSession s, double x0, double y0, double x1, double y1)
    {
        s.AddPoint(new Point(x0, y0));
        s.AddPoint(new Point(x1, y0));
        s.AddPoint(new Point(x1, y1));
        s.AddPoint(new Point(x0, y1));
        Assert.True(s.ClosePolygon());
    }
}

public class TraceSessionTests
{
    [Fact]
    public void Counted_area_is_on_source_minus_classified_terraces()
    {
        var s = Plan.Session();
        Assert.True(s.HasGeometry);
        Assert.Equal(TraceMode.Draw, s.Mode);
        Plan.Rectangle(s, 10, 0, 30, 10);                         // 200 m², dont 100 sur la SEP et 50 sur la SEU
        Assert.Equal(100, s.OnSource, 3);
        Assert.Equal(50, s.RemovedClassified, 3);
        Assert.Equal(50, s.CountedArea, 3);
        Assert.Equal(100, s.Outside, 3);
        Assert.Equal(TraceMode.Edit, s.Mode);
        Assert.True(s.CanSave);
        Assert.Equal(150 - 50, s.R3After, 3);                    // aperçu : l'écart du niveau baisse de l'aire comptée
    }

    [Fact]
    public void Self_intersecting_or_empty_trace_cannot_be_saved()
    {
        var s = Plan.Session();
        s.AddPoint(new Point(1, 1));
        s.AddPoint(new Point(9, 9));
        s.AddPoint(new Point(9, 1));
        s.AddPoint(new Point(1, 9));                              // nœud papillon
        s.ClosePolygon();
        Assert.True(s.IsSelfIntersecting);
        Assert.False(s.CanSave);
        Assert.True(s.MessageIsError);
        var t = Plan.Session();
        Plan.Rectangle(t, 30, 0, 40, 10);                         // hors de la SEP
        Assert.Equal(0, t.CountedArea, 3);
        Assert.False(t.CanSave);
        Assert.Contains("ne recouvre pas", t.Message);
    }

    [Fact]
    public void Undo_redo_and_backspace()
    {
        var s = Plan.Session();
        s.AddPoint(new Point(0, 0));
        s.AddPoint(new Point(5, 0));
        s.RemoveLastPoint();
        Assert.Single(s.Polygons[0]);
        s.Undo();                                                 // annule le retrait
        Assert.Equal(2, s.Polygons[0].Count);
        s.Redo();
        Assert.Single(s.Polygons[0]);
        Assert.True(s.CancelOpenPolygon());
        Assert.Empty(s.Polygons);
    }

    [Fact]
    public void Snap_prefers_vertices_then_edges()
    {
        var s = Plan.Session();
        Assert.Equal(new Point(15, 0), s.Snap(new Point(15.2, 0.1), 0.5));        // coin de la SEU
        Assert.Equal(new Point(8, 10), s.Snap(new Point(8, 10.2), 0.5));          // arête haute de la SEP
        s.SnapToEdges = false;
        Assert.Null(s.Snap(new Point(8, 10.2), 0.5));
    }

    [Fact]
    public void Existing_trace_opens_in_edit_mode_and_saves_as_manual()
    {
        var existing = JsonSerializer.Deserialize<Correction>("""
            {"id": "abords-A-N00", "op": "découper", "cible": {"ids": ["sep"]}, "vers": "SA", "aire": 100.0, "origine": "règle",
             "statut": "acceptée", "explication": "x", "polygone": {"type": "Polygon", "coordinates": [[[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]]}}
            """)!;
        var s = Plan.Session(existing, r3: 50, applied: 100);
        Assert.Equal(TraceMode.Edit, s.Mode);
        Assert.Equal(100, s.CountedArea, 3);
        Assert.False(s.CanSave);                                  // rien n'a changé
        s.BeginChange();
        s.MoveVertex(0, 1, new Point(12, 0));
        s.MoveVertex(0, 2, new Point(12, 10));
        Assert.Equal(120, s.CountedArea, 3);
        Assert.Equal(50 + 100 - 120, s.R3After, 3);               // la correction déjà appliquée est rendue avant de compter la nouvelle
        var c = s.BuildCorrection("ignored", "S1");
        Assert.Equal("abords-A-N00", c.Id);
        Assert.Equal(120, c.Area);
        Assert.Equal("manuel", c.Origin);
        Assert.Equal("MultiPolygon", c.Extra!["polygone"].GetProperty("type").GetString());
        Assert.Equal(100.0, c.Extra["base"].GetProperty("aire").GetDouble());
        var tri = c.Trace!;
        var area = 0.0;
        for (var k = 0; k < tri.Indices.Length; k += 3)
        {
            double X(int i) => tri.Vertices[2 * tri.Indices[i]];
            double Y(int i) => tri.Vertices[2 * tri.Indices[i] + 1];
            area += Math.Abs((X(k + 1) - X(k)) * (Y(k + 2) - Y(k)) - (X(k + 2) - X(k)) * (Y(k + 1) - Y(k))) / 2;
        }
        Assert.Equal(120, area, 1);                               // la triangulation couvre l'aire comptée
    }
}

public class TraceViewModelTests
{
    private static Surface FixtureSurface(MainViewModel vm, string id) => vm.Document!.Surfaces.First(s => s.Id == id);

    [Fact]
    public void Retrace_a_proposal_keeps_its_decision_and_writes_the_journal()
    {
        using var tmp = new TempDir();
        var vm = SubjectFixture.Loaded(tmp);
        vm.SelectedSubject = vm.Subjects[0];
        vm.SelectedCorrection = vm.SelectedSubject.Corrections[0];       // découpe de err-n00-sep (maillage dans la fixture)
        vm.SetCorrectionDecisionCommand.Execute("accepted");
        Assert.True(vm.CanTraceSelected);
        vm.OpenTraceForCorrectionCommand.Execute(null);
        Assert.True(vm.IsTraceOpen);
        var t = vm.Trace!;
        t.Clear();
        var b = t.Shapes.First(x => x.IsSource).Paths.SelectMany(p => p).ToList();
        var (x0, x1, y0, y1) = (b.Min(p => p.x), b.Max(p => p.x), b.Min(p => p.y), b.Max(p => p.y));
        Plan.Rectangle(t, x0, y0, (x0 + x1) / 2, y1);                    // la moitié de la source
        Assert.True(t.CanSave);
        vm.SaveTraceCommand.Execute(null);
        Assert.False(vm.IsTraceOpen);
        var c = vm.SelectedCorrection!;
        Assert.Equal(CorrectionDecision.Accepted, c.Decision);
        Assert.Equal("manuel", c.Model.Origin);
        var journal = File.ReadAllText(new AppPaths(tmp.Path, tmp.Path).CorrectionsFile(tmp.Path));
        Assert.Contains("polygone", journal);
        Assert.Contains("manuel", journal);
    }

    [Fact]
    public void Cut_from_a_surface_creates_a_manual_correction_in_its_subject()
    {
        using var tmp = new TempDir();
        var vm = SubjectFixture.Loaded(tmp);
        vm.SelectSurface("err-n00-sep");
        vm.OpenTraceForSurfaceCommand.Execute(null);
        Assert.True(vm.IsTraceManual);
        Assert.Equal("SA", vm.TraceTarget);
        var t = vm.Trace!;
        var b = t.Shapes.First(x => x.IsSource).Paths.SelectMany(p => p).ToList();
        Plan.Rectangle(t, b.Min(p => p.x), b.Min(p => p.y), b.Max(p => p.x), b.Max(p => p.y));
        vm.SaveTraceCommand.Execute(null);
        Assert.Equal("S1", vm.SelectedSubject!.Id);                     // la surface est dans S1
        var created = vm.SelectedSubject.Corrections.Single(c => c.Id.StartsWith("manuel-"));
        Assert.Equal("SA", created.Model.To);
        Assert.Equal(CorrectionDecision.Proposed, created.Decision);
        Assert.Contains(SubjectFixture.Loaded(tmp).Subjects[0].Corrections, c => c.Id == created.Id);   // gardée au journal
    }

    [Fact]
    public async Task Cancelling_a_changed_trace_asks_first()
    {
        using var tmp = new TempDir();
        var shell = new FakeShell { ConfirmAnswer = false };
        var vm = new MainViewModel(shell, new AppPaths(tmp.Path, tmp.Path), new AppSettings(), enginePath: null) { AiSearchBaseDir = tmp.Path };
        vm.LoadDocument(tmp.Path, SubjectFixture.Doc());
        vm.SelectSurface("err-n00-sep");
        vm.OpenTraceForSurfaceCommand.Execute(null);
        vm.Trace!.AddPoint(new Point(0, 0));
        await vm.CancelTraceCommand.ExecuteAsync(null);
        Assert.True(vm.IsTraceOpen);                                    // « Continuer le tracé »
        shell.ConfirmAnswer = true;
        await vm.CancelTraceCommand.ExecuteAsync(null);
        Assert.False(vm.IsTraceOpen);
        _ = FixtureSurface(vm, "err-n00-sep");
    }
}

public class SurfaceEditTests
{
    private static readonly Tolerance Tol = new() { AbsM2 = 0.5, Rel = 0.005 };

    [Fact]
    public void Reshape_starts_from_the_outline_and_edges_reopen_the_contour()
    {
        var sus = Plan.Square("sus", "SUS", 0, 0, 10, 4);                // 40 m²
        var s = new TraceSession(sus, [sus], [], "SUS", null, 0, 0, Tol, TraceKind.Reshape);
        Assert.Equal(TraceMode.Edit, s.Mode);
        Assert.Single(s.Polygons);
        Assert.Equal(40, s.CountedArea, 3);
        Assert.False(s.CanSave);                                          // rien de changé

        var poly = s.Polygons[0];
        var right = Enumerable.Range(0, poly.Count).First(i => poly[i].X == 10 && poly[(i + 1) % poly.Count].X == 10);
        s.BeginChange();
        s.MoveEdge(0, right, new Vector(-4, 0));                          // l'arête de droite recule de 4 m
        Assert.Equal(24, s.CountedArea, 3);
        Assert.True(s.CanSave);

        Assert.True(s.DeleteEdge(0, right));                             // le contour s'ouvre là
        Assert.True(s.IsDrawingOpen);
        Assert.Equal(TraceMode.Draw, s.Mode);
        Assert.False(s.CanSave);
        Assert.True(s.IsFirstPoint(s.Polygons[^1][0], 0.1));
        Assert.True(s.ClosePolygon());                                   // refermé tel quel : même aire
        Assert.Equal(24, s.CountedArea, 3);

        var c = s.BuildCorrection("m1", "manuel");
        Assert.Equal(("remodeler", (string?)null), (c.Op, c.To));        // type inchangé
        Assert.Equal(24, c.Area);
        Assert.True(c.Extra!.ContainsKey("polygone") && c.Extra.ContainsKey("z"));
    }

    [Fact]
    public void A_type_change_alone_can_be_saved()
    {
        var sus = Plan.Square("sus", "SUS", 0, 0, 10, 4);
        var s = new TraceSession(sus, [sus], [], "SUS", null, 0, 0, Tol, TraceKind.Reshape) { Target = "SUP" };
        Assert.True(s.CanSave);
        Assert.Equal("SUP", s.BuildCorrection("m1", null).To);
    }

    [Fact]
    public void Create_draws_a_new_surface_on_the_level()
    {
        var sp = Plan.Square("sp", "SP", 0, 0, 20, 10, kind: "node");
        var source = new Surface { Id = "", Building = "A", Level = "N00", Category = "SUS", Code = "SUS", Kind = "leaf" };
        var s = new TraceSession(source, [sp], [], "SUS", null, 0, 0, Tol, TraceKind.Create);
        Assert.Equal(TraceMode.Draw, s.Mode);
        Plan.Rectangle(s, 0, 0, 5, 4);
        var c = s.BuildCorrection("c1", "manuel");
        Assert.Equal(("créer", "SUS", 20.0), (c.Op, c.To, c.Area));
        Assert.Equal(JsonValueKind.Undefined, c.Target.ValueKind);       // pas de cible : le niveau suffit
        Assert.Equal("N00", c.Extra!["niveau"].GetProperty("level").GetString());
    }

    [Fact]
    public async Task Modify_create_and_delete_from_the_viewer_are_accepted_manual_corrections()
    {
        using var tmp = new TempDir();
        var vm = SubjectFixture.Loaded(tmp);

        vm.SelectSurface("err-n00-sep");
        vm.OpenReshapeForSurfaceCommand.Execute(null);
        Assert.True(vm.Trace!.IsReshape);
        vm.TraceTarget = "SEU";                                          // changement de type seul
        vm.SaveTraceCommand.Execute(null);
        var modif = vm.SelectedCorrection!;
        Assert.Equal(("remodeler", "SEU", CorrectionDecision.Accepted), (modif.Model.Op, modif.Model.To, modif.Decision));

        vm.OpenCreateSurfaceCommand.Execute(null);
        Assert.True(vm.IsTraceCreate);
        Assert.Equal(("ERR", "N00"), (vm.TraceBuilding, vm.TraceLevel));   // niveau de la surface sélectionnée
        vm.TraceTarget = "SUS";
        Plan.Rectangle(vm.Trace!, 0, 0, 2, 3);
        vm.SaveTraceCommand.Execute(null);
        var created = vm.SelectedCorrection!;
        Assert.Equal(("créer", "SUS", "ERR·N00"), (created.Model.Op, created.Model.To, created.Location));
        Assert.Equal(CorrectionDecision.Accepted, created.Decision);

        vm.SelectSurface("err-n00-sep");
        await vm.DeleteSelectedSurfaceCommand.ExecuteAsync(null);
        var deleted = vm.SelectedCorrection!;
        Assert.Equal(("exclure", CorrectionDecision.Accepted), (deleted.Model.Op, deleted.Decision));
        Assert.Equal(3, vm.PendingCorrections);                          // à appliquer par Analyser
    }
}

public class ScenePreviewTests
{
    [Fact]
    public async Task Decided_edits_show_in_the_3D_before_the_analysis()
    {
        using var tmp = new TempDir();
        var vm = SubjectFixture.Loaded(tmp);
        var scene = vm.Scene!;
        var before = scene.SurfacesOfLevel("ERR", "N00").ToHashSet();
        Assert.Contains("err-n00-sep", before);

        vm.SelectSurface("err-n00-sep");
        await vm.DeleteSelectedSurfaceCommand.ExecuteAsync(null);         // acceptée : masquée tout de suite
        Assert.DoesNotContain("err-n00-sep", scene.SurfacesOfLevel("ERR", "N00"));

        vm.OpenCreateSurfaceCommand.Execute(null);
        vm.TraceTarget = "SUS";
        Plan.Rectangle(vm.Trace!, 0, 0, 2, 3);
        vm.SaveTraceCommand.Execute(null);                                 // nouvelle surface : ajoutée à son niveau
        Assert.Contains(scene.SurfacesOfLevel("ERR", "N00"), SceneController.IsPreview);

        vm.SelectedCorrection!.Decision = CorrectionDecision.Rejected;    // rejetée : l'aperçu disparaît
        Assert.DoesNotContain(scene.SurfacesOfLevel("ERR", "N00"), SceneController.IsPreview);
    }
}

public class PendingSurfaceTests
{
    [Fact]
    public async Task A_modified_or_created_surface_opens_its_card_and_reuses_its_correction()
    {
        using var tmp = new TempDir();
        var vm = SubjectFixture.Loaded(tmp);
        vm.SelectSurface("err-n00-sep");
        vm.OpenReshapeForSurfaceCommand.Execute(null);
        var t = vm.Trace!;
        t.BeginChange();
        t.MoveEdge(0, 0, new Vector(0, 1));                              // emprise redessinée
        vm.SaveTraceCommand.Execute(null);
        var modif = vm.SelectedCorrection!;
        var preview = vm.Scene!.SurfacesOfLevel("ERR", "N00").Single(SceneController.IsPreview);

        vm.SelectSurface(preview);                                       // clic sur la nouvelle emprise en 3D
        Assert.NotNull(vm.SelectedSurface);
        Assert.Equal(modif.Id, vm.SelectedSurface!.Pending!.Id);
        Assert.Equal("err-n00-sep", vm.SelectedSurface.Surface.Id);
        Assert.False(vm.SelectedSurface.CanCut);

        vm.OpenReshapeForSurfaceCommand.Execute(null);                   // « Modifier… » reprend la même correction
        Assert.True(vm.ShowTraceTargets);
        vm.TraceTarget = "SEU";
        vm.SaveTraceCommand.Execute(null);
        var manual = vm.Subjects.SelectMany(s => s.Corrections).Where(c => c.Model.Op == "remodeler").ToList();
        Assert.Single(manual);
        Assert.Equal("SEU", manual[0].Model.To);

        vm.OpenCreateSurfaceCommand.Execute(null);
        Plan.Rectangle(vm.Trace!, 0, 0, 2, 3);
        vm.SaveTraceCommand.Execute(null);
        var created = vm.SelectedCorrection!;
        vm.SelectSurface(SceneController.PreviewPrefix + created.Id);
        Assert.Equal(("SUS", "ERR", "N00"), (vm.SelectedSurface!.Surface.DisplayCode, vm.SelectedSurface.Surface.Building, vm.SelectedSurface.Surface.Level));
        await vm.DeleteSelectedSurfaceCommand.ExecuteAsync(null);         // supprimer une création : elle est rejetée
        Assert.Equal(CorrectionDecision.Rejected, created.Decision);
    }
}

public class RightAngleSnapTests
{
    private static TraceSession Session()
    {
        var sus = Plan.Square("sus", "SUS", 0, 0, 10, 5);
        return new TraceSession(sus, [sus], [], "SUS", null, 0, 0, new Tolerance { AbsM2 = 0.5, Rel = 0.005 }, TraceKind.Reshape);
    }

    [Fact]
    public void Snaps_lightly_to_a_square_corner_and_marks_it()
    {
        var s = Session();
        var r = s.SnapRightAngle(new Point(0.05, 5), [(new Point(0, 0), new Point(10, 0))], 0.1);
        Assert.NotNull(r);
        Assert.Equal(new Point(0, 5), r!.Value.At);
        Assert.Equal(new Point(0, 0), r.Value.Marks.Single().Corner);
        Assert.Null(s.SnapRightAngle(new Point(0.5, 5), [(new Point(0, 0), new Point(10, 0))], 0.1));   // léger : hors tolérance, libre
        s.SnapToRightAngles = false;
        Assert.Null(s.SnapRightAngle(new Point(0.05, 5), [(new Point(0, 0), new Point(10, 0))], 0.1));
    }

    [Fact]
    public void Dragged_corner_lands_on_both_right_angles()
    {
        var s = Session();
        // Sommet (10, 5) glissé : voisins (10, 0) et (0, 5), eux-mêmes voisins de (0, 0).
        var r = s.SnapRightAngle(new Point(10.05, 5.04), [(new Point(10, 0), new Point(0, 0)), (new Point(0, 5), new Point(0, 0))], 0.1,
                                 (new Point(10, 0), new Point(0, 5)));
        Assert.Equal(new Point(10, 5), r!.Value.At);
        Assert.Equal(3, r.Value.Marks.Count);                            // aux deux voisins et au sommet lui-même
    }
}

public class BalanceScopeTests
{
    [Fact]
    public void All_buildings_shows_one_row_per_building_and_project_ratios()
    {
        using var tmp = new TempDir();
        var vm = SubjectFixture.Loaded(tmp);
        Assert.Equal(Ratio.AllBuildings, vm.BalanceChoices[0].Value);    // plusieurs bâtiments : « Tous » en tête
        vm.BalanceBuilding = Ratio.AllBuildings;
        Assert.Equal("Tous les bâtiments", vm.BalanceScopeLabel);
        Assert.Equal(vm.Buildings.Select(b => b.Name).OrderDescending(), vm.BalanceRows.Select(r => r.Level));
        var err = vm.BalanceRows.Single(r => r.Building == "ERR");
        Assert.Equal(vm.Document!.Levels.Where(l => l.Building == "ERR").Sum(l => l.Value("SP")), err.Sp, 3);
        Assert.All(vm.RatioRows, r => Assert.Null(r.Building));
    }
}

public class DuplicateAndCloseTests
{
    [Fact]
    public void Level_totals_doubled_by_their_pieces_are_not_shown()
    {
        var total = Plan.Square("sus-total", "SUS", 0, 0, 10, 4, kind: "node");
        var piece = Plan.Square("sus-1", "SUS", 0, 0, 10, 4);
        var sp = Plan.Square("sp", "SP", 0, 0, 20, 10, kind: "node");
        var doc = new ViewerDocument { Surfaces = [total, piece, sp] };
        Assert.Equal(["sus-total"], doc.RedundantTotals);                 // le SP n'a pas de pièces : gardé
        var scene = new SceneController(doc, new SiaPalette(doc.Categories), System.Windows.Media.Colors.Gray);
        Assert.Equal(["sus-1", "sp"], scene.SurfacesOfLevel("A", "N00").Order(StringComparer.Ordinal).Reverse());
    }

    [Fact]
    public void Nc_is_offered_when_modifying_and_classifying()
    {
        Assert.Contains("NC", MainViewModel.SurfaceTypes);
        using var tmp = new TempDir();
        var vm = SubjectFixture.Loaded(tmp);
        var c = vm.Subjects.Single(s => s.Id == "S1").Corrections.Single(x => x.Id == "abords-ERR-N00");
        Assert.Contains(c.Destinations, d => d.Value == "NC");
        c.Destination = "NC";
        Assert.Equal(("découper", "NC"), (c.Model.Op, c.Model.To));
    }

    [Fact]
    public void Subject_card_closes()
    {
        using var tmp = new TempDir();
        var vm = SubjectFixture.Loaded(tmp);
        vm.SelectedSubject = vm.Subjects[0];
        vm.CloseSubjectCommand.Execute(null);
        Assert.False(vm.HasSelectedSubject);
    }
}

public class SaLayerTests
{
    [Fact]
    public void Sa_layer_is_always_listed_in_its_sia_color()
    {
        using var tmp = new TempDir();
        var vm = SubjectFixture.Loaded(tmp);
        var sa = vm.Layers.Single(l => l.Code == "SA");
        Assert.Equal("Extérieur", sa.Group);
        Assert.True(sa.IsVisible);
        Assert.Equal(System.Windows.Media.Color.FromRgb(0x5B, 0xA8, 0x45), vm.Palette!.ColorOf("SA"));
        Assert.Contains("abords", sa.Title);
    }
}
