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
}

public sealed class MeshData
{
    [JsonPropertyName("v")] public float[] Vertices { get; init; } = [];
    [JsonPropertyName("i")] public int[] Indices { get; init; } = [];
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

public sealed class LevelBalance
{
    [JsonPropertyName("building")] public string Building { get; init; } = "";
    [JsonPropertyName("level")] public string Level { get; init; } = "";
    [JsonPropertyName("rank")] public double? Rank { get; init; }
    [JsonPropertyName("values")] public Dictionary<string, double> Values { get; init; } = [];
    [JsonPropertyName("r1")] public CheckResult? R1 { get; init; }
    [JsonPropertyName("r3")] public CheckResult? R3 { get; init; }
    [JsonPropertyName("alerts")] public List<string> Alerts { get; init; } = [];

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
