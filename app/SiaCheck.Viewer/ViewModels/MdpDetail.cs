using SiaCheck.Viewer.Services;

namespace SiaCheck.Viewer.ViewModels;

/// <summary>Un point de la page d'un MDP : présent ou non, sa valeur ou son détail, et ce qu'il apporte au benchmark.</summary>
public sealed record DetailPoint(string Label, string Value, bool Ok, bool Required, string Note)
{
    /// <summary>Glyphe : conforme, ou manquant (erreur si requis, alerte sinon).</summary>
    public string Verdict => Ok ? "OK" : Required ? "ERREUR" : "ALERTE";
}

/// <summary>
/// Page d'un MDP de la base (accueil, clic sur une ligne) : son identité d'abord, à remplir en priorité, puis chaque
/// contrôle des données avec ce qui manque et ce que cela coûte au benchmark.
/// </summary>
public sealed class MdpDetail
{
    public MdpDetail(BenchmarkItem item)
    {
        Item = item;
        var p = item.Project;
        Title = $"{p.Id} · {p.Name}";
        File = p.File;
        IsReliable = p.Reliable;
        Status = p.Reliable
            ? "Dans les références du benchmark : SP ≥ SN et part de construction plausible."
            : $"Écarté des références : {BenchmarkItem.RejectReason(p)}";

        string Info(string key) => p.Info(key) is { Length: > 0 } v ? (v.EndsWith(".0") ? v[..^2] : v) : "";
        DetailPoint Field(string label, string value, bool required, string note) =>
            new(label, value.Length > 0 ? value : "à renseigner", value.Length > 0, required, note);
        Identity =
        [
            Field("ID projet HRS", p.Id, true, "Relie toutes les tables du MDP."),
            Field("Nom du projet", p.Name, true, "Nom affiché dans le benchmark."),
            Field("Typologie", Info("categorie"), true, "Première sélection du benchmark : sans elle, le projet n'apparaît que dans « Toutes »."),
            Field("Canton", Info("canton"), true, "Deuxième sélection du benchmark."),
            Field("Type d'intervention", Info("intervention"), true, "Sélection du benchmark (neuf, rénovation…)."),
            Field("Commune", Info("commune"), false, "Facultatif."),
            Field("Phase SIA", Info("phase"), false, "Facultatif."),
        ];
        IdentityMissing = Identity.Count(d => d.Required && !d.Ok);

        // L'identité a sa propre section : le contrôle « infos » n'est pas répété
        Data = p.Checks.Where(c => c.Id != "infos").Select(c => new DetailPoint(
            c.Label, c.Ok ? (c.Detail.Length > 0 ? c.Detail : "présent") : c.Detail.Length > 0 ? c.Detail : "manquant",
            c.Ok, BenchmarkItem.Required.Contains(c.Id), Consequence(c.Id))).ToList();
        DataMissing = Data.Count(d => !d.Ok);
    }

    public BenchmarkItem Item { get; }
    public string Title { get; }
    public string File { get; }
    public bool IsReliable { get; }
    public string Status { get; }
    public IReadOnlyList<DetailPoint> Identity { get; }
    public int IdentityMissing { get; }
    public bool HasIdentityMissing => IdentityMissing > 0;
    public string IdentityHeader => IdentityMissing == 0
        ? "Identité du projet : complète"
        : $"Identité du projet : à remplir en priorité ({IdentityMissing} champ{(IdentityMissing > 1 ? "s" : "")} manquant{(IdentityMissing > 1 ? "s" : "")})";
    public IReadOnlyList<DetailPoint> Data { get; }
    public int DataMissing { get; }
    public string DataHeader => DataMissing == 0 ? "Données du MDP : toutes présentes" : $"Données du MDP : {DataMissing} point{(DataMissing > 1 ? "s" : "")} à revoir";

    /// <summary>Ce qu'apporte chaque contrôle (benchmark.py, _controles) : ce que son absence retire au benchmark.</summary>
    private static string Consequence(string id) => id switch
    {
        "brutes" => "Base de tous les ratios (dénominateur SP).",
        "decoupage" => "Ratios hors-sol : SUP / SP hors-sol, circulations, façade / SP hors-sol.",
        "nettes" => "SUP, SUS, SD, SI : rendement et pertes.",
        "coherence" => "Requis : sans lui, le projet est écarté des références.",
        "plausible" => "Requis : sans lui, le projet est écarté des références.",
        "logements" => "SUP par logement, SP hors-sol par logement, similarité par nombre de logements.",
        "chambres" => "Onglet Typologies : SUP par nombre de chambres.",
        "uspi" => "SVN / SP hors-sol et chiffre d'affaires du Programmer.",
        "enveloppe" => "Vitrée / pleine, part vitrée, façade / SP hors-sol.",
        _ => "",
    };
}
