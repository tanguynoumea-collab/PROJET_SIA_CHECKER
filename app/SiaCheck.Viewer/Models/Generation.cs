using System.IO;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace SiaCheck.Viewer.Models;

/// <summary>
/// Projet généré depuis l'IFC (V4, docs/DESIGN_PLAN.md Évolution 4.0) : ce que l'app lit des fichiers du moteur,
/// sans jamais les écrire (generation/rapport.json, generation/decisions.json, generation/maquette.json).
/// </summary>
public sealed class GenerationReport
{
    [JsonPropertyName("project")] public string Project { get; init; } = "";
    [JsonPropertyName("date")] public string Date { get; init; } = "";
    [JsonPropertyName("source")] public string Source { get; init; } = "";
    [JsonPropertyName("spaces")] public List<GeneratedSpace> Spaces { get; init; } = [];

    public static string PathOf(string dir) => Path.Combine(dir, "generation", "rapport.json");
    public static bool Exists(string dir) => File.Exists(PathOf(dir));
    public static GenerationReport Load(string dir) =>
        JsonSerializer.Deserialize<GenerationReport>(File.ReadAllText(PathOf(dir))) ?? new GenerationReport();
}

public sealed class GeneratedSpace
{
    public const double Sure = 0.8;   // engine.SURE : en dessous, décision à confirmer

    [JsonPropertyName("gid")] public string Gid { get; init; } = "";
    [JsonPropertyName("name")] public string? Name { get; init; }
    [JsonPropertyName("long_name")] public string? LongName { get; init; }
    [JsonPropertyName("level")] public string? Level { get; init; }
    [JsonPropertyName("storey")] public string? Storey { get; init; }
    [JsonPropertyName("lot")] public string? Lot { get; init; }
    [JsonPropertyName("in_lot")] public bool InLot { get; init; }
    [JsonPropertyName("nature")] public string Nature { get; init; } = "";
    [JsonPropertyName("code")] public string? Code { get; init; }
    [JsonPropertyName("type")] public string? Type { get; init; }
    [JsonPropertyName("source")] public string? Source { get; init; }
    [JsonPropertyName("confidence")] public double Confidence { get; init; }
    [JsonPropertyName("reason")] public string Reason { get; init; } = "";
    [JsonPropertyName("conflicts")] public List<string> Conflicts { get; init; } = [];
    [JsonPropertyName("area")] public double? Area { get; init; }
    [JsonPropertyName("area_plan")] public double? AreaPlan { get; init; }
    [JsonPropertyName("neighbours")] public List<string> Neighbours { get; init; } = [];
    [JsonPropertyName("surface")] public string? Surface { get; init; }

    /// <summary>Pièce ou extérieur : ce que l'analyse IA et les décisions classent (pas les contours, sites…).</summary>
    public bool IsClassified => Nature is "piece" or "exterieur";
    /// <summary>Les règles hésitent : même critère que les questions de l'analyse IA (generation/ia.py).</summary>
    public bool IsDoubtful => IsClassified && (Confidence < Sure || Conflicts.Count > 0 || Source is null);
    public string Label => string.Join(" / ", new[] { Name, LongName }.Where(s => !string.IsNullOrWhiteSpace(s)));
}

/// <summary>Décision du journal (generation/journal.py) : IA ou manuelle.</summary>
public sealed class GenerationDecision
{
    [JsonPropertyName("id")] public string Id { get; init; } = "";
    [JsonPropertyName("origine")] public string Origin { get; init; } = "";
    [JsonPropertyName("statut")] public string Status { get; init; } = "";
    [JsonPropertyName("code")] public string Code { get; init; } = "";
    [JsonPropertyName("type")] public string? Type { get; init; }
    [JsonPropertyName("certitude")] public string? Certainty { get; init; }
    [JsonPropertyName("raison")] public string? Reason { get; init; }

    public bool IsOpenProposal => Status == "proposée";
    public bool IsAccepted => Status == "acceptée";
    /// <summary>Tranchée : plus rien à décider sur l'espace (acceptée, rejetée, ou classement des règles confirmé).</summary>
    public bool IsSettled => Status is "acceptée" or "rejetée" or "confirmée";

    private sealed class File_
    {
        [JsonPropertyName("decisions")] public List<GenerationDecision> Decisions { get; init; } = [];
    }

    public static string PathOf(string dir) => Path.Combine(dir, "generation", "decisions.json");

    public static List<GenerationDecision> Load(string dir) =>
        File.Exists(PathOf(dir)) ? JsonSerializer.Deserialize<File_>(File.ReadAllText(PathOf(dir)))?.Decisions ?? [] : [];
}

/// <summary>Où en est la décision d'un projet généré (accueil, onglet Espaces).</summary>
public sealed record GenerationState(int ToDecide, int Proposals, int ToApply)
{
    public static GenerationState Of(GenerationReport report, IReadOnlyList<GenerationDecision> decisions)
    {
        var by = decisions.GroupBy(d => d.Id).ToDictionary(g => g.Key, g => g.Last());
        var spaces = report.Spaces.ToDictionary(s => s.Gid);
        var toDecide = report.Spaces.Count(s => s.IsDoubtful && !(by.GetValueOrDefault(s.Gid)?.IsSettled ?? false));
        var proposals = by.Values.Count(d => d.IsOpenProposal);
        // acceptée mais pas encore appliquée : le rapport (dernière génération) dit encore autre chose
        var toApply = by.Values.Count(d => d.IsAccepted && spaces.GetValueOrDefault(d.Id) is { } s
                                           && (s.Code != d.Code || d.Type is not null && s.Type != d.Type));
        return new GenerationState(toDecide, proposals, toApply);
    }
}

/// <summary>Murs, dalles, toits, poteaux de la maquette (calque « Maquette IFC »), en repère local.</summary>
public sealed class ContextModel
{
    public sealed record Element(string Building, string Level, float[] Vertices, int[] Indices);

    public List<Element> Elements { get; } = [];

    public static string PathOf(string dir) => Path.Combine(dir, "generation", "maquette.json");

    public static ContextModel? Load(string dir)
    {
        if (!File.Exists(PathOf(dir))) return null;
        using var doc = JsonDocument.Parse(File.ReadAllText(PathOf(dir)));
        var m = new ContextModel();
        foreach (var e in doc.RootElement.GetProperty("elements").EnumerateArray())
        {
            if (e.GetProperty("level").GetString() is not { } level || e.GetProperty("building").GetString() is not { } b) continue;
            var v = Convert.FromBase64String(e.GetProperty("v").GetString() ?? "");
            var i = Convert.FromBase64String(e.GetProperty("i").GetString() ?? "");
            var floats = new float[v.Length / 4];
            Buffer.BlockCopy(v, 0, floats, 0, floats.Length * 4);
            var ints = new int[i.Length / 4];
            Buffer.BlockCopy(i, 0, ints, 0, ints.Length * 4);
            m.Elements.Add(new Element(b, level, floats, ints));
        }
        return m;
    }
}
