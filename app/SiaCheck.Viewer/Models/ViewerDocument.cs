using System.IO;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace SiaCheck.Viewer.Models;

/// <summary>
/// Contrat du fichier produit par <c>sia-check --viewer-json</c> (src/sia_check/viewer.py, format version 1).
/// </summary>
public sealed class ViewerDocument
{
    public const int SupportedVersion = 1;

    [JsonPropertyName("format")] public string Format { get; init; } = "";
    [JsonPropertyName("version")] public int Version { get; init; }
    [JsonPropertyName("tool_version")] public string ToolVersion { get; init; } = "";
    [JsonPropertyName("project")] public string Project { get; init; } = "";
    [JsonPropertyName("date")] public string Date { get; init; } = "";
    [JsonPropertyName("sources")] public List<string> Sources { get; init; } = [];
    [JsonPropertyName("exit_code")] public int ExitCode { get; init; }
    [JsonPropertyName("counts")] public Dictionary<string, int> Counts { get; init; } = [];
    [JsonPropertyName("tolerance")] public Tolerance Tolerance { get; init; } = new();
    [JsonPropertyName("cache")] public CacheInfo Cache { get; init; } = new();
    [JsonPropertyName("categories")] public List<CategoryInfo> Categories { get; init; } = [];
    [JsonPropertyName("surfaces")] public List<Surface> Surfaces { get; init; } = [];
    [JsonPropertyName("levels")] public List<LevelBalance> Levels { get; init; } = [];
    [JsonPropertyName("issues")] public List<Issue> Issues { get; init; } = [];
    /// <summary>Ratios informatifs (absents des fichiers antérieurs : liste vide).</summary>
    [JsonPropertyName("ratios")] public List<Ratio> Ratios { get; init; } = [];
    /// <summary>Sujets et corrections proposées (V2 ; absents des fichiers antérieurs : liste vide).</summary>
    [JsonPropertyName("subjects")] public List<Subject> Subjects { get; init; } = [];
    /// <summary>Application des corrections du journal (analyse lancée avec <c>--corrections</c>).</summary>
    [JsonPropertyName("corrections_log")] public List<CorrectionLogEntry> CorrectionsLog { get; init; } = [];
    /// <summary>Fusion de la revue IA (analyse lancée avec <c>--revue</c>).</summary>
    [JsonPropertyName("review")] public ReviewInfo? Review { get; init; }

    private HashSet<string>? _redundantTotals;
    private Dictionary<string, IReadOnlyList<Surface>>? _islands;
    private Dictionary<string, Surface>? _islandById;

    /// <summary>
    /// Surfaces faites de plusieurs îlots séparés (une SEP de niveau en plusieurs morceaux…) : chaque îlot est un objet
    /// à part pour la 3D, le plan et la fiche (id « parent#ilotN », aire au prorata de la géométrie). Les corrections
    /// visent la surface d'origine, avec le tracé de l'îlot.
    /// </summary>
    [JsonIgnore]
    public IReadOnlyDictionary<string, IReadOnlyList<Surface>> Islands => _islands ??= FindIslands();

    /// <summary>Îlot par identifiant.</summary>
    [JsonIgnore]
    public IReadOnlyDictionary<string, Surface> IslandById =>
        _islandById ??= Islands.Values.SelectMany(i => i).ToDictionary(s => s.Id, StringComparer.Ordinal);

    /// <summary>Surfaces à montrer et à sélectionner : sans les totaux doublés, chaque surface à îlots remplacée par ses îlots.</summary>
    [JsonIgnore]
    public IEnumerable<Surface> DisplaySurfaces =>
        Surfaces.Where(s => !RedundantTotals.Contains(s.Id))
                .SelectMany(s => Islands.TryGetValue(s.Id, out var parts) ? parts : [s]);

    private Dictionary<string, IReadOnlyList<Surface>> FindIslands()
    {
        var found = new Dictionary<string, IReadOnlyList<Surface>>(StringComparer.Ordinal);
        // Surfaces SIA 416 seulement : une surface USPI d'appartement (SNH d'un lot) reste un seul objet, pièces comprises.
        var sia = Categories.Where(c => c.Family == "sia").Select(c => c.Code).ToHashSet(StringComparer.Ordinal);
        foreach (var s in Surfaces.Where(s => s.Mesh is not null && !RedundantTotals.Contains(s.Id)
                                              && (sia.Count == 0 || sia.Contains(s.DisplayCode))))
        {
            var parts = MeshIslands.Split(s.Mesh!);
            if (parts.Count < 2) continue;
            var total = parts.Sum(p => p.Area);
            found[s.Id] = parts.Select((p, k) => new Surface
            {
                Id = $"{s.Id}#ilot{k + 1}", IslandOf = s.Id, Building = s.Building, Level = s.Level, Category = s.Category,
                Code = s.Code, Kind = s.Kind, Status = s.Status, RoomType = s.RoomType, Lot = s.Lot, Mesh = p.Mesh,
                Area = s.Area is double a && total > 0 ? Math.Round(a * p.Area / total, 2) : Math.Round(p.Area, 2),
            }).ToList();
        }
        return found;
    }

    /// <summary>
    /// Totaux de niveau Treegram dont les pièces (même catégorie, avec géométrie) sont livrées : même emprise que leur
    /// détail, qui fait foi dans les sommes. Ni montrés en 3D ni dans le plan, ni sélectionnables : sinon doublons.
    /// (Le moteur ne leur donne plus de maillage ; ce filtre vaut aussi pour une analyse antérieure.)
    /// </summary>
    [JsonIgnore]
    public IReadOnlySet<string> RedundantTotals => _redundantTotals ??= FindRedundantTotals();

    private HashSet<string> FindRedundantTotals()
    {
        var detailed = Surfaces.Where(s => s.Kind == "leaf" && s.Mesh is not null && !s.IsExcluded)
            .Select(s => (s.Building, s.Level, s.Category)).ToHashSet();
        return Surfaces.Where(s => s.Kind == "node" && detailed.Contains((s.Building, s.Level, s.Category)))
            .Select(s => s.Id).ToHashSet(StringComparer.Ordinal);
    }

    public static ViewerDocument Load(string path)
    {
        using var stream = File.OpenRead(path);
        var doc = JsonSerializer.Deserialize<ViewerDocument>(stream)
                  ?? throw new InvalidDataException($"{path} : fichier vide.");
        if (doc.Format != "sia-check-viewer")
            throw new InvalidDataException($"{path} : ce n'est pas un fichier sia-check pour la visionneuse.");
        if (doc.Version != SupportedVersion)
            throw new InvalidDataException(
                $"{path} : format version {doc.Version}, la visionneuse lit la version {SupportedVersion}. Mettez à jour l'application.");
        return doc;
    }
}

public sealed class Tolerance
{
    [JsonPropertyName("abs_m2")] public double AbsM2 { get; init; }
    [JsonPropertyName("rel")] public double Rel { get; init; }
}

public sealed class CacheInfo
{
    [JsonPropertyName("files")] public int Files { get; init; }
    [JsonPropertyName("newest")] public DateTime? Newest { get; init; }
    [JsonPropertyName("oldest")] public DateTime? Oldest { get; init; }
    [JsonPropertyName("source_modified")] public DateTime? SourceModified { get; init; }
    [JsonPropertyName("stale")] public bool Stale { get; init; }
    [JsonPropertyName("errors")] public List<string> Errors { get; init; } = [];
    [JsonPropertyName("surfaces_without_mesh")] public int SurfacesWithoutMesh { get; init; }
}

public sealed class CategoryInfo
{
    [JsonPropertyName("code")] public string Code { get; init; } = "";
    [JsonPropertyName("family")] public string? Family { get; init; }
    /// <summary>checked | ignored | unknown</summary>
    [JsonPropertyName("status")] public string Status { get; init; } = "";
    [JsonPropertyName("color")] public string? Color { get; init; }
    [JsonPropertyName("hatched")] public bool Hatched { get; init; }
    [JsonPropertyName("name")] public string? Name { get; init; }
    [JsonPropertyName("ref")] public string? Ref { get; init; }
    [JsonPropertyName("definition")] public string? Definition { get; init; }
}

public sealed class Surface
{
    [JsonPropertyName("id")] public string Id { get; init; } = "";
    [JsonPropertyName("building")] public string? Building { get; init; }
    [JsonPropertyName("level")] public string? Level { get; init; }
    [JsonPropertyName("category")] public string Category { get; init; } = "";
    [JsonPropertyName("code")] public string? Code { get; init; }
    /// <summary>leaf | node</summary>
    [JsonPropertyName("kind")] public string Kind { get; init; } = "";
    [JsonPropertyName("status")] public string Status { get; init; } = "";
    [JsonPropertyName("area")] public double? Area { get; init; }
    [JsonPropertyName("room_type")] public string? RoomType { get; init; }
    [JsonPropertyName("lot")] public string? Lot { get; init; }
    [JsonPropertyName("mesh")] public MeshData? Mesh { get; init; }

    /// <summary>Code affiché : code normalisé, sinon code brut (inconnus).</summary>
    [JsonIgnore] public string DisplayCode => Code ?? Category;
    [JsonIgnore] public bool IsLevelTotal => Kind == "node";
    /// <summary>Retirée par une correction : hors calques et hors sommes, montrée seulement à la demande.</summary>
    [JsonIgnore] public bool IsExcluded => Status == "excluded";
    /// <summary>Îlot d'une surface en plusieurs morceaux (<see cref="ViewerDocument.Islands"/>) : identifiant de la surface d'origine.</summary>
    [JsonIgnore] public string? IslandOf { get; init; }
    /// <summary>
    /// Part découpée d'une surface (scission, découpe), pas encore appliquée par une analyse : la correction qui la crée.
    /// Elle se modifie comme une surface ; ses changements mettent à jour cette correction. <see cref="IslandOf"/> porte
    /// la surface d'origine, visée par la correction.
    /// </summary>
    [JsonIgnore] public string? FromCorrection { get; init; }
}

public sealed class MeshData
{
    [JsonPropertyName("v")] public float[] Vertices { get; init; } = [];
    [JsonPropertyName("i")] public int[] Indices { get; init; } = [];
}

/// <summary>Morceaux d'un seul tenant d'un maillage : triangles reliés par un sommet commun (au millimètre près).</summary>
public static class MeshIslands
{
    /// <summary>Au-dessous (m²), un morceau est une miette du maillage : il rejoint le plus grand.</summary>
    private const double MinArea = 0.05;

    public static List<(MeshData Mesh, double Area)> Split(MeshData m)
    {
        var tris = m.Indices.Length / 3;
        if (tris < 2) return [(m, AreaOf(m, Enumerable.Range(0, tris)))];
        var parent = Enumerable.Range(0, tris).ToArray();
        int Find(int x) { while (parent[x] != x) x = parent[x] = parent[parent[x]]; return x; }
        var owner = new Dictionary<(long, long), int>();
        for (var t = 0; t < tris; t++)
            for (var k = 0; k < 3; k++)
            {
                var i = m.Indices[3 * t + k];
                var key = ((long)Math.Round(m.Vertices[3 * i] * 1000), (long)Math.Round(m.Vertices[3 * i + 1] * 1000));
                if (owner.TryGetValue(key, out var other)) parent[Find(t)] = Find(other);
                else owner[key] = t;
            }
        var groups = Enumerable.Range(0, tris).GroupBy(Find).Select(g => g.ToList()).OrderByDescending(g => AreaOf(m, g)).ToList();
        var big = groups.Where(g => AreaOf(m, g) >= MinArea).ToList();
        if (big.Count < 2) return [(m, AreaOf(m, Enumerable.Range(0, tris)))];
        foreach (var crumb in groups.Where(g => AreaOf(m, g) < MinArea)) big[0].AddRange(crumb);
        return big.Select(g => (SubMesh(m, g), AreaOf(m, g))).ToList();
    }

    private static double AreaOf(MeshData m, IEnumerable<int> tris)
    {
        double a = 0;
        foreach (var t in tris)
        {
            var (i, j, k) = (m.Indices[3 * t], m.Indices[3 * t + 1], m.Indices[3 * t + 2]);
            a += Math.Abs((m.Vertices[3 * j] - m.Vertices[3 * i]) * (m.Vertices[3 * k + 1] - m.Vertices[3 * i + 1])
                          - (m.Vertices[3 * k] - m.Vertices[3 * i]) * (m.Vertices[3 * j + 1] - m.Vertices[3 * i + 1])) / 2;
        }
        return a;
    }

    private static MeshData SubMesh(MeshData m, List<int> tris)
    {
        var map = new Dictionary<int, int>();
        var v = new List<float>();
        var idx = new List<int>();
        foreach (var t in tris)
            for (var k = 0; k < 3; k++)
            {
                var i = m.Indices[3 * t + k];
                if (!map.TryGetValue(i, out var n))
                {
                    map[i] = n = map.Count;
                    v.AddRange([m.Vertices[3 * i], m.Vertices[3 * i + 1], m.Vertices[3 * i + 2]]);
                }
                idx.Add(n);
            }
        return new MeshData { Vertices = [.. v], Indices = [.. idx] };
    }
}

/// <summary>Ratio informatif SIA 416 / USPI (src/sia_check/ratios.py) ; Building « * » = projet entier.</summary>
public sealed class Ratio
{
    public const string AllBuildings = "*";

    [JsonPropertyName("building")] public string Building { get; init; } = "";
    [JsonPropertyName("id")] public string Id { get; init; } = "";
    /// <summary>sia | uspi</summary>
    [JsonPropertyName("family")] public string Family { get; init; } = "";
    [JsonPropertyName("label")] public string Label { get; init; } = "";
    [JsonPropertyName("value")] public double? Value { get; init; }
    /// <summary>ratio | m2</summary>
    [JsonPropertyName("unit")] public string Unit { get; init; } = "ratio";
    [JsonPropertyName("ref_min")] public double? RefMin { get; init; }
    [JsonPropertyName("ref_max")] public double? RefMax { get; init; }
    /// <summary>ok | bas | haut | info | n/a</summary>
    [JsonPropertyName("status")] public string Status { get; init; } = "";
    [JsonPropertyName("num_m2")] public double? NumM2 { get; init; }
    [JsonPropertyName("den_m2")] public double? DenM2 { get; init; }
    [JsonPropertyName("note")] public string? Note { get; init; }

    public bool HasReference => RefMin is not null && RefMax is not null;
}

/// <summary>Aperçu en direct (sia-check --apercu) : bilan par niveau et ratios après les corrections du journal.</summary>
public sealed class BalancePreview
{
    [JsonPropertyName("levels")] public List<LevelBalance> Levels { get; init; } = [];
    [JsonPropertyName("ratios")] public List<Ratio> Ratios { get; init; } = [];
    [JsonPropertyName("corrections_log")] public List<CorrectionLogEntry> CorrectionsLog { get; init; } = [];
}

public sealed class LevelBalance
{
    [JsonPropertyName("building")] public string Building { get; init; } = "";
    [JsonPropertyName("level")] public string Level { get; init; } = "";
    [JsonPropertyName("rank")] public double? Rank { get; init; }
    [JsonPropertyName("values")] public Dictionary<string, double> Values { get; init; } = [];
    [JsonPropertyName("r1")] public CheckResult? R1 { get; init; }
    [JsonPropertyName("r3")] public CheckResult? R3 { get; init; }
    [JsonPropertyName("alerts")] public List<string> Alerts { get; init; } = [];
    /// <summary>Le même niveau sans les corrections ; null sans corrections appliquées.</summary>
    [JsonPropertyName("before")] public LevelBefore? Before { get; init; }

    public double Value(string code) => Values.TryGetValue(code, out var v) ? v : 0;
}

public sealed class CheckResult
{
    [JsonPropertyName("diff")] public double? Diff { get; init; }
    [JsonPropertyName("verdict")] public string Verdict { get; init; } = "";
}

public sealed class Issue
{
    [JsonPropertyName("key")] public string Key { get; init; } = "";
    [JsonPropertyName("rule")] public string Rule { get; init; } = "";
    [JsonPropertyName("verdict")] public string Verdict { get; init; } = "";
    [JsonPropertyName("building")] public string Building { get; init; } = "";
    [JsonPropertyName("level")] public string Level { get; init; } = "";
    [JsonPropertyName("lot")] public string? Lot { get; init; }
    [JsonPropertyName("category")] public string Category { get; init; } = "";
    [JsonPropertyName("expected")] public double? Expected { get; init; }
    [JsonPropertyName("obtained")] public double? Obtained { get; init; }
    [JsonPropertyName("diff_m2")] public double? DiffM2 { get; init; }
    [JsonPropertyName("diff_pct")] public double? DiffPct { get; init; }
    [JsonPropertyName("message")] public string Message { get; init; } = "";
    [JsonPropertyName("title")] public string? Title { get; init; }
    [JsonPropertyName("hint")] public string? Hint { get; init; }
    [JsonPropertyName("surface_ids")] public List<string> SurfaceIds { get; init; } = [];
}
