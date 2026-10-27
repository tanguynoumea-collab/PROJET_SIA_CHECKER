using System.IO;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace SiaCheck.Viewer.Services;

/// <summary>Contrôle de fiabilité d'un MDP (sia_check.benchmark._controles), dans l'ordre du moteur.</summary>
public sealed class BenchmarkCheck
{
    [JsonPropertyName("id")] public string Id { get; set; } = "";
    [JsonPropertyName("label")] public string Label { get; set; } = "";
    [JsonPropertyName("ok")] public bool Ok { get; set; }
    [JsonPropertyName("detail")] public string Detail { get; set; } = "";
}

public sealed class BenchmarkProject
{
    [JsonPropertyName("id")] public string Id { get; set; } = "";
    [JsonPropertyName("nom")] public string Name { get; set; } = "";
    [JsonPropertyName("fichier")] public string File { get; set; } = "";
    [JsonPropertyName("infos")] public Dictionary<string, JsonElement> Infos { get; set; } = [];
    [JsonPropertyName("score")] public double Score { get; set; }
    /// <summary>Admis dans les références (SP et SN cohérentes).</summary>
    [JsonPropertyName("fiable")] public bool Reliable { get; set; }
    [JsonPropertyName("controles")] public List<BenchmarkCheck> Checks { get; set; } = [];

    public string? Info(string key) =>
        Infos.TryGetValue(key, out var v) && v.ValueKind is JsonValueKind.String or JsonValueKind.Number ? v.ToString() : null;
}

/// <summary>benchmark.json, écrit par <c>sia-check --benchmark</c> ; seuls les champs de l'accueil sont lus ici.</summary>
public sealed class BenchmarkData
{
    [JsonPropertyName("genere")] public DateTime Generated { get; set; }
    [JsonPropertyName("projets")] public List<BenchmarkProject> Projects { get; set; } = [];
    [JsonPropertyName("erreurs")] public List<string> Errors { get; set; } = [];
    /// <summary>Listes déroulantes de la fiche « Identité du projet », lues dans le gabarit MDP par le moteur.</summary>
    [JsonPropertyName("listes")] public Dictionary<string, List<string>>? Lists { get; set; }
}

public static class BenchmarkBase
{
    /// <summary>Le benchmark lu, null s'il n'existe pas ou est illisible (il sera régénéré).</summary>
    public static BenchmarkData? Load(string path)
    {
        try
        {
            if (!System.IO.File.Exists(path)) return null;
            using var s = System.IO.File.OpenRead(path);
            return JsonSerializer.Deserialize<BenchmarkData>(s);
        }
        catch (Exception ex) when (ex is JsonException or IOException)
        {
            return null;
        }
    }

    public static IEnumerable<string> MdpFiles(string folder) =>
        Directory.Exists(folder)
            ? Directory.EnumerateFiles(folder, "MDP*.xlsx").Where(f => !Path.GetFileName(f).StartsWith("~$"))
            : [];

    /// <summary>
    /// Le benchmark est à refaire si un MDP est plus récent que lui, ou si le dossier a changé depuis (fichier ajouté,
    /// retiré ou renommé : la date du dossier bouge).
    /// </summary>
    public static bool IsStale(string folder, string json)
    {
        if (!System.IO.File.Exists(json)) return true;
        var built = System.IO.File.GetLastWriteTime(json);
        return Directory.GetLastWriteTime(folder) > built || MdpFiles(folder).Any(f => System.IO.File.GetLastWriteTime(f) > built);
    }

    /// <summary>MDP déjà dans la base pour cet ID projet (« MDP-1778-… », « MDP-1778.00_… »), à remplacer plutôt qu'à doubler.</summary>
    public static string? FindById(string folder, string id) =>
        MdpFiles(folder).FirstOrDefault(f =>
            System.Text.RegularExpressions.Regex.Match(Path.GetFileName(f), @"^MDP-(\d+)") is { Success: true } m &&
            m.Groups[1].Value == id.Trim());
}
