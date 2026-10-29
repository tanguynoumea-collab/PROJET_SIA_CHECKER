using System.IO;

namespace SiaCheck.Viewer.Services;

/// <summary>
/// Fiche projet (docs/DESIGN_PLAN.md, Évolutions 3.8 et 4.5) : l'identité HRS et la source des données, saisies à la
/// création du projet et modifiables à tout moment ; l'export MDP reprend l'identité sans rien redemander.
/// Source Treegram : <see cref="Folder"/> est le dossier du .tgm. Source IFC (<see cref="Ifc"/>) : à la création,
/// <see cref="OutDir"/> est le dossier des projets générés (le projet y prend son nom) ; ensuite, <see cref="Folder"/>
/// est le dossier généré et la maquette reste en lecture seule.
/// </summary>
public sealed record ProjectSheet(string Folder, MdpProject Identity)
{
    public string? Ifc { get; init; }
    public string? OutDir { get; init; }
    public bool IsIfc => Ifc is not null;
}

/// <summary>Ce que la fiche affiche sous ses champs : état du dossier, ID déjà pris ; <see cref="CanSave"/> = bouton actif.</summary>
public sealed record SheetCheck(string FolderMessage, bool FolderOk, bool FolderWarning, string? IdWarning)
{
    public bool CanSave => FolderOk;
}

/// <summary>
/// Contrôle d'un dossier de projet : un seul fichier source, .tgm (Treegram, cache VWR facultatif) ou .siagen.json
/// (projet généré depuis un IFC, géométrie comprise ; docs/V4_PLAN.md §3.2).
/// </summary>
public static class ProjectFolder
{
    public const string SiagenSuffix = ".siagen.json";

    public static string[] Sources(string dir) => Directory.Exists(dir)
        ? [.. Directory.GetFiles(dir, "*.tgm"), .. Directory.GetFiles(dir, "*" + SiagenSuffix)]
        : [];

    public static bool IsSiagen(string path) => path.EndsWith(SiagenSuffix, StringComparison.OrdinalIgnoreCase);

    /// <summary>Nom du projet d'un fichier source : « L OREE » pour « L OREE.tgm » comme pour « L OREE.siagen.json ».</summary>
    public static string ProjectName(string path) =>
        IsSiagen(path) ? Path.GetFileName(path)[..^SiagenSuffix.Length] : Path.GetFileNameWithoutExtension(path);

    public static SheetCheck Check(string dir)
    {
        if (string.IsNullOrWhiteSpace(dir)) return new("Choisissez le dossier du projet Treegram.", false, false, null);
        if (!Directory.Exists(dir)) return new("Dossier introuvable.", false, false, null);
        var sources = Sources(dir);
        if (sources.Length == 0) return new("Aucun fichier .tgm (ni .siagen.json) dans ce dossier.", false, false, null);
        if (sources.Length > 1) return new($"{sources.Length} fichiers .tgm ou .siagen.json : un seul attendu.", false, false, null);
        var tgm = Path.GetFileName(sources[0]);
        if (IsSiagen(tgm)) return new($"✓ {tgm} · projet généré, géométrie comprise", true, false, null);
        return Directory.Exists(Path.Combine(dir, "VWR"))
            ? new($"✓ {tgm} · cache VWR présent", true, false, null)
            : new($"{tgm} · pas de cache VWR : l'analyse se fera sans 3D.", true, true, null);
    }

    public static bool Same(string a, string b) =>
        a.Length > 0 && b.Length > 0 && string.Equals(Normalize(a), Normalize(b), StringComparison.OrdinalIgnoreCase);

    public static string Normalize(string path) => Path.TrimEndingDirectorySeparator(Path.GetFullPath(path));
}
