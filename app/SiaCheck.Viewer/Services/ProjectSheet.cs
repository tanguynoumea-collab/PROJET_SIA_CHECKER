using System.IO;

namespace SiaCheck.Viewer.Services;

/// <summary>
/// Fiche projet (docs/DESIGN_PLAN.md, Évolution 3.8) : le dossier Treegram et l'identité HRS, saisis à la création du
/// projet et modifiables à tout moment ; l'export MDP reprend l'identité sans rien redemander.
/// </summary>
public sealed record ProjectSheet(string Folder, MdpProject Identity);

/// <summary>Ce que la fiche affiche sous ses champs : état du dossier, ID déjà pris ; <see cref="CanSave"/> = bouton actif.</summary>
public sealed record SheetCheck(string FolderMessage, bool FolderOk, bool FolderWarning, string? IdWarning)
{
    public bool CanSave => FolderOk;
}

/// <summary>Contrôle d'un dossier de projet Treegram : un seul .tgm, cache VWR facultatif.</summary>
public static class ProjectFolder
{
    public static string[] Tgms(string dir) => Directory.Exists(dir) ? Directory.GetFiles(dir, "*.tgm") : [];

    public static SheetCheck Check(string dir)
    {
        if (string.IsNullOrWhiteSpace(dir)) return new("Choisissez le dossier du projet Treegram.", false, false, null);
        if (!Directory.Exists(dir)) return new("Dossier introuvable.", false, false, null);
        var tgms = Tgms(dir);
        if (tgms.Length == 0) return new("Aucun fichier .tgm dans ce dossier.", false, false, null);
        if (tgms.Length > 1) return new($"{tgms.Length} fichiers .tgm : un seul attendu.", false, false, null);
        var tgm = Path.GetFileName(tgms[0]);
        return Directory.Exists(Path.Combine(dir, "VWR"))
            ? new($"✓ {tgm} · cache VWR présent", true, false, null)
            : new($"{tgm} · pas de cache VWR : l'analyse se fera sans 3D.", true, true, null);
    }

    public static bool Same(string a, string b) =>
        a.Length > 0 && b.Length > 0 && string.Equals(Normalize(a), Normalize(b), StringComparison.OrdinalIgnoreCase);

    public static string Normalize(string path) => Path.TrimEndingDirectorySeparator(Path.GetFullPath(path));
}
