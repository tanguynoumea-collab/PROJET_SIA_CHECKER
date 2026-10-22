using System.IO;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.Json.Serialization;
using System.Text.RegularExpressions;

namespace SiaCheck.Viewer.Services;

public enum AiVerdictKind { Unknown, TrueIssue, ToConfirm, FalsePositive, Aggregate }

/// <summary>Verdict de la revue IA pour un point (format de .claude/skills/revue-ia/SKILL.md, étape 6).</summary>
public sealed class AiVerdict
{
    [JsonPropertyName("verdict_ia")] public string Verdict { get; set; } = "";
    [JsonPropertyName("sujet")] public string? Subject { get; set; }
    [JsonPropertyName("raison")] public string Reason { get; set; } = "";

    [JsonIgnore] public AiVerdictKind Kind => KindOf(Verdict);

    public static AiVerdictKind KindOf(string? verdict) => verdict?.Trim().ToLowerInvariant() switch
    {
        "vrai sujet" => AiVerdictKind.TrueIssue,
        "à confirmer" or "a confirmer" => AiVerdictKind.ToConfirm,
        "faux positif" => AiVerdictKind.FalsePositive,
        "agrégat" or "agregat" => AiVerdictKind.Aggregate,
        _ => AiVerdictKind.Unknown,
    };

    public static string Label(AiVerdictKind kind) => kind switch
    {
        AiVerdictKind.TrueIssue => "vrai sujet",
        AiVerdictKind.ToConfirm => "à confirmer",
        AiVerdictKind.FalsePositive => "faux positif",
        AiVerdictKind.Aggregate => "agrégat",
        _ => "inconnu",
    };
}

/// <summary>
/// Fichier <c>&lt;PROJET&gt;_&lt;date&gt;.verdicts.json</c>, clé = clé du point (règle|bâtiment|niveau|lot|catégorie).
/// Version 2 : bloc <c>sujets</c>, décisions de la revue sur les corrections de base, lu par le moteur
/// (<c>sia-check --revue</c>, sia_check.sujets.apply_review) ; l'app le conserve tel quel.
/// </summary>
public sealed class AiVerdictFile
{
    [JsonPropertyName("version")] public int Version { get; set; } = 1;
    [JsonPropertyName("projet")] public string Project { get; set; } = "";
    [JsonPropertyName("analyse")] public string AnalysisDate { get; set; } = "";
    [JsonPropertyName("revue_ia")] public string ReviewDate { get; set; } = "";
    [JsonPropertyName("modele")] public string Model { get; set; } = "";
    [JsonPropertyName("points")] public Dictionary<string, AiVerdict> Points { get; set; } = [];

    [JsonPropertyName("sujets"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public JsonObject? Subjects { get; set; }
}

/// <summary>Une revue IA trouvée sur disque : verdicts, et rapport markdown s'il est à côté.</summary>
public sealed record AiReview(string VerdictsPath, AiVerdictFile Data)
{
    public string? ReportPath => File.Exists(Path.ChangeExtension(Path.ChangeExtension(VerdictsPath, null), ".md"))
        ? Path.ChangeExtension(Path.ChangeExtension(VerdictsPath, null), ".md") : null;

    public AiVerdict? Get(string key) => Data.Points.GetValueOrDefault(key);
}

/// <summary>Lecture et écriture des revues IA : <c>docs/revue-ia/</c> du dépôt, ou dossier de l'application.</summary>
public static partial class AiReviewFiles
{
    private static readonly JsonSerializerOptions Options = new()
    {
        WriteIndented = true,
        Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping,   // accents lisibles
    };

    [GeneratedRegex(@"_(\d{4}-\d{2}-\d{2})\.verdicts\.json$", RegexOptions.IgnoreCase)]
    private static partial Regex DatedVerdicts();

    /// <summary>« L OREE » → « L_OREE » : même règle que les fichiers écrits à la main dans docs/revue-ia.</summary>
    public static string Prefix(string projectName) =>
        new(projectName.Trim().Select(c => char.IsLetterOrDigit(c) ? c : '_').ToArray());

    public static AiVerdictFile Load(string path)
    {
        using var s = File.OpenRead(path);
        var f = JsonSerializer.Deserialize<AiVerdictFile>(s, Options)
                ?? throw new InvalidDataException($"{path} : fichier vide.");
        if (f.Points.Count == 0) throw new InvalidDataException($"{path} : aucun verdict.");
        return f;
    }

    /// <summary>
    /// Revue la plus récente pour ce projet, cherchée dans les dossiers donnés (le premier gagne à date égale).
    /// Un fichier d'un autre projet, ou illisible, est ignoré.
    /// </summary>
    public static AiReview? FindLatest(string projectName, IEnumerable<string> dirs)
    {
        var prefix = Prefix(projectName);
        var candidates = dirs.Where(Directory.Exists).SelectMany((d, rank) =>
                Directory.GetFiles(d, $"{prefix}_*.verdicts.json")
                    .Select(p => (FilePath: p, Rank: rank, Match: DatedVerdicts().Match(Path.GetFileName(p))))
                    .Where(c => c.Match.Success && Path.GetFileName(c.FilePath).Length == prefix.Length + c.Match.Length))
            .OrderByDescending(c => c.Match.Groups[1].Value, StringComparer.Ordinal)
            .ThenBy(c => c.Rank);
        foreach (var c in candidates)
        {
            try
            {
                var f = Load(c.FilePath);
                if (Prefix(f.Project).Equals(prefix, StringComparison.OrdinalIgnoreCase)) return new AiReview(c.FilePath, f);
            }
            catch (Exception ex) when (ex is IOException or JsonException or InvalidDataException) { /* suivant */ }
        }
        return null;
    }

    /// <summary>Écrit rapport et verdicts côte à côte ; renvoie la revue relue depuis le disque.</summary>
    public static AiReview Save(string dir, string projectName, string date, string reportMarkdown, AiVerdictFile verdicts)
    {
        Directory.CreateDirectory(dir);
        var stem = Path.Combine(dir, $"{Prefix(projectName)}_{date}");
        File.WriteAllText(stem + ".md", reportMarkdown);
        var tmp = stem + ".verdicts.json.tmp";
        File.WriteAllText(tmp, JsonSerializer.Serialize(verdicts, Options));
        File.Move(tmp, stem + ".verdicts.json", overwrite: true);
        return new AiReview(stem + ".verdicts.json", verdicts);
    }

    /// <summary>
    /// Dossiers où chercher : celui de l'application, puis <c>docs/revue-ia</c> du dépôt quand l'app tourne
    /// depuis une copie de travail (revues faites dans Claude Code).
    /// </summary>
    public static IEnumerable<string> SearchDirs(string appReviewDir, string appBaseDir)
    {
        yield return appReviewDir;
        for (var d = new DirectoryInfo(appBaseDir); d is not null; d = d.Parent)
        {
            var docs = Path.Combine(d.FullName, "docs", "revue-ia");
            if (Directory.Exists(docs)) { yield return docs; yield break; }
        }
    }
}
