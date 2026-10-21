using System.Windows.Media;
using System.Windows.Media.Media3D;
using SiaCheck.Viewer.Models;

namespace SiaCheck.Viewer.Scene;

/// <summary>
/// Scène 3D des surfaces SIA, indépendante de la vue.
///
/// Hiérarchie : Root → un groupe par (bâtiment, niveau) portant la translation d'éclatement →
/// un GeometryModel3D par catégorie (« lot de rendu »). Regrouper ~5 700 surfaces en ~1 300 lots
/// garde la vue fluide ; chaque lot conserve la table sommet → surface pour la sélection au clic.
///
/// Isolement d'un point d'attention : tous les lots passent en matériau fantôme et les surfaces
/// concernées sont rajoutées par-dessus avec leur couleur, dans le groupe de leur niveau.
/// </summary>
public sealed class SceneController
{
    private const double FocusLift = 0.01;   // m : évite le scintillement avec le fantôme coplanaire
    private const double SpOpacity = 0.20;   // SP : plaque translucide sous ses sous-catégories (plan §2)

    public Model3DGroup Root { get; } = new();

    private readonly SiaPalette _palette;
    private readonly Dictionary<(string B, string L), LevelNode> _levels = [];
    private readonly Dictionary<string, SurfaceGeometry> _surfaces = new(StringComparer.Ordinal);
    private readonly Dictionary<GeometryModel3D, Batch> _byModel = [];
    private readonly Dictionary<string, Material> _materials = [];
    private readonly Material _ghost;

    private HashSet<string> _visibleCodes = [];
    private HashSet<string>? _buildings;          // null = tous
    private string? _level;                       // null = tous
    private HashSet<string>? _focus;
    /// <summary>
    /// Coupe d'isolement : altitude (éclatement compris) du plus haut point isolé. Les niveaux qui
    /// commencent au-dessus sont masqués, tous bâtiments confondus : un socle commun passe sous les voisins.
    /// </summary>
    private double? _cutZ;
    private const double CutTolerance = 0.5;   // m
    private double _explode;

    public SceneController(ViewerDocument doc, SiaPalette palette, Color ghost)
    {
        _palette = palette;
        _ghost = Frozen(new DiffuseMaterial(new SolidColorBrush(ghost)));
        Build(doc);
    }

    public int SurfacesWithGeometry => _surfaces.Count;
    public IEnumerable<string> Codes => _surfaces.Values.Select(s => s.Code).Distinct();
    public bool IsFocused => _focus is not null;

    // ------------------------------------------------------------------ construction

    private sealed record SurfaceGeometry(string Id, string Building, string Level, string Code, Point3D[] Points, int[] Indices);

    private sealed class Batch(string code, GeometryModel3D model, int[] starts, string[] ids)
    {
        public string Code { get; } = code;
        public GeometryModel3D Model { get; } = model;
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
        public List<GeometryModel3D> FocusModels { get; } = [];
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
        }

        // Rang des niveaux par bâtiment : sert à l'éclatement (écart proportionnel à l'ordre réel des niveaux).
        var ranks = doc.Levels.ToDictionary(l => (l.Building, l.Level), l => l.Rank ?? 0);
        foreach (var grp in _surfaces.Values.GroupBy(s => (s.Building, s.Level)))
        {
            var node = new LevelNode(grp.Key.Building, grp.Key.Level)
            {
                MinZ = grp.Min(s => s.Points.Min(p => p.Z)),
            };
            node.Group.Transform = node.Translate;
            // SP en dernier : translucide, il doit être dessiné après les surfaces opaques.
            foreach (var byCode in grp.GroupBy(s => s.Code).OrderBy(g => g.Key == "SP" ? 1 : 0).ThenBy(g => g.Key))
            {
                var (mesh, starts, ids) = Merge(byCode, _palette.IsHatched(byCode.Key));
                var model = new GeometryModel3D(mesh, MaterialOf(byCode.Key)) { BackMaterial = MaterialOf(byCode.Key) };
                var batch = new Batch(byCode.Key, model, starts, ids);
                node.Batches.Add(batch);
                _byModel[model] = batch;
            }
            _levels[grp.Key] = node;
        }
        foreach (var bld in _levels.Values.GroupBy(n => n.Building))
        {
            var ordinal = 0;
            foreach (var n in bld.OrderBy(n => ranks.GetValueOrDefault((n.Building, n.Level))))
                n.Ordinal = ordinal++;
        }
        _visibleCodes = _surfaces.Values.Select(s => s.Code).ToHashSet();
        Refresh();
    }

    private static (MeshGeometry3D, int[], string[]) Merge(IEnumerable<SurfaceGeometry> surfaces, bool textured)
    {
        var mesh = new MeshGeometry3D();
        var positions = new Point3DCollection();
        var indices = new Int32Collection();
        var tex = textured ? new System.Windows.Media.PointCollection() : null;
        var starts = new List<int>();
        var ids = new List<string>();
        foreach (var s in surfaces)
        {
            var baseIndex = positions.Count;
            starts.Add(baseIndex);
            ids.Add(s.Id);
            foreach (var p in s.Points)
            {
                positions.Add(p);
                tex?.Add(new System.Windows.Point(p.X / SiaPalette.HatchTexturePeriod, p.Y / SiaPalette.HatchTexturePeriod));
            }
            foreach (var i in s.Indices) indices.Add(baseIndex + i);
        }
        mesh.Positions = positions;
        mesh.TriangleIndices = indices;
        if (tex is not null) mesh.TextureCoordinates = tex;
        mesh.Freeze();
        return (mesh, starts.ToArray(), ids.ToArray());
    }

    private Material MaterialOf(string code)
    {
        if (_materials.TryGetValue(code, out var m)) return m;
        var c = _palette.ColorOf(code);
        Brush brush = _palette.IsHatched(code)
            ? SiaPalette.Hatch(c, 0.35, BrushMappingMode.Absolute, 1.0)
            : code == "SP" ? new SolidColorBrush(Color.FromArgb((byte)(255 * SpOpacity), c.R, c.G, c.B))
            : new SolidColorBrush(c);
        brush.Freeze();
        return _materials[code] = Frozen(new DiffuseMaterial(brush));
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
            // Les surfaces isolées s'affichent même hors filtre ou calque masqué : on vient de les demander.
            foreach (var f in n.FocusModels) n.Group.Children.Add(f);
            if (FilterShows(n))
                foreach (var b in n.Batches.Where(b => _visibleCodes.Contains(b.Code)))
                {
                    var mat = _focus is null ? MaterialOf(b.Code) : _ghost;
                    b.Model.Material = mat;
                    b.Model.BackMaterial = mat;
                    n.Group.Children.Add(b.Model);
                }
            if (n.Group.Children.Count > 0) Root.Children.Add(n.Group);
        }
    }

    // ------------------------------------------------------------------ isolement

    /// <summary>Isole des surfaces ; renvoie leurs bornes (éclatement compris), ou null si aucune n'a de géométrie.</summary>
    public Rect3D? Focus(IEnumerable<string> surfaceIds)
    {
        ClearFocusModels();
        var shown = surfaceIds.Where(_surfaces.ContainsKey).Select(id => _surfaces[id]).ToList();
        _focus = shown.Select(s => s.Id).ToHashSet();
        _cutZ = Bounds(shown) is { } fb ? fb.Z + fb.SizeZ : null;
        foreach (var grp in shown.GroupBy(s => (s.Building, s.Level)))
        {
            var node = _levels[grp.Key];
            foreach (var byCode in grp.GroupBy(s => s.Code))
            {
                var (mesh, starts, ids) = Merge(byCode.Select(Lift), _palette.IsHatched(byCode.Key));
                var model = new GeometryModel3D(mesh, MaterialOf(byCode.Key)) { BackMaterial = MaterialOf(byCode.Key) };
                node.FocusModels.Add(model);
                _byModel[model] = new Batch(byCode.Key, model, starts, ids);
            }
        }
        Refresh();
        return Bounds(shown);
    }

    public void ClearFocus()
    {
        ClearFocusModels();
        _focus = null;
        _cutZ = null;
        Refresh();
    }

    private void ClearFocusModels()
    {
        foreach (var n in _levels.Values)
        {
            foreach (var m in n.FocusModels) _byModel.Remove(m);
            n.FocusModels.Clear();
        }
    }

    private static SurfaceGeometry Lift(SurfaceGeometry s) =>
        s with { Points = s.Points.Select(p => new Point3D(p.X, p.Y, p.Z + FocusLift)).ToArray() };

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
        _surfaces.Values.Where(s => s.Building == building && s.Level == level).Select(s => s.Id);

    // ------------------------------------------------------------------ sélection

    /// <summary>Surface touchée : modèle et indice de sommet renvoyés par le test d'impact WPF.</summary>
    public string? SurfaceAt(GeometryModel3D model, int vertexIndex)
    {
        if (!_byModel.TryGetValue(model, out var batch)) return null;
        var k = Array.BinarySearch(batch.VertexStarts, vertexIndex);
        if (k < 0) k = ~k - 1;
        return k >= 0 ? batch.Ids[k] : null;
    }
}
