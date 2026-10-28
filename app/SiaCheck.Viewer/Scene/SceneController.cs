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
/// <summary>
/// Aperçu d'une correction décidée que l'analyse n'a pas encore appliquée : surfaces masquées (exclusion, emprise
/// remplacée), recolorées (reclassement) et surface ajoutée (tracé d'une emprise, d'une création ou d'une découpe).
/// </summary>
public sealed record ScenePreview(string Id, IReadOnlyList<string> Hide, IReadOnlyList<string> Recolor, string? Code,
                                  TraceMesh? Mesh, string? Building, string? Level, bool Lift = false);

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
    private const double PreviewLift = 0.03;    // m : part découpée posée sur sa surface d'origine (aperçu)
    public const string PreviewPrefix = "aperçu:";

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
    /// <summary>Codes des surfaces lues : un code apparu par l'aperçu (SA d'une découpe…) n'a pas de calque, il reste visible.</summary>
    private HashSet<string> _baseCodes = [];
    private readonly HashSet<string> _previewHidden = new(StringComparer.Ordinal);
    private readonly Dictionary<string, string> _previewRecolored = new(StringComparer.Ordinal);   // id -> code d'origine
    private readonly HashSet<string> _previewAdded = new(StringComparer.Ordinal);
    private readonly HashSet<string> _previewLifted = new(StringComparer.Ordinal);
    private readonly Dictionary<string, SurfaceGeometry> _previewReplaced = new(StringComparer.Ordinal);   // id -> géométrie lue
    private HashSet<string>? _buildings;          // null = tous
    private string? _level;                       // null = tous
    private HashSet<string>? _focus;
    /// <summary>Coupe d'isolement : altitude du plus haut point isolé ; les niveaux qui commencent au-dessus sont masqués.</summary>
    private double? _cutZ;
    private double _explode;
    /// <summary>Maquette IFC d'un projet généré (V4) : murs, dalles, toits, poteaux par niveau, en gris translucide.</summary>
    private readonly Dictionary<(string B, string L), GeometryModel3D> _context = [];
    private bool _showContext;

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

    private const double GlazingOffset = 0.03;   // m : vitrages SRV devant la façade SFN, sans scintillement

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

    /// <summary>Surface en plusieurs îlots : ses îlots, seuls présents dans la scène (<see cref="ViewerDocument.Islands"/>).</summary>
    private readonly Dictionary<string, List<string>> _islandsOf = new(StringComparer.Ordinal);

    /// <summary>Identifiants de la scène : une surface à îlots devient ses îlots.</summary>
    private IEnumerable<string> Expand(IEnumerable<string> ids) =>
        ids.SelectMany(id => _islandsOf.TryGetValue(id, out var parts) ? parts : [id]);

    private void Build(ViewerDocument doc)
    {
        foreach (var (parent, parts) in doc.Islands) _islandsOf[parent] = parts.Select(p => p.Id).ToList();
        // Sans les totaux doublés par leurs pièces ; une surface en plusieurs îlots, un objet par îlot.
        foreach (var s in doc.DisplaySurfaces)
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
            _levels[grp.Key] = node;
            RebuildBatches(node);
        }
        foreach (var bld in _levels.Values.GroupBy(n => n.Building))
        {
            var ordinal = 0;
            foreach (var n in bld.OrderBy(n => ranks.GetValueOrDefault((n.Building, n.Level))))
                n.Ordinal = ordinal++;
        }
        _visibleCodes = Shown.Select(s => s.Code).ToHashSet();
        _baseCodes = _surfaces.Values.Select(s => s.Code).ToHashSet();
        Refresh();
    }

    /// <summary>Lots de rendu d'un niveau : une catégorie par lot, les parts découpées de l'aperçu à part (surélevées).</summary>
    private void RebuildBatches(LevelNode node)
    {
        foreach (var b in node.Batches) _byModel.Remove(b.Top);
        node.Batches.Clear();
        var shown = _surfaces.Values.Where(s => s.Building == node.Building && s.Level == node.Level && !_hidden.Contains(s.Id));
        foreach (var grp in shown.GroupBy(s => (s.Code, Lifted: _previewLifted.Contains(s.Id))).OrderBy(g => g.Key.Code))
            node.Batches.Add(MakeBatch(grp.Key.Code, grp, lift: grp.Key.Lifted ? PreviewLift : 0));
    }

    // ------------------------------------------------------------------ aperçu des corrections

    /// <summary>
    /// Remplace l'aperçu des corrections : rétablit l'état lu, puis masque, recolore et ajoute ce que les corrections
    /// décidées changeront à la prochaine analyse. Seuls les niveaux touchés sont reconstruits.
    /// </summary>
    /// <param name="replaced">Surfaces dont l'emprise change avant l'analyse (parts découpées en attente) : nouveau maillage,
    /// ou null si rien ne reste.</param>
    public void SetPreview(IReadOnlyList<ScenePreview> items, IReadOnlyDictionary<string, MeshData?>? replaced = null)
    {
        var touched = new HashSet<(string, string)>();
        void Touch(string id) { if (_surfaces.TryGetValue(id, out var g)) touched.Add((g.Building, g.Level)); }

        foreach (var (id, original) in _previewReplaced) { Touch(id); _surfaces[id] = original; }
        _previewReplaced.Clear();

        foreach (var id in _previewHidden) { Touch(id); _hidden.Remove(id); }
        _previewHidden.Clear();
        foreach (var (id, code) in _previewRecolored) { Touch(id); _surfaces[id] = _surfaces[id] with { Code = code }; }
        _previewRecolored.Clear();
        foreach (var id in _previewAdded) { Touch(id); _surfaces.Remove(id); }
        _previewAdded.Clear();
        _previewLifted.Clear();

        foreach (var (id, mesh) in replaced ?? new Dictionary<string, MeshData?>())
        {
            if (!_surfaces.TryGetValue(id, out var g)) continue;
            _previewReplaced[id] = g;
            Touch(id);
            if (mesh is null) { if (_hidden.Add(id)) _previewHidden.Add(id); continue; }
            var pts = new Point3D[mesh.Vertices.Length / 3];
            for (var k = 0; k < pts.Length; k++) pts[k] = new Point3D(mesh.Vertices[3 * k], mesh.Vertices[3 * k + 1], mesh.Vertices[3 * k + 2]);
            _surfaces[id] = g with { Points = pts, Indices = mesh.Indices };
        }
        foreach (var p in items)
        {
            foreach (var id in Expand(p.Hide).Where(id => _surfaces.ContainsKey(id) && !_hidden.Contains(id)))
            {
                _hidden.Add(id);
                _previewHidden.Add(id);
                Touch(id);
            }
            if (p.Code is { } code)
                foreach (var id in Expand(p.Recolor).Where(id => _surfaces.ContainsKey(id) && !_previewRecolored.ContainsKey(id)))
                {
                    _previewRecolored[id] = _surfaces[id].Code;
                    _surfaces[id] = _surfaces[id] with { Code = code };
                    Touch(id);
                }
            if (p is { Mesh: { Indices.Length: >= 3 } m, Code: { } c, Building: { } b, Level: { } l } && _levels.ContainsKey((b, l)))
            {
                var pts = new Point3D[m.Vertices.Length / 2];
                for (var k = 0; k < pts.Length; k++) pts[k] = new Point3D(m.Vertices[2 * k], m.Vertices[2 * k + 1], m.Z);
                var id = PreviewPrefix + p.Id;
                _surfaces[id] = new SurfaceGeometry(id, b, l, c, pts, m.Indices);
                _previewAdded.Add(id);
                if (p.Lift) _previewLifted.Add(id);
                touched.Add((b, l));
            }
        }
        foreach (var key in touched)
            if (_levels.TryGetValue(key, out var node)) RebuildBatches(node);
        if (touched.Count > 0) Refresh();
    }

    /// <summary>Surface de l'aperçu (tracé d'une correction) : pas de fiche, ce n'est pas une surface lue.</summary>
    public static bool IsPreview(string id) => id.StartsWith(PreviewPrefix, StringComparison.Ordinal);

    private Batch MakeBatch(string code, IEnumerable<SurfaceGeometry> surfaces, double lift)
    {
        // SP et SEP : totaux de plancher, coplanaires avec leurs surfaces élémentaires (pièces, balcons) ; posés
        // dessous, sinon les deux couleurs se disputent la profondeur (moiré en triangles)
        var sp = code is "SP" or "SEP";
        if (code == "SRV") surfaces = OffsetOutward(surfaces.ToList(), GlazingOffset);
        // Façades et vitrages sont verticaux : pas d'épaisseur de dalle, qui les doublerait d'un chant horizontal
        var (top, edges, starts, ids) = Extrude(surfaces,
            dz: lift - (sp ? SpDrop : 0), thickness: sp ? SpThickness : _palette.IsEnvelope(code) ? 0 : SlabThickness, textured: false);
        var batch = new Batch(code,
            new GeometryModel3D(top, MaterialOf(code, edge: false)) { BackMaterial = MaterialOf(code, edge: false) },
            new GeometryModel3D(edges, MaterialOf(code, edge: true)) { BackMaterial = MaterialOf(code, edge: true) },
            starts, ids);
        _byModel[batch.Top] = batch;
        return batch;
    }

    /// <summary>
    /// Vitrages opaques dans le plan de la façade : sans décalage, les deux se disputent le même plan
    /// (scintillement). Chaque vitrage avance selon sa normale, du côté opposé au centre de ses voisins du niveau.
    /// </summary>
    private static List<SurfaceGeometry> OffsetOutward(List<SurfaceGeometry> surfaces, double offset)
    {
        if (surfaces.Count == 0) return surfaces;
        var all = surfaces.SelectMany(s => s.Points).ToList();
        var cx = all.Average(p => p.X);
        var cy = all.Average(p => p.Y);
        return surfaces.Select(s =>
        {
            // Normale du plus grand triangle, ramenée à l'horizontale : les vitrages sont verticaux
            double nx = 0, ny = 0, best = 0;
            for (var t = 0; t + 2 < s.Indices.Length; t += 3)
            {
                var n = Vector3D.CrossProduct(s.Points[s.Indices[t + 1]] - s.Points[s.Indices[t]],
                                              s.Points[s.Indices[t + 2]] - s.Points[s.Indices[t]]);
                if (n.LengthSquared > best) (best, nx, ny) = (n.LengthSquared, n.X, n.Y);
            }
            var len = Math.Sqrt(nx * nx + ny * ny);
            if (len < 1e-9) return s;
            nx /= len; ny /= len;
            if (nx * (s.Points.Average(p => p.X) - cx) + ny * (s.Points.Average(p => p.Y) - cy) < 0) { nx = -nx; ny = -ny; }
            return s with { Points = s.Points.Select(p => new Point3D(p.X + nx * offset, p.Y + ny * offset, p.Z)).ToArray() };
        }).ToList();
    }

    /// <summary>
    /// Dessus (triangulation du moteur, décalée de dz) + chants : un quadrilatère vers le bas sur chaque
    /// arête de contour, c'est-à-dire chaque arête utilisée par un seul triangle de la surface ; + dessous,
    /// dans le maillage des chants (même teinte assombrie).
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
            // Dessous : la triangulation du dessus, retournée, au pied des chants. Sans elle, une dalle vue
            // d'en dessous est ouverte et laisse voir les triangles de son dessus.
            if (thickness > 0)
            {
                var k = edgePos.Count;
                foreach (var p in s.Points) edgePos.Add(new Point3D(p.X, p.Y, p.Z + dz - thickness));
                for (var t = 0; t + 2 < s.Indices.Length; t += 3)
                {
                    edgeIdx.Add(k + s.Indices[t]); edgeIdx.Add(k + s.Indices[t + 2]); edgeIdx.Add(k + s.Indices[t + 1]);
                }
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

    /// <param name="layerCodes">Codes qui ont un calque : un code sans calque (apparu par l'aperçu) reste visible.</param>
    public void SetVisibleCodes(IEnumerable<string> codes, IEnumerable<string>? layerCodes = null)
    {
        _visibleCodes = codes.ToHashSet();
        if (layerCodes is not null) _baseCodes = layerCodes.ToHashSet();
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

    /// <summary>Calque coché, ou code sans calque (apparu par l'aperçu des corrections).</summary>
    private bool IsShown(string code) => _visibleCodes.Contains(code) || !_baseCodes.Contains(code);

    private void Refresh()
    {
        Root.Children.Clear();
        foreach (var n in _levels.Values.OrderBy(n => n.Building).ThenBy(n => n.Ordinal))
        {
            n.Group.Children.Clear();
            // Opaques d'abord (surfaces isolées), fantôme translucide ensuite : ordre de rendu WPF.
            // Les calques valent aussi pour l'isolement : un calque masqué ne revient pas avec la surface isolée.
            foreach (var f in n.FocusBatches.Where(b => IsShown(b.Code))) { n.Group.Children.Add(f.Top); n.Group.Children.Add(f.Edges); }
            foreach (var o in n.Overlay) n.Group.Children.Add(o);
            if (FilterShows(n))
                foreach (var b in n.Batches.Where(b => IsShown(b.Code)))
                {
                    var top = _focus is null ? MaterialOf(b.Code, false) : _ghost;
                    var edge = _focus is null ? MaterialOf(b.Code, true) : _ghost;
                    b.Top.Material = b.Top.BackMaterial = top;
                    b.Edges.Material = b.Edges.BackMaterial = edge;
                    n.Group.Children.Add(b.Top);
                    // En fantôme, les chants alourdiraient le voile : on ne garde que les dessus.
                    if (_focus is null) n.Group.Children.Add(b.Edges);
                }
            if (_showContext && FilterShows(n) && _context.TryGetValue((n.Building, n.Level), out var ctx)) n.Group.Children.Add(ctx);
            if (n.Group.Children.Count > 0) Root.Children.Add(n.Group);
        }
    }

    // ------------------------------------------------------------------ maquette IFC (contexte)

    public bool HasContext => _context.Count > 0;

    /// <summary>
    /// Maquette de contexte d'un projet généré : un maillage par niveau, posé dans le groupe du niveau (il suit filtres,
    /// éclatement et coupe d'isolement). Les niveaux sans surface générée n'ont pas de groupe : leur maquette est ignorée.
    /// </summary>
    public void SetContext(ContextModel? model, Color color)
    {
        _context.Clear();
        if (model is not null)
        {
            var material = Frozen(new DiffuseMaterial(new SolidColorBrush(color)));
            foreach (var grp in model.Elements.GroupBy(e => (e.Building, e.Level)).Where(g => _levels.ContainsKey(g.Key)))
            {
                var mesh = new MeshGeometry3D();
                var pos = new Point3DCollection();
                var idx = new Int32Collection();
                foreach (var e in grp)
                {
                    var start = pos.Count;
                    for (var k = 0; k + 2 < e.Vertices.Length; k += 3) pos.Add(new Point3D(e.Vertices[k], e.Vertices[k + 1], e.Vertices[k + 2]));
                    foreach (var i in e.Indices) idx.Add(start + i);
                }
                mesh.Positions = pos;
                mesh.TriangleIndices = idx;
                mesh.Freeze();
                _context[grp.Key] = new GeometryModel3D(mesh, material) { BackMaterial = material };
            }
        }
        Refresh();
    }

    public void ShowContext(bool show)
    {
        _showContext = show;
        Refresh();
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
        // Une part posée sur une surface à îlots : tous ses îlots en fantôme, le tracé sur leur niveau.
        var traced = parts.Select(p => (Ids: Expand([p.SurfaceId]).Where(_surfaces.ContainsKey).ToList(), p.Trace))
                          .Where(p => p.Ids.Count > 0).ToList();
        var partIds = traced.SelectMany(p => p.Ids).ToHashSet();
        var shown = Expand(surfaceIds).Where(id => _surfaces.ContainsKey(id) && !partIds.Contains(id)).Select(id => _surfaces[id]).ToList();
        var all = shown.Concat(partIds.Select(id => _surfaces[id])).ToList();
        _focus = all.Select(s => s.Id).ToHashSet();
        _cutZ = Bounds(all) is { } fb ? fb.Z + fb.SizeZ : null;
        foreach (var grp in shown.GroupBy(s => (s.Building, s.Level)))
        {
            var node = _levels[grp.Key];
            foreach (var byCode in grp.GroupBy(s => s.Code))
                node.FocusBatches.Add(MakeBatch(byCode.Key, byCode, lift: FocusLift));
        }
        foreach (var (ids, trace) in traced)
            AddOverlay(trace, _surfaces[ids[0]].Building, _surfaces[ids[0]].Level, accent, PartAlpha);
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
        Bounds(Expand(surfaceIds).Where(_surfaces.ContainsKey).Select(id => _surfaces[id]));

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
