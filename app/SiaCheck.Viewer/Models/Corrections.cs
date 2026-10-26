using System.Text.Json;
using System.Text.Json.Serialization;

namespace SiaCheck.Viewer.Models;

/// <summary>
/// Sujet : points d'attention regroupés par cause, avec ses corrections proposées
/// (src/sia_check/sujets.py, réorienté par la revue IA avec <c>sia-check --revue</c>).
/// </summary>
public sealed class Subject
{
    [JsonPropertyName("id")] public string Id { get; init; } = "";
    [JsonPropertyName("titre")] public string Title { get; init; } = "";
    [JsonPropertyName("cause")] public string Cause { get; init; } = "";
    /// <summary>corriger | aucune | à vérifier</summary>
    [JsonPropertyName("action")] public string Action { get; init; } = "";
    [JsonPropertyName("certitude")] public string? Certainty { get; init; }
    [JsonPropertyName("explication")] public string Explanation { get; init; } = "";
    /// <summary>ia | absent (règle)</summary>
    [JsonPropertyName("origine")] public string? Origin { get; init; }
    [JsonPropertyName("points")] public List<string> Points { get; init; } = [];
    [JsonPropertyName("m2")] public double M2 { get; init; }
    [JsonPropertyName("corrections")] public List<Correction> Corrections { get; init; } = [];
}

/// <summary>
/// Correction au format du journal (src/sia_check/corrections.py). Les champs inconnus de l'app
/// (polygone, base…) sont conservés tels quels : le journal les rend au moteur sans perte.
/// </summary>
public sealed class Correction
{
    public const string Proposed = "proposée";
    public const string Accepted = "acceptée";
    public const string Rejected = "rejetée";

    [JsonPropertyName("id")] public string Id { get; set; } = "";
    /// <summary>reclasser | exclure | découper | ajuster | affecter</summary>
    [JsonPropertyName("op")] public string Op { get; set; } = "";
    /// <summary>Absente pour « créer » (la nouvelle surface porte son `niveau`) : non écrite.</summary>
    [JsonPropertyName("cible"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingDefault)] public JsonElement Target { get; set; }
    [JsonPropertyName("vers"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] public string? To { get; set; }
    [JsonPropertyName("aire"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] public double? Area { get; set; }
    [JsonPropertyName("affectation"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] public string? Assignment { get; set; }
    [JsonPropertyName("explication")] public string Explanation { get; set; } = "";
    [JsonPropertyName("sujet"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] public string? Subject { get; set; }
    /// <summary>règle | ia | manuel</summary>
    [JsonPropertyName("origine")] public string Origin { get; set; } = "";
    [JsonPropertyName("statut")] public string Status { get; set; } = Proposed;
    /// <summary>Surface en jeu (m²), calculée par le moteur.</summary>
    [JsonPropertyName("m2"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] public double? M2 { get; set; }
    [JsonPropertyName("trace"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] public TraceMesh? Trace { get; set; }
    [JsonPropertyName("a_retracer"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingDefault)] public bool NeedsRetrace { get; set; }

    [JsonExtensionData] public Dictionary<string, JsonElement>? Extra { get; set; }

    /// <summary>Identifiants de surface visés (cible.ids), vide pour une sélection.</summary>
    [JsonIgnore]
    public IReadOnlyList<string> TargetIds =>
        Target.ValueKind == JsonValueKind.Object && Target.TryGetProperty("ids", out var ids) && ids.ValueKind == JsonValueKind.Array
            ? ids.EnumerateArray().Select(i => i.ToString()).ToList() : [];

    public Correction Clone() => JsonSerializer.Deserialize<Correction>(JsonSerializer.Serialize(this))!;

    /// <summary>Ce que le moteur applique : deux corrections de même signature produisent le même résultat.</summary>
    [JsonIgnore]
    public string Signature =>
        // Cible ré-sérialisée : le texte brut dépend de qui a écrit le journal (espaces, ordre d'origine).
        $"{Status}|{Op}|{(Target.ValueKind == JsonValueKind.Undefined ? "" : JsonSerializer.Serialize(Target))}|{To}|" +
        $"{Area?.ToString("R", System.Globalization.CultureInfo.InvariantCulture)}|{Assignment}";
}

/// <summary>Tracé triangulé à plat (sujets._trace) : sommets x, y et triangles, à l'altitude z.</summary>
public sealed class TraceMesh
{
    [JsonPropertyName("z")] public double Z { get; set; }
    [JsonPropertyName("v")] public double[] Vertices { get; set; } = [];
    [JsonPropertyName("i")] public int[] Indices { get; set; } = [];
}

/// <summary>Application d'une correction par le moteur (corrections.apply, journal).</summary>
public sealed class CorrectionLogEntry
{
    public const string Applied = "appliquée";

    [JsonPropertyName("id")] public string Id { get; init; } = "";
    [JsonPropertyName("statut")] public string? Status { get; init; }
    /// <summary>appliquée | cible introuvable | refusée | non acceptée</summary>
    [JsonPropertyName("application")] public string Application { get; init; } = "";
    [JsonPropertyName("surfaces")] public int Surfaces { get; init; }
    [JsonPropertyName("m2")] public double M2 { get; init; }
    [JsonPropertyName("raison")] public string Reason { get; init; } = "";
}

/// <summary>Bilan de la fusion de la revue IA (sujets.apply_review).</summary>
public sealed class ReviewInfo
{
    [JsonPropertyName("date")] public string? Date { get; init; }
    [JsonPropertyName("modele")] public string? Model { get; init; }
    [JsonPropertyName("decisions")] public int Decisions { get; init; }
    [JsonPropertyName("problemes")] public List<ReviewProblem> Problems { get; init; } = [];
}

public sealed class ReviewProblem
{
    [JsonPropertyName("sujet")] public string? Subject { get; init; }
    [JsonPropertyName("id")] public string? Id { get; init; }
    [JsonPropertyName("raison")] public string Reason { get; init; } = "";
}

/// <summary>Bilan d'un niveau sans les corrections (fichier analysé avec <c>--corrections</c>).</summary>
public sealed class LevelBefore
{
    [JsonPropertyName("values")] public Dictionary<string, double> Values { get; init; } = [];
    [JsonPropertyName("r1")] public CheckResult? R1 { get; init; }
    [JsonPropertyName("r3")] public CheckResult? R3 { get; init; }

    public double Value(string code) => Values.TryGetValue(code, out var v) ? v : 0;
}
