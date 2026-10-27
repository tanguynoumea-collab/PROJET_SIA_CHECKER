using System.Globalization;
using System.Text.Json;
using System.Windows;
using Clipper2Lib;
using CommunityToolkit.Mvvm.ComponentModel;
using LibTessDotNet;
using SiaCheck.Viewer.Models;

namespace SiaCheck.Viewer.ViewModels;

/// <summary>Tracer un contour, le modifier, ou scinder la surface par une ligne (emprise d'une surface seulement).</summary>
public enum TraceMode { Draw, Edit, Split }

/// <summary>
/// Usage du module : découper une part d'une surface (correction « découper » / exclusion partielle), redessiner
/// l'emprise d'une surface (« remodeler », type compris), ou créer une surface sur un niveau (« créer »).
/// </summary>
public enum TraceKind { Cut, Reshape, Create }

/// <summary>Élément du tracé sélectionné en mode Modifier : un sommet, ou l'arête qui part de ce sommet.</summary>
public readonly record struct TraceSelection(int Polygon, int Index, bool IsEdge);

/// <summary>Angle droit trouvé par l'accrochage : au sommet <see cref="Corner"/>, entre les directions U et V (unitaires).</summary>
public readonly record struct RightAngleMark(Point Corner, Vector U, Vector V);

/// <summary>Surface du niveau dessinée dans le plan : contours (union des triangles du maillage, en mètres).</summary>
public sealed record PlanShape(string Id, string Code, PathsD Paths, bool IsSource, bool IsBelow);

/// <summary>
/// Session du module de tracé (plan, Évolution 2.1) : polygones dessinés sur le plan d'un niveau, aire comptée en
/// direct, annuler / rétablir, accrochage, aperçu de l'écart R3, puis la correction à enregistrer.
///
/// Aire comptée = (polygones ∩ surface source) − SEU / SED / SEI du niveau quand la source est une SEP : la règle
/// des tracés pré-calculés (sujets.py) et de la vérification du moteur (corrections._traced_area).
/// Calcul en direct avec Clipper2, à 1 mm près ; le moteur refait le calcul avec shapely à l'application.
/// </summary>
public sealed partial class TraceSession : ObservableObject
{
    public static readonly string[] ClassifiedExternal = ["SEU", "SED", "SEI"];
    private const int Precision = 3;                   // décimales (m) des opérations Clipper2
    private const int MaxUndo = 50;
    private static readonly NumberFormatInfo Format = new() { NumberGroupSeparator = " ", NumberDecimalSeparator = "," };

    private readonly PathsD _source;
    private readonly PathsD _classified;
    private readonly double _sepArea;
    private readonly double _r3Now;
    private readonly double _appliedArea;
    private readonly Tolerance _tolerance;
    /// <summary>État annulable : polygones et polygone en cours de dessin.</summary>
    private sealed record Snapshot(List<List<Point>> Polygons, bool Open);
    private readonly Stack<Snapshot> _undo = new();
    private readonly Stack<Snapshot> _redo = new();
    private List<List<Point>> _polygons = [];
    private readonly List<Point> _snapVertices = [];
    private readonly List<(Point A, Point B)> _snapEdges = [];

    /// <param name="source">Surface à découper (ou à exclure en partie), à redessiner, ou, pour une création, surface
    /// fictive qui porte le bâtiment, le niveau et le type de la nouvelle surface.</param>
    /// <param name="level">Surfaces du niveau (avec maillage), source comprise.</param>
    /// <param name="below">Surfaces du niveau inférieur : leur emprise sert de repère et d'accroche.</param>
    /// <param name="existing">Correction déjà tracée (pré-calcul du moteur ou tracé manuel), sinon null.</param>
    /// <param name="r3Now">Écart R3 actuel du niveau (bilan).</param>
    /// <param name="appliedArea">Aire de cette correction déjà appliquée par la dernière analyse (0 sinon).</param>
    public TraceSession(Surface source, IEnumerable<Surface> level, IEnumerable<Surface> below, string target,
                        Correction? existing, double r3Now, double appliedArea, Tolerance tolerance,
                        TraceKind kind = TraceKind.Cut, IReadOnlyList<IReadOnlyList<Point>>? initial = null,
                        IReadOnlyList<Surface>? siblings = null)
    {
        Kind = kind;
        // Îlot d'une surface en plusieurs morceaux : les autres îlots gardent leur emprise dans la correction.
        _siblings = (siblings ?? []).SelectMany(s => OuterRings(Outline(s))).Select(r => r.Select(ToPoint).ToList()).ToList();
        Source = source;
        _target = target;
        _openedTarget = target;
        Existing = existing;
        _r3Now = r3Now;
        _appliedArea = appliedArea;
        _tolerance = tolerance;
        var shapes = new List<PlanShape>();
        // La source est toujours dessinée, même absente des surfaces du niveau (surface à îlots, montrée par ses îlots).
        foreach (var s in level.Where(s => s.Id != source.Id).Prepend(source).Where(s => s.Mesh is not null && (!s.IsExcluded || s.Id == source.Id)))
            if (Outline(s) is { Count: > 0 } p) shapes.Add(new PlanShape(s.Id, s.DisplayCode, p, s.Id == source.Id, false));
        var belowPaths = new PathsD();
        foreach (var s in below.Where(s => s.Mesh is not null && s.DisplayCode == "SP"))
            if (Outline(s) is { Count: > 0 } p) belowPaths.AddRange(p);
        BelowOutline = belowPaths.Count > 0 ? Clipper.Union(belowPaths, FillRule.NonZero) : [];
        Shapes = shapes;
        _source = shapes.FirstOrDefault(s => s.IsSource)?.Paths ?? [];
        var classified = new PathsD();
        if (source.DisplayCode == "SEP")
            foreach (var s in shapes.Where(s => ClassifiedExternal.Contains(s.Code))) classified.AddRange(s.Paths);
        _classified = classified.Count > 0 ? Clipper.Union(classified, FillRule.NonZero) : [];
        _sepArea = source.Area ?? Clipper.Area(_source);
        foreach (var paths in shapes.Select(s => s.Paths).Append(BelowOutline))
            foreach (var path in paths)
                for (var i = 0; i < path.Count; i++)
                {
                    var a = ToPoint(path[i]);
                    _snapVertices.Add(a);
                    _snapEdges.Add((a, ToPoint(path[(i + 1) % path.Count])));
                }
        if (initial is not null)   // contour repris d'un autre niveau (nouvelle surface) : à enregistrer tel quel
        {
            _polygons = initial.Where(p => p.Count >= 3).Select(p => p.ToList()).ToList();
            _isDirty = _polygons.Count > 0;
        }
        else if (existing is not null) _polygons = ReadPolygons(existing);
        else if (kind == TraceKind.Reshape)   // l'emprise actuelle, prête à modifier (contours extérieurs)
            _polygons = OuterRings(_source).Select(path => path.Select(ToPoint).ToList()).Where(p => p.Count >= 3).ToList();
        _z = kind == TraceKind.Create ? LevelZ(level) : TopZ(source);
        _mode = _polygons.Count > 0 ? TraceMode.Edit : TraceMode.Draw;
        Recompute();
    }

    private readonly double _z;
    private readonly List<List<Point>> _siblings;
    /// <summary>Type à l'ouverture : celui de la correction reprise, sinon de la surface. Le changer est une modification.</summary>
    private readonly string _openedTarget;

    /// <summary>Surface visée par la correction : la surface d'origine d'un îlot, sinon la source elle-même.</summary>
    public string TargetSurfaceId => Source.IslandOf ?? Source.Id;
    public bool IsIsland => Source.IslandOf is not null;

    public TraceKind Kind { get; }
    public bool IsCut => Kind == TraceKind.Cut;
    public bool IsReshape => Kind == TraceKind.Reshape;
    public bool IsCreate => Kind == TraceKind.Create;
    public Surface Source { get; }

    /// <summary>Catégorie visée : de la part découpée (« » = exclue), de la surface redessinée ou créée.</summary>
    [ObservableProperty] [NotifyPropertyChangedFor(nameof(Title), nameof(CanSave))] private string _target;
    public Correction? Existing { get; }
    public bool HasGeometry => _source.Count > 0;
    public IReadOnlyList<PlanShape> Shapes { get; }
    public PathsD BelowOutline { get; }
    /// <summary>Polygones du tracé ; le dernier est ouvert tant qu'on dessine (<see cref="IsDrawingOpen"/>).</summary>
    public IReadOnlyList<IReadOnlyList<Point>> Polygons => _polygons;
    public PathsD Counted { get; private set; } = [];
    /// <summary>Bornes du niveau (m), pour cadrer le plan.</summary>
    public Rect Bounds
    {
        get
        {
            var r = Rect.Empty;
            foreach (var p in Shapes.SelectMany(s => s.Paths).Concat(BelowOutline).SelectMany(p => p)) r.Union(new Point(p.x, p.y));
            return r;
        }
    }

    public string Title => Kind switch
    {
        TraceKind.Create => $"{Source.Building}·{Source.Level} · nouvelle {Target}",
        TraceKind.Reshape => $"{Source.Building}·{Source.Level} · {Source.DisplayCode}{(Target != Source.DisplayCode ? " → " + Target : "")} · emprise",
        _ => $"{Source.Building}·{Source.Level} · {Source.DisplayCode} → {(Target == "" ? "exclue" : Target)}",
    };

    [ObservableProperty] [NotifyPropertyChangedFor(nameof(IsDrawMode), nameof(IsEditMode), nameof(IsSplitMode), nameof(Help), nameof(CanSave))]
    private TraceMode _mode;
    public bool IsDrawMode { get => Mode == TraceMode.Draw; set { if (value) Mode = TraceMode.Draw; } }
    public bool IsEditMode { get => Mode == TraceMode.Edit; set { if (value) Mode = TraceMode.Edit; } }
    public bool IsSplitMode { get => Mode == TraceMode.Split; set { if (value) Mode = TraceMode.Split; } }
    [ObservableProperty] private bool _snapToVertices = true;
    [ObservableProperty] private bool _snapToEdges = true;
    /// <summary>Accrochage léger aux angles droits avec les arêtes voisines du tracé (repère ⦜ à l'angle).</summary>
    [ObservableProperty] private bool _snapToRightAngles = true;
    /// <summary>Les autres surfaces du niveau en transparence (contour seul), pour voir le tracé et la source.</summary>
    [ObservableProperty] private bool _fadeOthers;
    /// <summary>Le dernier polygone est en cours de dessin (pas encore fermé).</summary>
    [ObservableProperty] private bool _isDrawingOpen;
    [ObservableProperty] private bool _isDirty;

    public string Help => Mode == TraceMode.Split
        ? "Clic : poser un point de la ligne de coupe, qui traverse la surface de part en part · Entrée ou double-clic : couper · ⌫ : retirer le dernier point · Échap : effacer la ligne · Alt : sans accrochage"
        : Mode == TraceMode.Draw
        ? "Clic : ajouter un point · clic sur le premier point, Entrée ou double-clic : fermer · ⌫ : retirer le dernier point · Maj : horizontal / vertical · Alt : sans accrochage · Échap : annuler le point en cours"
        : "Clic : sélectionner un sommet ou une arête, glisser pour la déplacer · glisser l'intérieur : tout le contour · double-clic sur une arête : ajouter un sommet · Suppr : retirer le sommet, ou l'arête (le contour s'ouvre : complétez-le en mode Tracer) · flèches : 0,10 m (Maj : 1 m) · Ctrl+Z / Ctrl+Y";

    // ------------------------------------------------------------------ chiffres

    public double CountedArea { get; private set; }
    public double OnSource { get; private set; }
    public double RemovedClassified { get; private set; }
    public double Outside { get; private set; }
    public double SourceArea => Clipper.Area(_source);
    public bool IsSelfIntersecting { get; private set; }
    public double R3Before => _r3Now;
    public double R3After => _r3Now + _appliedArea - CountedArea;
    public string R3Verdict => Math.Abs(R3After) <= _tolerance.AbsM2 || (_sepArea > 0 && Math.Abs(R3After) / _sepArea <= _tolerance.Rel) ? "OK" : "ERREUR";

    public string CountedText => Area(CountedArea);
    public string OnSourceText => Area(OnSource);
    public string RemovedText => Area(RemovedClassified);
    public string OutsideText => Area(Outside);
    public string R3BeforeText => Area(R3Before);
    public string R3AfterText => Area(R3After);
    public string SourceLabel => $"sur la {Source.DisplayCode}";
    /// <summary>Emprise redessinée : aire de la surface avant modification, et l'écart.</summary>
    public string OriginalAreaText => Area(Source.Area ?? SourceArea);
    public string AreaDeltaText => (CountedArea - (Source.Area ?? SourceArea)).ToString("+#,##0.00;−#,##0.00;0,00", Format) + " m²";
    public string OutsideLabel => $"hors de la {Source.DisplayCode}";
    public bool HasClassified => _classified.Count > 0;

    public string? Message =>
        IsSelfIntersecting ? "Le contour se recoupe : déplacez un sommet."
        : IsDrawingOpen && !IsCut && _polygons.Count > 0 ? "Contour ouvert : complétez-le en mode Tracer, puis fermez-le (clic sur le premier point ou Entrée)."
        : !IsCut ? null
        : ClosedPolygons().Any() && CountedArea <= 0.005 ? $"Le tracé ne recouvre pas la {Source.DisplayCode} du niveau."
        : CountedArea > 0 && SourceArea > 0 && CountedArea >= SourceArea - Math.Max(0.5, 0.005 * SourceArea)
            ? "Le tracé couvre toute la surface : une exclusion ou un reclassement entier serait plus simple."
        : Existing?.NeedsRetrace == true && !IsDirty ? "L'aire a été modifiée à la main depuis ce tracé."
        : null;
    public bool HasMessage => Message is not null;
    public bool MessageIsError => IsSelfIntersecting || IsCut && ClosedPolygons().Any() && CountedArea <= 0.005;

    /// <summary>
    /// Emprise redessinée : un changement de type seul suffit à enregistrer ; en mode Scinder, une coupe faite. Le type se
    /// compare à celui de l'ouverture (correction reprise), pas au type d'origine de la surface : une part passée de SA à
    /// SC peut revenir à SA.
    /// </summary>
    public bool CanSave => IsSplitMode ? HasSplit
        : IsDirty || Existing?.NeedsRetrace == true || IsReshape && Target != _openedTarget
            ? !IsDrawingOpen && !IsSelfIntersecting && CountedArea > 0.005 : false;

    // ------------------------------------------------------------------ scinder

    private readonly List<Point> _splitLine = [];
    /// <summary>Ligne de coupe en cours (mode Scinder).</summary>
    public IReadOnlyList<Point> SplitLine => _splitLine;
    /// <summary>Les deux parties de la surface après la coupe ; vides tant que la ligne n'est pas validée.</summary>
    public PathsD SplitPartA { get; private set; } = [];
    public PathsD SplitPartB { get; private set; } = [];
    public bool HasSplit => SplitPartA.Count > 0 && SplitPartB.Count > 0;
    public bool IsSplitDone => HasSplit;
    public string SplitAreaAText => Area(Math.Abs(Clipper.Area(SplitPartA)));
    public string SplitAreaBText => Area(Math.Abs(Clipper.Area(SplitPartB)));
    /// <summary>Type de chaque partie : celui de la surface d'origine par défaut.</summary>
    [ObservableProperty] private string _splitTypeA = "";
    [ObservableProperty] private string _splitTypeB = "";
    public string? SplitMessage { get; private set; }

    public void AddSplitPoint(Point p)
    {
        if (HasSplit) ClearSplit();
        _splitLine.Add(p);
        OnPropertyChanged(string.Empty);
    }

    public void RemoveLastSplitPoint()
    {
        if (HasSplit) { SplitPartA = SplitPartB = []; }
        if (_splitLine.Count > 0) _splitLine.RemoveAt(_splitLine.Count - 1);
        OnPropertyChanged(string.Empty);
    }

    /// <summary>Échap : efface la ligne et la coupe ; false s'il n'y avait rien.</summary>
    public bool ClearSplit()
    {
        if (_splitLine.Count == 0 && !HasSplit) return false;
        _splitLine.Clear();
        SplitPartA = SplitPartB = [];
        SplitMessage = null;
        OnPropertyChanged(string.Empty);
        return true;
    }

    /// <summary>
    /// Entrée ou double-clic : coupe la surface par la ligne. Les extrémités sont prolongées bien au-delà du niveau, et
    /// un grand détour d'un côté ferme un demi-plan : partie 1 = surface ∩ ce côté, partie 2 = le reste.
    /// </summary>
    public bool FinishSplit()
    {
        var line = _splitLine.ToList();
        if (line.Count >= 2 && (line[^1] - line[^2]).Length < 1e-6) line.RemoveAt(line.Count - 1);   // double-clic
        SplitPartA = SplitPartB = [];
        SplitMessage = null;
        if (line.Count < 2 || _source.Count == 0)
        {
            SplitMessage = "Posez au moins deux points : la ligne doit traverser la surface.";
            OnPropertyChanged(string.Empty);
            return false;
        }
        var side = SideOf(line, Bounds);
        var a = Clipper.Intersect(_source, side, FillRule.NonZero, Precision);
        var b = Clipper.Difference(_source, side, FillRule.NonZero, Precision);
        if (Math.Abs(Clipper.Area(a)) < 0.01 || Math.Abs(Clipper.Area(b)) < 0.01)
        {
            SplitMessage = "La ligne ne coupe pas la surface en deux : prolongez-la de part en part.";
            OnPropertyChanged(string.Empty);
            return false;
        }
        // Partie 1 : la plus grande, elle garde la surface d'origine.
        (SplitPartA, SplitPartB) = Math.Abs(Clipper.Area(a)) >= Math.Abs(Clipper.Area(b)) ? (a, b) : (b, a);
        if (SplitTypeA == "") SplitTypeA = Source.DisplayCode;
        if (SplitTypeB == "") SplitTypeB = Source.DisplayCode;
        OnPropertyChanged(string.Empty);
        return true;
    }

    private static PathsD SideOf(List<Point> line, Rect bounds)
    {
        var size = Math.Max(Math.Max(bounds.Width, bounds.Height), 1) * 4;
        var c = new Point(bounds.X + bounds.Width / 2, bounds.Y + bounds.Height / 2);
        Point Extend(Point from, Point to) { var d = to - from; d.Normalize(); return to + d * size; }
        var start = Extend(line[1], line[0]);
        var end = Extend(line[^2], line[^1]);
        // Détour par un grand cercle autour du niveau, de la fin de la ligne à son début, toujours du même côté.
        double Angle(Point p) => Math.Atan2(p.Y - c.Y, p.X - c.X);
        var a0 = Angle(end);
        var a1 = Angle(start);
        if (a1 <= a0) a1 += 2 * Math.PI;
        var ring = new List<Point> { start };
        ring.AddRange(line);
        ring.Add(end);
        for (var t = 1; t < 32; t++)
        {
            var ang = a0 + (a1 - a0) * t / 32;
            ring.Add(new Point(c.X + Math.Cos(ang) * size * 3, c.Y + Math.Sin(ang) * size * 3));
        }
        return Clipper.Union(new PathsD([new PathD(ring.Select(p => new PointD(p.X, p.Y)))]), FillRule.NonZero);
    }

    /// <summary>
    /// Corrections de la coupe : la partie 2 est découpée de la surface d'origine (même catégorie ou celle choisie, mêmes
    /// métadonnées) ; la partie 1 reste la surface d'origine, découpée elle aussi si son type change.
    /// </summary>
    public IReadOnlyList<Correction> BuildSplitCorrections(string idStem, string? subject)
    {
        var parts = new List<(int N, PathsD Paths, string Type)> { (2, SplitPartB, SplitTypeB) };
        if (SplitTypeA != Source.DisplayCode) parts.Add((1, SplitPartA, SplitTypeA));
        return parts.Select(p =>
        {
            var area = Math.Round(Math.Abs(Clipper.Area(p.Paths)), 2);
            return new Correction
            {
                Id = $"{idStem}-{p.N}", Op = "découper", To = p.Type, Subject = subject, Status = Correction.Proposed, Origin = "manuel",
                Target = JsonSerializer.SerializeToElement(new { ids = new[] { TargetSurfaceId } }),
                Area = area, M2 = area, Trace = Triangulate(p.Paths, _z),
                Extra = new() { ["polygone"] = MultiPolygon(OuterRings(p.Paths).Select(r => r.Select(ToPoint).ToList())) },
                Explanation = $"{Source.Building} {Source.Level} : {Source.DisplayCode} scindée, partie {p.N} ({Area(area)})" +
                              (p.Type != Source.DisplayCode ? $" classée {p.Type}." : ", nouvelle surface de même type."),
            };
        }).ToList();
    }

    private static string Area(double v) => v.ToString("#,##0.00", Format) + " m²";

    private IEnumerable<List<Point>> ClosedPolygons() =>
        _polygons.Where((p, i) => p.Count >= 3 && !(IsDrawingOpen && i == _polygons.Count - 1));

    private void Recompute()
    {
        var drawn = new PathsD(ClosedPolygons().Select(ToPath));
        var union = drawn.Count > 0 ? Clipper.Union(drawn, FillRule.NonZero) : [];
        if (!IsCut)   // emprise ou nouvelle surface : l'aire est celle du contour dessiné
        {
            Counted = union;
            OnSource = CountedArea = Math.Abs(Clipper.Area(union));
            RemovedClassified = Outside = 0;
            IsSelfIntersecting = ClosedPolygons().Any(SelfIntersects);
            OnPropertyChanged(string.Empty);
            return;
        }
        var onSource = union.Count > 0 && _source.Count > 0 ? Clipper.Intersect(union, _source, FillRule.NonZero, Precision) : [];
        Counted = onSource.Count > 0 && _classified.Count > 0 ? Clipper.Difference(onSource, _classified, FillRule.NonZero, Precision) : onSource;
        OnSource = Math.Abs(Clipper.Area(onSource));
        CountedArea = Math.Abs(Clipper.Area(Counted));
        RemovedClassified = Math.Max(0, OnSource - CountedArea);
        Outside = Math.Max(0, Math.Abs(Clipper.Area(union)) - OnSource);
        IsSelfIntersecting = ClosedPolygons().Any(SelfIntersects);
        OnPropertyChanged(string.Empty);
    }

    // ------------------------------------------------------------------ édition (une étape d'annulation par geste)

    /// <summary>À appeler avant un geste qui modifie le tracé (clic, début de glisser, suppression).</summary>
    public void BeginChange()
    {
        _undo.Push(Take());
        if (_undo.Count > MaxUndo) { var keep = _undo.Take(MaxUndo).Reverse().ToList(); _undo.Clear(); foreach (var k in keep) _undo.Push(k); }
        _redo.Clear();
        IsDirty = true;
    }

    public void AddPoint(Point p)
    {
        BeginChange();
        if (!IsDrawingOpen) { _polygons.Add([]); IsDrawingOpen = true; }
        _polygons[^1].Add(p);
        Recompute();
    }

    /// <summary>Entrée ou double-clic : ferme le polygone en cours (au moins 3 points) et passe en Modifier.</summary>
    public bool ClosePolygon()
    {
        if (!IsDrawingOpen) return false;
        var last = _polygons[^1];
        if (last.Count >= 2 && (last[^1] - last[^2]).Length < 1e-6) last.RemoveAt(last.Count - 1);   // double-clic
        if (last.Count < 3) return false;
        IsDrawingOpen = false;
        Mode = TraceMode.Edit;
        Recompute();
        return true;
    }

    /// <summary>⌫ en mode Tracer : retire le dernier point du polygone en cours.</summary>
    public void RemoveLastPoint()
    {
        if (!IsDrawingOpen) return;
        BeginChange();
        _polygons[^1].RemoveAt(_polygons[^1].Count - 1);
        if (_polygons[^1].Count == 0) { _polygons.RemoveAt(_polygons.Count - 1); IsDrawingOpen = false; }
        Recompute();
    }

    /// <summary>Échap en mode Tracer : abandonne le polygone en cours ; renvoie false s'il n'y en avait pas.</summary>
    public bool CancelOpenPolygon()
    {
        if (!IsDrawingOpen) return false;
        BeginChange();
        _polygons.RemoveAt(_polygons.Count - 1);
        IsDrawingOpen = false;
        Recompute();
        return true;
    }

    /// <summary>Déplacement en cours de glisser : sans étape d'annulation (BeginChange au début du geste).</summary>
    public void MoveVertex(int polygon, int index, Point p)
    {
        _polygons[polygon][index] = p;
        Recompute();
    }

    public void MovePolygon(int polygon, Vector delta)
    {
        var poly = _polygons[polygon];
        for (var i = 0; i < poly.Count; i++) poly[i] += delta;
        Recompute();
    }

    /// <summary>Glisser ou flèches sur une arête : ses deux sommets bougent ensemble (sans étape d'annulation).</summary>
    public void MoveEdge(int polygon, int index, Vector delta)
    {
        var poly = _polygons[polygon];
        poly[index] += delta;
        poly[(index + 1) % poly.Count] += delta;
        Recompute();
    }

    /// <summary>
    /// Supprime une arête : le contour s'ouvre à cet endroit et devient le tracé en cours (mode Tracer), à compléter
    /// puis refermer. Il reprend au sommet qui suit l'arête et finit sur celui qui la précède. Refusé tant qu'un
    /// autre contour est en cours de dessin.
    /// </summary>
    public bool DeleteEdge(int polygon, int index)
    {
        if (IsDrawingOpen) return false;
        BeginChange();
        var poly = _polygons[polygon];
        var n = poly.Count;
        var open = Enumerable.Range(1, n).Select(k => poly[(index + k) % n]).ToList();
        _polygons.RemoveAt(polygon);
        _polygons.Add(open);
        IsDrawingOpen = true;
        Mode = TraceMode.Draw;
        Recompute();
        return true;
    }

    /// <summary>Clic sur le premier point du contour en cours : il se ferme (au moins 3 points).</summary>
    public bool IsFirstPoint(Point p, double radius) =>
        IsDrawingOpen && _polygons[^1].Count >= 3 && (_polygons[^1][0] - p).Length <= radius;

    public void InsertVertex(int polygon, int afterIndex, Point p)
    {
        BeginChange();
        _polygons[polygon].Insert(afterIndex + 1, p);
        Recompute();
    }

    /// <summary>Supprime un sommet ; un polygone sous 3 sommets disparaît.</summary>
    public void DeleteVertex(int polygon, int index)
    {
        BeginChange();
        _polygons[polygon].RemoveAt(index);
        if (_polygons[polygon].Count < 3) _polygons.RemoveAt(polygon);
        Recompute();
    }

    public void Clear()
    {
        if (_polygons.Count == 0) return;
        BeginChange();
        _polygons.Clear();
        IsDrawingOpen = false;
        Mode = TraceMode.Draw;
        Recompute();
    }

    public bool CanUndo => _undo.Count > 0;
    public bool CanRedo => _redo.Count > 0;

    public void Undo()
    {
        if (_undo.Count == 0) return;
        _redo.Push(Take());
        Restore(_undo.Pop());
        IsDirty = true;
    }

    public void Redo()
    {
        if (_redo.Count == 0) return;
        _undo.Push(Take());
        Restore(_redo.Pop());
    }

    private Snapshot Take() => new(Copy(_polygons), IsDrawingOpen);

    private void Restore(Snapshot s)
    {
        _polygons = s.Polygons;
        IsDrawingOpen = s.Open && _polygons.Count > 0;
        if (IsDrawingOpen) Mode = TraceMode.Draw;
        Recompute();
    }

    // ------------------------------------------------------------------ accrochage et test d'impact

    /// <summary>Point d'accrochage le plus proche dans <paramref name="radius"/> (m) : sommets d'abord, puis arêtes.</summary>
    public Point? Snap(Point p, double radius) => SnapToVertex(p, radius) ?? SnapToEdge(p, radius)?.At;

    /// <summary>Sommet des surfaces (ou de l'emprise du niveau inférieur) le plus proche, dans le rayon.</summary>
    public Point? SnapToVertex(Point p, double radius)
    {
        if (!SnapToVertices) return null;
        Point? best = null;
        var d = radius;
        foreach (var v in _snapVertices)
            if ((v - p).Length is var l && l <= d) { d = l; best = v; }
        return best;
    }

    /// <summary>Point le plus proche sur une arête des surfaces, avec l'arête elle-même.</summary>
    public (Point At, Point A, Point B)? SnapToEdge(Point p, double radius)
    {
        if (!SnapToEdges) return null;
        (Point, Point, Point)? best = null;
        var d = radius;
        foreach (var (a, b) in _snapEdges)
            if (Project(p, a, b) is var q && (q - p).Length is var l && l <= d) { d = l; best = (q, a, b); }
        return best;
    }

    /// <summary>
    /// Accrochage léger aux angles droits : <paramref name="anchors"/> (sommet c, voisin o) donne la droite passant par c
    /// perpendiculaire à (o − c), sur laquelle le point fait un angle droit en c. Le point est ramené sur la droite la
    /// plus proche (ou à l'intersection de deux droites) s'il en est à moins de <paramref name="tolerance"/> (m).
    /// <paramref name="corner"/> : sommet déplacé, entre ses deux voisins, pour signaler un angle droit à cet endroit.
    /// </summary>
    public (Point At, IReadOnlyList<RightAngleMark> Marks)? SnapRightAngle(Point p, IReadOnlyList<(Point Corner, Point Other)> anchors,
                                                                           double tolerance, (Point Prev, Point Next)? corner = null)
    {
        if (!SnapToRightAngles) return null;
        var lines = new List<(Point C, Vector Dir, Vector Edge, double D)>();
        foreach (var (c, o) in anchors)
        {
            var edge = o - c;
            if (edge.LengthSquared < 1e-9 || (p - c).Length < 1e-6) continue;
            edge.Normalize();
            var dir = new Vector(-edge.Y, edge.X);
            var q = c + dir * Vector.Multiply(p - c, dir);
            var d = (q - p).Length;
            if (d <= tolerance) lines.Add((c, dir, edge, d));
        }
        Point at;
        List<RightAngleMark> marks = [];
        if (lines.Count >= 2 && Intersect(lines[0].C, lines[0].Dir, lines[1].C, lines[1].Dir) is { } x && (x - p).Length <= tolerance * 1.5)
        {
            at = x;
            marks.AddRange(lines.Take(2).Select(l => Mark(l.C, l.Edge, at)));
        }
        else if (lines.Count > 0)
        {
            var l = lines.MinBy(l => l.D);
            at = l.C + l.Dir * Vector.Multiply(p - l.C, l.Dir);
            marks.Add(Mark(l.C, l.Edge, at));
        }
        else at = p;
        if (corner is { } k && (k.Prev - at).Length > 1e-6 && (k.Next - at).Length > 1e-6)
        {
            var u = k.Prev - at; u.Normalize();
            var v = k.Next - at; v.Normalize();
            if (Math.Abs(Vector.Multiply(u, v)) < Math.Sin(Math.PI / 180)) marks.Add(new RightAngleMark(at, u, v));   // ±1°
        }
        return marks.Count == 0 ? null : (at, marks);

        static RightAngleMark Mark(Point c, Vector edge, Point at)
        {
            var w = at - c;
            w.Normalize();
            return new RightAngleMark(c, edge, w);
        }
    }

    private static Point? Intersect(Point a, Vector u, Point b, Vector v)
    {
        var den = u.X * v.Y - u.Y * v.X;
        if (Math.Abs(den) < 1e-9) return null;
        var t = ((b.X - a.X) * v.Y - (b.Y - a.Y) * v.X) / den;
        return a + u * t;
    }

    /// <summary>Sommet du tracé sous le point (rayon en m) : (polygone, indice), sinon null.</summary>
    public (int Polygon, int Index)? VertexAt(Point p, double radius)
    {
        for (var k = 0; k < _polygons.Count; k++)
            for (var i = 0; i < _polygons[k].Count; i++)
                if ((_polygons[k][i] - p).Length <= radius) return (k, i);
        return null;
    }

    /// <summary>Arête du tracé sous le point : (polygone, indice du premier sommet, point projeté), sinon null.</summary>
    public (int Polygon, int Index, Point At)? EdgeAt(Point p, double radius)
    {
        for (var k = 0; k < _polygons.Count; k++)
        {
            var poly = _polygons[k];
            for (var i = 0; i < poly.Count; i++)
            {
                var q = Project(p, poly[i], poly[(i + 1) % poly.Count]);
                if ((q - p).Length <= radius) return (k, i, q);
            }
        }
        return null;
    }

    /// <summary>Polygone fermé qui contient le point (pour le déplacer en entier).</summary>
    public int? PolygonAt(Point p)
    {
        for (var k = _polygons.Count - 1; k >= 0; k--)
            if (_polygons[k].Count >= 3 && !(IsDrawingOpen && k == _polygons.Count - 1) &&
                Clipper.PointInPolygon(new PointD(p.X, p.Y), ToPath(_polygons[k])) != PointInPolygonResult.IsOutside)
                return k;
        return null;
    }

    // ------------------------------------------------------------------ enregistrement

    /// <summary>
    /// Correction enregistrée : la proposition (ou une nouvelle découpe) avec le tracé dessiné (`polygone`), l'aire
    /// comptée, la triangulation pour la 3D, origine « manuel » ; la proposition d'origine reste dans `base`.
    /// </summary>
    public Correction BuildCorrection(string newId, string? subject)
    {
        // Îlot d'une surface en plusieurs morceaux, dont le type change : la part passe à ce type (découpe de la surface
        // d'origine) ; même type : la surface d'origine est redessinée, les autres îlots gardés tels quels.
        var islandRetype = IsIsland && Kind == TraceKind.Reshape && Target != Source.DisplayCode;
        var keepSiblings = IsIsland && Kind == TraceKind.Reshape && !islandRetype;
        var c = Existing?.Clone() ?? new Correction
        {
            Id = newId,
            Op = islandRetype ? "découper" : Kind switch { TraceKind.Reshape => "remodeler", TraceKind.Create => "créer", _ => "découper" },
            To = Target, Subject = subject, Status = Correction.Proposed,
            Target = Kind == TraceKind.Create ? default : JsonSerializer.SerializeToElement(new { ids = new[] { TargetSurfaceId } }),
        };
        c.Extra ??= [];
        if (Existing is not null && !c.Extra.ContainsKey("base"))
            c.Extra["base"] = JsonSerializer.SerializeToElement(new { aire = Existing.Area, origine = Existing.Origin });
        var rings = (keepSiblings ? _siblings.Concat(ClosedPolygons()) : ClosedPolygons()).ToList();
        c.Extra["polygone"] = MultiPolygon(rings);
        c.Area = Math.Round(CountedArea + (keepSiblings ? _siblings.Sum(r => Math.Abs(Clipper.Area(ToPath(r)))) : 0), 2);
        c.M2 = c.Area;
        c.Trace = Triangulate(keepSiblings ? Clipper.Union(new PathsD(rings.Select(ToPath)), FillRule.NonZero) : Counted, _z);
        c.NeedsRetrace = false;
        c.Origin = "manuel";
        if (Kind != TraceKind.Cut)
        {
            c.Extra["z"] = JsonSerializer.SerializeToElement(Math.Round(_z, 3));
            c.To = c.Op == "remodeler" && Target == Source.DisplayCode ? null : Target;   // une découpe garde toujours sa catégorie
        }
        if (Source.FromCorrection is not null)
            c.Explanation = $"{Source.Building} {Source.Level} : surface découpée de {CountedText}, {Target}.";
        if (IsIsland && Existing is null)
            c.Explanation = islandRetype
                ? $"{Source.Building} {Source.Level} : îlot de {CountedText} de la {Source.DisplayCode} classé {Target}."
                : $"{Source.Building} {Source.Level} : îlot de la {Source.DisplayCode} redessiné, {OriginalAreaText} → {CountedText} ; autres îlots inchangés.";
        if (Kind == TraceKind.Create)
            c.Extra["niveau"] = JsonSerializer.SerializeToElement(new { building = Source.Building, level = Source.Level });
        if (!IsIsland && (string.IsNullOrWhiteSpace(c.Explanation) || Existing is null))   // îlot : explication posée plus haut
            c.Explanation = Kind switch
            {
                TraceKind.Create => $"{Source.Building} {Source.Level} : nouvelle {Target} de {CountedText}, tracée sur le plan.",
                TraceKind.Reshape => $"{Source.Building} {Source.Level} : emprise de la {Source.DisplayCode} redessinée, {OriginalAreaText} → {CountedText}" +
                                     (Target != Source.DisplayCode ? $", classée {Target}." : "."),
                _ => $"{Source.Building} {Source.Level} : {CountedText} de {Source.DisplayCode} tracés → {(Target == "" ? "exclus" : Target)}.",
            };
        return c;
    }

    private static JsonElement MultiPolygon(IEnumerable<List<Point>> rings) => JsonSerializer.SerializeToElement(new
    {
        type = "MultiPolygon",
        coordinates = rings.Select(p => new[] { p.Append(p[0]).Select(v => new[] { Math.Round(v.X, 3), Math.Round(v.Y, 3) }).ToArray() }).ToArray(),
    });

    /// <summary>Emprise d'une surface (îlot) : polygone GeoJSON, tracé pour la 3D, aire en plan.</summary>
    public static (JsonElement Polygon, TraceMesh? Trace, double Area) Footprint(Surface s)
    {
        var rings = OuterRings(Outline(s)).Select(r => r.Select(ToPoint).ToList()).ToList();
        var paths = Outline(s);
        return (MultiPolygon(rings), Triangulate(paths, TopZ(s)), Math.Abs(Clipper.Area(paths)));
    }

    internal static TraceMesh? Triangulate(PathsD paths, double z)
    {
        if (paths.Count == 0) return null;
        var tess = new Tess();
        foreach (var path in paths)
            tess.AddContour(path.Select(p => new ContourVertex(new Vec3((float)p.x, (float)p.y, 0))).ToArray(), ContourOrientation.Original);
        tess.Tessellate(WindingRule.NonZero, ElementType.Polygons, 3);
        if (tess.ElementCount == 0) return null;
        return new TraceMesh
        {
            Z = z,
            Vertices = tess.Vertices.SelectMany(v => new[] { Math.Round(v.Position.X, 3), Math.Round(v.Position.Y, 3) }).ToArray(),
            Indices = tess.Elements.Take(tess.ElementCount * 3).ToArray(),
        };
    }

    // ------------------------------------------------------------------ géométrie

    /// <summary>Contour d'une surface : union des triangles de son maillage (orientés positivement).</summary>
    internal static PathsD Outline(Surface s) => s.Mesh is { Vertices.Length: > 0 } m ? Outline(m) : [];

    internal static PathsD Outline(MeshData m)
    {
        var tris = new PathsD();
        for (var t = 0; t + 2 < m.Indices.Length; t += 3)
        {
            var tri = new PathD(3);
            for (var k = 0; k < 3; k++)
            {
                var i = m.Indices[t + k];
                tri.Add(new PointD(m.Vertices[3 * i], m.Vertices[3 * i + 1]));
            }
            if (Math.Abs(Clipper.Area(tri)) < 1e-9) continue;
            if (!Clipper.IsPositive(tri)) tri.Reverse();
            tris.Add(tri);
        }
        return tris.Count == 0 ? [] : Clipper.Union(tris, FillRule.NonZero);
    }

    /// <summary>Contours extérieurs d'une union Clipper : même orientation que le plus grand ; les trous, inverses, sont écartés.</summary>
    private static IEnumerable<PathD> OuterRings(PathsD paths)
    {
        if (paths.Count == 0) return [];
        var outer = Clipper.IsPositive(paths.MaxBy(p => Math.Abs(Clipper.Area(p)))!);
        return paths.Where(p => Clipper.IsPositive(p) == outer);
    }

    /// <summary>Altitude d'une nouvelle surface : le dessus de la SP du niveau, sinon le plus haut de ses surfaces.</summary>
    private static double LevelZ(IEnumerable<Surface> level)
    {
        var withMesh = level.Where(s => s.Mesh is { Vertices.Length: > 2 }).ToList();
        var sp = withMesh.FirstOrDefault(s => s.DisplayCode == "SP");
        return sp is not null ? TopZ(sp) : withMesh.Count > 0 ? withMesh.Max(TopZ) : 0;
    }

    private static double TopZ(Surface s) => s.Mesh is { } m ? TopZ(m) : 0;

    internal static double TopZ(MeshData m) =>
        m.Vertices.Length > 2 ? Enumerable.Range(0, m.Vertices.Length / 3).Max(k => (double)m.Vertices[3 * k + 2]) : 0;

    /// <summary>Maillage du tracé d'une correction (2D + altitude).</summary>
    public static MeshData ToMesh(TraceMesh t) => new()
    {
        Vertices = Enumerable.Range(0, t.Vertices.Length / 2).SelectMany(k => new[] { (float)t.Vertices[2 * k], (float)t.Vertices[2 * k + 1], (float)t.Z }).ToArray(),
        Indices = t.Indices,
    };

    /// <summary>Scission d'une part découpée : sa correction ne garde que la partie 1 (contour, type, aire).</summary>
    public Correction PartAsSplitA(Correction part)
    {
        var c = part.Clone();
        var area = Math.Round(Math.Abs(Clipper.Area(SplitPartA)), 2);
        c.To = SplitTypeA;
        c.Area = c.M2 = area;
        c.Trace = Triangulate(SplitPartA, _z);
        c.Extra ??= [];
        c.Extra["polygone"] = MultiPolygon(OuterRings(SplitPartA).Select(r => r.Select(ToPoint).ToList()));
        c.Origin = "manuel";
        c.Explanation = $"{Source.Building} {Source.Level} : surface découpée de {Area(area)}, {SplitTypeA} (partie 1 d'une scission).";
        return c;
    }

    /// <summary>Tracé d'une correction (`polygone`) en contours Clipper.</summary>
    public static PathsD PolygonOf(Correction c) => new(ReadPolygons(c).Select(ToPath));

    /// <summary>Maillage à plat d'un contour, à l'altitude z (format du fichier visionneuse).</summary>
    public static MeshData? ToMesh(PathsD paths, double z) => Triangulate(paths, z) is { } t
        ? new MeshData
        {
            Vertices = Enumerable.Range(0, t.Vertices.Length / 2).SelectMany(k => new[] { (float)t.Vertices[2 * k], (float)t.Vertices[2 * k + 1], (float)z }).ToArray(),
            Indices = t.Indices,
        }
        : null;

    private static List<List<Point>> ReadPolygons(Correction c)
    {
        var polys = new List<List<Point>>();
        if (c.Extra?.TryGetValue("polygone", out var g) != true || g.ValueKind != JsonValueKind.Object) return polys;
        var type = g.TryGetProperty("type", out var t) ? t.GetString() : null;
        if (!g.TryGetProperty("coordinates", out var coords)) return polys;
        IEnumerable<JsonElement> polygons = type == "MultiPolygon" ? coords.EnumerateArray() : type == "Polygon" ? [coords] : [];
        foreach (var poly in polygons)
        {
            var ring = poly.EnumerateArray().FirstOrDefault();   // contour extérieur ; les trous ne se modifient pas
            if (ring.ValueKind != JsonValueKind.Array) continue;
            var pts = ring.EnumerateArray().Select(p => new Point(p[0].GetDouble(), p[1].GetDouble())).ToList();
            if (pts.Count > 1 && (pts[0] - pts[^1]).Length < 1e-6) pts.RemoveAt(pts.Count - 1);
            if (pts.Count >= 3) polys.Add(pts);
        }
        return polys;
    }

    private static bool SelfIntersects(List<Point> p)
    {
        var n = p.Count;
        for (var i = 0; i < n; i++)
            for (var j = i + 2; j < n; j++)
            {
                if (i == 0 && j == n - 1) continue;   // arêtes voisines par la fermeture
                if (SegmentsCross(p[i], p[(i + 1) % n], p[j], p[(j + 1) % n])) return true;
            }
        return false;
    }

    private static bool SegmentsCross(Point a, Point b, Point c, Point d)
    {
        static double Cross(Vector u, Vector v) => u.X * v.Y - u.Y * v.X;
        var d1 = Cross(b - a, c - a);
        var d2 = Cross(b - a, d - a);
        var d3 = Cross(d - c, a - c);
        var d4 = Cross(d - c, b - c);
        return d1 * d2 < 0 && d3 * d4 < 0;
    }

    private static Point Project(Point p, Point a, Point b)
    {
        var ab = b - a;
        var len2 = ab.LengthSquared;
        if (len2 < 1e-12) return a;
        var t = Math.Clamp(Vector.Multiply(p - a, ab) / len2, 0, 1);
        return a + t * ab;
    }

    private static PathD ToPath(List<Point> poly)
    {
        var path = new PathD(poly.Select(v => new PointD(v.X, v.Y)));
        if (!Clipper.IsPositive(path)) path.Reverse();
        return path;
    }

    private static Point ToPoint(PointD p) => new(p.x, p.y);

    private static List<List<Point>> Copy(List<List<Point>> polys) => polys.Select(p => p.ToList()).ToList();
}
