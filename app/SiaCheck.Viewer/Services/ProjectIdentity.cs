using System.IO;
using System.Text.Json;

namespace SiaCheck.Viewer.Services;

/// <summary>Usage de la fiche « Identité du projet » : ce qui est obligatoire, ce qui est modifiable.</summary>
public enum IdentityMode
{
    /// <summary>Export MDP de travail : seul l'ID est obligatoire.</summary>
    Export,
    /// <summary>Ajouter à la base : tous les champs nécessaires au benchmark sont obligatoires.</summary>
    Base,
    /// <summary>MDP déjà dans la base : l'ID (qui relie ses tables) ne change pas, rien n'est obligatoire.</summary>
    EditBase,
}

/// <summary>Listes déroulantes de la fiche « Identité du projet » (feuille « Listes formulaire » du gabarit MDP).</summary>
public sealed class IdentityLists
{
    public IReadOnlyList<string> Typologies { get; init; } = [];
    public IReadOnlyList<string> Cantons { get; init; } = [];
    public IReadOnlyList<string> Interventions { get; init; } = [];
    public IReadOnlyList<string> Phases { get; init; } = [];

    /// <summary>
    /// Copie des listes du gabarit livré, utilisée tant que la base n'a pas été lue : le moteur les transmet ensuite
    /// avec benchmark.json (<c>listes</c>), qui font foi.
    /// </summary>
    public static IdentityLists Default { get; } = new()
    {
        Typologies = ["Logement (100-90% SU)", "Logement Mixte (>10% autres affectations)", "Activités (Bureaux, Artisanat, Commerce)",
                      "Industriel", "Ecole", "Hôtel", "Sport", "EMS", "Santé", "Centre commercial", "Autre"],
        Cantons = ["AG", "AR", "AI", "BL", "BS", "BE", "FR", "GE", "GL", "GR", "JU", "LU", "NE", "NW", "OW", "SH", "SZ", "SO",
                   "SG", "TG", "TI", "UR", "VS", "VD", "ZG", "ZH"],
        Interventions = ["Renovation", "Nouvelle construction", "Reno et nouvelle construction", "Demolition"],
        Phases = ["21", "31", "32", "33", "41", "51", "52", "53"],
    };

    public static IdentityLists From(Dictionary<string, List<string>>? listes) =>
        listes is null ? Default : new()
        {
            Typologies = Pick(listes, ProjectIdentity.Typologie, Default.Typologies),
            Cantons = Pick(listes, ProjectIdentity.Canton, Default.Cantons),
            Interventions = Pick(listes, ProjectIdentity.Intervention, Default.Interventions),
            Phases = Pick(listes, ProjectIdentity.Phase, Default.Phases),
        };

    private static IReadOnlyList<string> Pick(Dictionary<string, List<string>> l, string key, IReadOnlyList<string> fallback) =>
        l.TryGetValue(key, out var v) && v.Count > 0 ? v : fallback;
}

/// <summary>
/// Identité d'un projet telle que le MDP la porte (feuille InfosProjet) : ce qui permet de le sélectionner dans le
/// benchmark (typologie, canton…). Clés = descriptions de InfosProjet, comme le moteur les attend (<c>--identite</c>).
/// </summary>
public static class ProjectIdentity
{
    public const string Id = "ID projet", Nom = "Nom Projet HRS", Canton = "Canton", Commune = "Commune",
                        Typologie = "Categorie d'Ouvrage", Intervention = "Type d'intervention", Phase = "Phase du projet";

    /// <summary>Champs nécessaires pour entrer dans le benchmark (fiche marquée *).</summary>
    public static IReadOnlyList<(string Key, string Label)> RequiredForBase { get; } =
        [(Id, "ID projet HRS"), (Nom, "nom du projet"), (Typologie, "typologie"), (Canton, "canton"), (Intervention, "type d'intervention")];

    public static List<string> Missing(MdpProject p, bool forBase)
    {
        var values = Values(p);
        var required = forBase ? RequiredForBase : RequiredForBase.Take(1);
        return required.Where(r => string.IsNullOrWhiteSpace(values[r.Key])).Select(r => r.Label).ToList();
    }

    public static Dictionary<string, string> Values(MdpProject p) => new()
    {
        [Id] = p.Id, [Nom] = p.Name, [Canton] = p.Canton, [Commune] = p.Commune, [Typologie] = p.Typologie,
        [Intervention] = p.Intervention, [Phase] = p.Phase,
    };

    /// <summary>La fiche écrite pour le moteur ; les champs vides n'effacent rien dans le MDP.</summary>
    public static string WriteEngineFile(MdpProject p, string path)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        File.WriteAllText(path, JsonSerializer.Serialize(Values(p).Where(kv => !string.IsNullOrWhiteSpace(kv.Value))
                                                                  .ToDictionary(kv => kv.Key, kv => kv.Value.Trim())));
        return path;
    }

    /// <summary>Libellé court d'une typologie pour les listes (« Logement », « Log. mixte »…).</summary>
    public static string Short(string? typologie) => typologie switch
    {
        null or "" => "Non identifié",
        var t when t.StartsWith("Logement Mixte", StringComparison.OrdinalIgnoreCase) => "Log. mixte",
        var t when t.StartsWith("Logement", StringComparison.OrdinalIgnoreCase) => "Logement",
        var t when t.StartsWith("Activit", StringComparison.OrdinalIgnoreCase) => "Activités",
        var t => t,
    };
}
