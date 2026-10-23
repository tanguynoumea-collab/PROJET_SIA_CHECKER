using System.Windows.Media;
using System.Windows.Media.Media3D;
using SiaCheck.Viewer.Models;

namespace SiaCheck.Viewer.Scene;

/// <summary>
/// Scène 3D des surfaces SIA, indépendante de la vue.
///
/// Rendu « dalles » à la Treegram : chaque surface est extrudée vers le bas (épaisseur fixe)
/// avec des chants plus sombres que le dessus, et la SP est une dalle opaque plus foncée posée
/// sous les pièces. Les joints entre pièces et les tranches de chaque niveau restent lisibles
/// en vue plongeante ou quand plusieurs niveaux se superposent à l'écran.
///
/// Hiérarchie : Root → un groupe par (bâtiment, niveau) portant la translation d'éclatement →
/// par catégorie, un modèle « dessus » et un modèle « chants ». Regrouper ~5 700 surfaces en
/// ~1 300 lots garde la vue fluide ; chaque lot conserve la table sommet → surface pour la sélection.
///
/// Isolement d'un point d'attention : les lots passent en matériau fantôme, les surfaces concernées
/// sont rajoutées par-dessus avec leurs couleurs, et les niveaux au-dessus du point sont coupés.
///
/// Corrections (V2) : une surface exclue par une correction n'est dans aucun lot, mais reste isolable
/// (sélection de sa correction). Le tracé d'une correction se dessine en surimpression, à l'accent :
/// aplat translucide et liseré, posés sur la surface visée.
/// </summary>
public sealed class SceneController
{
    private const double SlabThickness = 0.15;  // m : dalle d'une surface élémentaire
    private const double SpThickness = 0.30;    // m : dalle SP, plus épaisse, sous les pièces
    private const double SpDrop = 0.04;         // m : dessus de la SP sous celui des pièces (joints visibles)
    private const double EdgeShade = 0.58;      // chants : 58 % de la luminosité du dessus
    private const double SpShade = 0.72;        // SP plus foncée que sa couleur de légende, comme dans Treegram
    private const double ExternalTint = 0.45;   // surfaces externes : part de la couleur conservée (reste = blanc)
    private const double FocusLift = 0.01;      // m : évite le scintillement avec le fantôme coplanaire
    private const double CutTolerance = 0.5;    // m
    private const double OverlayLift = 0.05;    // m : tracé au-dessus de la surface visée
    private const double OverlayEdge = 0.35;    // m : hauteur du liseré du tracé
    private const byte OverlayAlpha = 0x55;     // aplat du tracé : accent à ~33 %
    private const byte PartAlpha = 0xD0;        // part isolée : aplat presque opaque sur la surface en fantôme

    public Model3DGroup Root { get; } = new();

    private readonly SiaPalette _palette;
    private readonly Dictionary<(string B, string L), LevelNode> _levels = [];
    private readonly Dictionary<string, SurfaceGeometry> _surfaces = new(StringComparer.Ordinal);
    private readonly Dictionary<GeometryModel3D, Batch> _byModel = [];
    private readonly Dictionary<(string Code, bool Edge), Material> _materials = [];
    private readonly Material _ghost;
    /// <summary>Surfaces exclues par une correction : géométrie connue, absentes des lots.</summary>
    private readonly HashSet<string> _hidden = new(StringComparer.Ordinal);

    private HashSet<string> _visibleCodes = [];
    private HashSet<string>? _buildings;          // null = tous
    private string? _level;                       // null = tous
    private HashSet<string>? _focus;
    /// <summary>Coupe d'isolement : altitude du plus haut point isolé ; les niveaux qui commencent au-dessus sont masqués.</summary>
    private double? _cutZ;
    private double _explode;

    public SceneController(ViewerDocument doc, SiaPalette palette, Color ghost)
    {
        _palette = palette;
        _ghost = Frozen(new DiffuseMaterial(new SolidColorBrush(ghost)));
        Build(doc);
    }

    public int SurfacesWithGeometry => _surfaces.Count - _hidden.Count;
    public IEnumerable<string> Codes => Shown.Select(s => s.Code).Distinct();
    private IEnumerable<SurfaceGeometry> Shown => _surfaces.Values.Where(s => !_hidden.Contains(s.Id));
    public bool IsFocused => _focus is not null;

    // ------------------------------------------------------------------ construction

    private sealed record SurfaceGeometry(string Id, string Building, string Level, string Code, Point3D[] Points, int[] Indices);

    /// <summary>Un lot de rendu : dessus (sélectionnable) + chants, pour une catégorie d'un niveau.</summary>
    private sealed class Batch(string code, GeometryModel3D top, GeometryModel3D edges, int[] starts, string[] ids)
    {
        public string Code { get; } = code;
        public GeometryModel3D Top { get; } = top;
        public GeometryModel3D Edges { get; } = edges;
        public int[] VertexStarts { get; } = starts;
        public string[] Ids { get; } = ids;
    }

    private sealed class LevelNode(string building, string level)
    {
        public string Building { get; } = building;
        public string Level { get; } = level;
        public Model3DGroup Group { get; } = new();
        public TranslateTransform3D Translate { get; } = new();
        public List<Batch> Batches { get; } = [];
        public List<Batch> FocusBatches { get; } = [];
        public List<Model3D> Overlay { get; } = [];
        public int Ordinal { get; set; }
        /// <summary>Altitude la plus basse du niveau, hors éclatement.</summary>
        public double MinZ { get; set; }
    }

    private void Build(ViewerDocument doc)
    {
        foreach (var s in doc.Surfaces)
        {
            if (s.Mesh is not { Vertices.Length: > 0 } m || s.Building is null || s.Level is null) continue;
            var pts = new Point3D[m.Vertices.Length / 3];
            for (var k = 0; k < pts.Length; k++)
                pts[k] = new Point3D(m.Vertices[3 * k], m.Vertices[3 * k + 1], m.Vertices[3 * k + 2]);
            _surfaces[s.Id] = new SurfaceGeometry(s.Id, s.Building, s.Level, s.DisplayCode, pts, m.Indices);
            if (s.IsExcluded) _hidden.Add(s.Id);
        }

        // Rang des niveaux par bâtiment : sert à l'éclatement (écart proportionnel à l'ordre réel des niveaux).
        var ranks = doc.Levels.ToDictionary(l => (l.Building, l.Level), l => l.Rank ?? 0);
        foreach (var grp in _surfaces.Values.GroupBy(s => (s.Building, s.Level)))
        {
            var node = new LevelNode(grp.Key.Building, grp.Key.Level) { MinZ = grp.Min(s => s.Points.Min(p => p.Z)) };
            node.Group.Transform = node.Translate;
            foreach (var byCode in grp.Where(s => !_hidden.Contains(s.Id)).GroupBy(s => s.Code).OrderBy(g => g.Key))
                node.Batches.Add(MakeBatch(byCode.Key, byCode, lift: 0));
            _levels[grp.Key] = node;
        }
        foreach (var bld in _levels.Values.GroupBy(n => n.Building))
        {
            var ordinal = 0;
            foreach (var n in bld.OrderBy(n => ranks.GetValueOrDefault((n.Building, n.Level))))
                n.Ordinal = ordinal++;
        }
        _visibleCodes = Shown.Select(s => s.Code).ToHashSet();
        Refresh();
    }

    private Batch MakeBatch(string code, IEnumerable<SurfaceGeometry> surfaces, double lift)
    {
        var sp = code == "SP";
        var (top, edges, starts, ids) = Extrude(surfaces,
            dz: lift - (sp ? SpDrop : 0), thickness: sp ? SpThickness : SlabThickness, textured: false);
        var batch = new Batch(code,
            new GeometryModel3D(top, MaterialOf(code, edge: false)) { BackMaterial = MaterialOf(code, edge: false) },
            new GeometryModel3D(edges, MaterialOf(code, edge: true)) { BackMaterial = MaterialOf(code, edge: true) },
            starts, ids);
        _byModel[batch.Top] = batch;
        return batch;
    }

    /// <summary>
    /// Dessus (triangulation du moteur, décalée de dz) + chants : un quadrilatère vers le bas sur chaque
    /// arête de contour, c'est-à-dire chaque arête utilisée par un seul triangle de la surface.
    /// </summary>
    private static (MeshGeometry3D Top, MeshGeometry3D Edges, int[] Starts, string[] Ids) Extrude(
        IEnumerable<SurfaceGeometry> surfaces, double dz, double thickness, bool textured)
    {
        var top = new MeshGeometry3D();
        var topPos = new Point3DCollection();
        var topIdx = new Int32Collection();
        var tex = textured ? new System.Windows.Media.PointCollection() : null;
        var edgePos = new Point3DCollection();
        var edgeIdx = new Int32Collection();
        var starts = new List<int>();
        var ids = new List<string>();
        foreach (var s in surfaces)
        {
            var baseIndex = topPos.Count;
            starts.Add(baseIndex);
            ids.Add(s.Id);
            foreach (var p in s.Points)
            {
                topPos.Add(new Point3D(p.X, p.Y, p.Z + dz));
                tex?.Add(new System.Windows.Point(p.X / SiaPalette.HatchTexturePeriod, p.Y / SiaPalette.HatchTexturePeriod));
            }
            foreach (var i in s.Indices) topIdx.Add(baseIndex + i);

            foreach (var (a, b) in BoundaryEdges(s.Indices))
            {
                var pa = s.Points[a];
                var pb = s.Points[b];
                var k = edgePos.Count;
                edgePos.Add(new Point3D(pa.X, pa.Y, pa.Z + dz));
                edgePos.Add(new Point3D(pb.X, pb.Y, pb.Z + dz));
                edgePos.Add(new Point3D(pb.X, pb.Y, pb.Z + dz - thickness));
                edgePos.Add(new Point3D(pa.X, pa.Y, pa.Z + dz - thickness));
                edgeIdx.Add(k); edgeIdx.Add(k + 2); edgeIdx.Add(k + 1);
                edgeIdx.Add(k); edgeIdx.Add(k + 3); edgeIdx.Add(k + 2);
            }
        }
        top.Positions = topPos;
        top.TriangleIndices = topIdx;
        if (tex is not null) top.TextureCoordinates = tex;
        top.Freeze();
        var edges = new MeshGeometry3D { Positions = edgePos, TriangleIndices = edgeIdx };
        edges.Freeze();
        return (top, edges, starts.ToArray(), ids.ToArray());
    }

    /// <summary>Arêtes orientées utilisées par un seul triangle : le contour (extérieur et trous) de la surface.</summary>
    internal static IEnumerable<(int A, int B)> BoundaryEdges(int[] indices)
    {
        var count = new Dictionary<(int, int), int>();
        var oriented = new List<(int, int)>(indices.Length);
        for (var t = 0; t + 2 < indices.Length; t += 3)
            foreach (var (a, b) in new[] { (indices[t], indices[t + 1]), (indices[t + 1], indices[t + 2]), (indices[t + 2], indices[t]) })
            {
                var key = a < b ? (a, b) : (b, a);
                count[key] = count.GetValueOrDefault(key) + 1;
                oriented.Add((a, b));
            }
        return oriented.Where(e => count[e.Item1 < e.Item2 ? (e.Item1, e.Item2) : (e.Item2, e.Item1)] == 1);
    }

    private Material MaterialOf(string code, bool edge)
    {
        if (_materials.TryGetValue((code, edge), out var m)) return m;
        var c = _palette.ColorOf(code);
        if (code == "SP") c = SiaPalette.Shade(c, SpShade);
        // Surfaces externes : aplat pâle de leur teinte plutôt que des hachures. En 3D, la distance fait
        // varier l'échelle des hachures et produit un moiré qui envahit la vue d'ensemble ; les hachures
        // restent dans la légende et le bilan, où l'échelle est fixe.
        if (_palette.IsHatched(code)) c = SiaPalette.Tint(c, ExternalTint);
        Brush brush = new SolidColorBrush(edge ? SiaPalette.Shade(c, EdgeShade) : c);
        brush.Freeze();
        return _materials[(code, edge)] = Frozen(new DiffuseMaterial(brush));
    }

    private static Material Frozen(Material m)
    {
        m.Freeze();
        return m;
    }

    // ------------------------------------------------------------------ visibilité

    public void SetVisibleCodes(IEnumerable<string> codes)
    {
        _visibleCodes = codes.ToHashSet();
        Refresh();
    }

    /// <summary>Filtre bâtiments (null = tous) et niveau (null = tous).</summary>
    public void SetFilter(IEnumerable<string>? buildings, string? level)
    {
        _buildings = buildings?.ToHashSet();
        _level = level;
        Refresh();
    }

    /// <summary>Écart supplémentaire entre niveaux successifs d'un même bâtiment, en mètres.</summary>
    public void SetExplode(double metres)
    {
        _explode = metres;
        foreach (var n in _levels.Values) n.Translate.OffsetZ = n.Ordinal * metres;
    }

    private bool FilterShows(LevelNode n) =>
        (_buildings is null || _buildings.Contains(n.Building)) && (_level is null || _level == n.Level) &&
        !(_cutZ is { } cut && n.MinZ + n.Ordinal * _explode > cut + CutTolerance);

    private void Refresh()
    {
        Root.Children.Clear();
        foreach (var n in _levels.Values.OrderBy(n => n.Building).ThenBy(n => n.Ordinal))
        {
            n.Group.Children.Clear();
            // Opaques d'abord (surfaces isolées), fantôme translucide ensuite : ordre de rendu WPF.
            foreach (var f in n.FocusBatches) { n.Group.Children.Add(f.Top); n.Group.Children.Add(f.Edges); }
            foreach (var o in n.Overlay) n.Group.Children.Add(o);
            if (FilterShows(n))
                foreach (var b in n.Batches.Where(b => _visibleCodes.Contains(b.Code)))
                {
                    var top = _focus is null ? MaterialOf(b.Code, false) : _ghost;
                    var edge = _focus is null ? MaterialOf(b.Code, true) : _ghost;
                    b.Top.Material = b.Top.BackMaterial = top;
                    b.Edges.Material = b.Edges.BackMaterial = edge;
                    n.Group.Children.Add(b.Top);
                    // En fantôme, les chants alourdiraient le voile : on ne garde que les dessus.
                    if (_focus is null) n.Group.Children.Add(b.Edges);
                }
            if (n.Group.Children.Count > 0) Root.Children.Add(n.Group);
        }
    }

    // ------------------------------------------------------------------ isolement

    /// <summary>Isole des surfaces ; renvoie leurs bornes (éclatement compris), ou null si aucune n'a de géométrie.</summary>
    public Rect3D? Focus(IEnumerable<string> surfaceIds) => Focus(surfaceIds, []);

    /// <summary>
    /// Isole des surfaces entières et des parts de surface (tracés des corrections). Une surface dont seule une part
    /// est en cause reste en fantôme, la part est posée dessus à l'accent : la zone déjà classée de la même surface
    /// (SED d'une SEP…) ne se confond pas avec le problème.
    /// </summary>
    public Rect3D? Focus(IEnumerable<string> surfaceIds, IReadOnlyList<(string SurfaceId, TraceMesh Trace)> parts, Color accent = default)
    {
        ClearFocusBatches();
        var partIds = parts.Select(p => p.SurfaceId).ToHashSet();
        surfaceIds = surfaceIds.Where(id => !partIds.Contains(id)).ToList();
        var traced = parts.Where(p => _surfaces.ContainsKey(p.SurfaceId)).ToList();
        var shown = surfaceIds.Where(_surfaces.ContainsKey).Select(id => _surfaces[id]).ToList();
        var all = shown.Concat(traced.Select(p => _surfaces[p.SurfaceId])).ToList();
        _focus = all.Select(s => s.Id).ToHashSet();
        _cutZ = Bounds(all) is { } fb ? fb.Z + fb.SizeZ : null;
        foreach (var grp in shown.GroupBy(s => (s.Building, s.Level)))
        {
            var node = _levels[grp.Key];
            foreach (var byCode in grp.GroupBy(s => s.Code))
                node.FocusBatches.Add(MakeBatch(byCode.Key, byCode, lift: FocusLift));
        }
        foreach (var (id, trace) in traced)
            AddOverlay(trace, _surfaces[id].Building, _surfaces[id].Level, accent, PartAlpha);
        Refresh();
        return Bounds(all);
    }

    public void ClearFocus()
    {
        ClearFocusBatches();
        _focus = null;
        _cutZ = null;
        Refresh();
    }

    private void ClearFocusBatches()
    {
        foreach (var n in _levels.Values)
        {
            foreach (var b in n.FocusBatches) _byModel.Remove(b.Top);
            n.FocusBatches.Clear();
            n.Overlay.Clear();
        }
    }

    /// <summary>
    /// Tracé d'une correction (part de surface qui va bouger) posé sur son niveau, à l'accent : aplat
    /// translucide et liseré. Effacé par le prochain isolement ou par <see cref="ClearFocus"/>.
    /// </summary>
    public void SetOverlay(TraceMesh trace, string building, string level, Color accent)
    {
        if (_levels.TryGetValue((building, level), out var node)) node.Overlay.Clear();
        AddOverlay(trace, building, level, accent, OverlayAlpha);
        Refresh();
    }

    private void AddOverlay(TraceMesh trace, string building, string level, Color accent, byte alpha)
    {
        if (!_levels.TryGetValue((building, level), out var node) || trace.Indices.Length < 3) return;
        var z = trace.Z + OverlayLift;
        var pts = new Point3D[trace.Vertices.Length / 2];
        for (var k = 0; k < pts.Length; k++) pts[k] = new Point3D(trace.Vertices[2 * k], trace.Vertices[2 * k + 1], z);

        var fill = new MeshGeometry3D { Positions = new Point3DCollection(pts), TriangleIndices = new Int32Collection(trace.Indices) };
        fill.Freeze();
        var fillMat = Frozen(new DiffuseMaterial(new SolidColorBrush(Color.FromArgb(alpha, accent.R, accent.G, accent.B))));
        var edges = new MeshGeometry3D();
        var pos = new Point3DCollection();
        var idx = new Int32Collection();
        foreach (var (a, b) in BoundaryEdges(trace.Indices))
        {
            var k = pos.Count;
            pos.Add(pts[a]); pos.Add(pts[b]);
            pos.Add(new Point3D(pts[b].X, pts[b].Y, z + OverlayEdge)); pos.Add(new Point3D(pts[a].X, pts[a].Y, z + OverlayEdge));
            idx.Add(k); idx.Add(k + 1); idx.Add(k + 2);
            idx.Add(k); idx.Add(k + 2); idx.Add(k + 3);
        }
        edges.Positions = pos;
        edges.TriangleIndices = idx;
        edges.Freeze();
        var edgeMat = Frozen(new EmissiveMaterial(new SolidColorBrush(accent)));
        // Liseré opaque d'abord, aplat translucide ensuite : ordre de rendu WPF de la transparence.
        node.Overlay.Add(new GeometryModel3D(edges, edgeMat) { BackMaterial = edgeMat });
        node.Overlay.Add(new GeometryModel3D(fill, fillMat) { BackMaterial = fillMat });
    }

    public Rect3D? Bounds(IEnumerable<string> surfaceIds) =>
        Bounds(surfaceIds.Where(_surfaces.ContainsKey).Select(id => _surfaces[id]));

    private Rect3D? Bounds(IEnumerable<SurfaceGeometry> surfaces)
    {
        Rect3D? r = null;
        foreach (var s in surfaces)
        {
            var dz = _levels[(s.Building, s.Level)].Ordinal * _explode;
            foreach (var p in s.Points)
            {
                var b = new Rect3D(p.X, p.Y, p.Z + dz, 0, 0, 0);
                r = r is { } cur ? Rect3D.Union(cur, b) : b;
            }
        }
        return r;
    }

    public IEnumerable<string> SurfacesOfLevel(string building, string level) =>
        Shown.Where(s => s.Building == building && s.Level == level).Select(s => s.Id);

    // ------------------------------------------------------------------ sélection

    /// <summary>Surface touchée : modèle « dessus » et indice de sommet renvoyés par le test d'impact WPF.</summary>
    public string? SurfaceAt(GeometryModel3D model, int vertexIndex)
    {
        if (!_byModel.TryGetValue(model, out var batch)) return null;
        var k = Array.BinarySearch(batch.VertexStarts, vertexIndex);
        if (k < 0) k = ~k - 1;
        return k >= 0 ? batch.Ids[k] : null;
    }
}
