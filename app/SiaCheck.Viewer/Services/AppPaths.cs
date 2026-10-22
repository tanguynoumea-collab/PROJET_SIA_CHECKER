using System.IO;
using System.Security.Cryptography;
using System.Text;

namespace SiaCheck.Viewer.Services;

/// <summary>Emplacements des fichiers de l'application, par projet Treegram.</summary>
public sealed class AppPaths(string roamingRoot, string localRoot)
{
    public static AppPaths Default { get; } = new(
        Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "SiaCheckViewer"),
        Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "SiaCheckViewer"));

    public string SettingsFile => Path.Combine(roamingRoot, "settings.json");

    /// <summary>Statuts et commentaires : suivent l'utilisateur (profil itinérant).</summary>
    public string ReviewFile(string projectDir) => Path.Combine(roamingRoot, "reviews", $"{Slug(projectDir)}.review.json");

    /// <summary>Dernier résultat d'analyse : régénérable, reste local.</summary>
    public string AnalysisFile(string projectDir) => Path.Combine(localRoot, "analyses", $"{Slug(projectDir)}.viewer.json");

    public string LogFile(string projectDir) => Path.Combine(localRoot, "analyses", $"{Slug(projectDir)}.log");

    /// <summary>Revues IA lancées depuis l'app (rapport, verdicts, preuves) : suivent l'utilisateur, comme les statuts.</summary>
    public string AiReviewDir(string projectDir) => Path.Combine(roamingRoot, "revue-ia", Slug(projectDir));

    /// <summary>Clé API Anthropic chiffrée (DPAPI, utilisateur courant) : locale, jamais dans le dépôt.</summary>
    public string ApiKeyFile => Path.Combine(localRoot, "anthropic-key.bin");

    /// <summary>Nom lisible + empreinte du chemin complet : deux projets homonymes ne se mélangent pas.</summary>
    public static string Slug(string projectDir)
    {
        var full = Path.GetFullPath(projectDir).TrimEnd('\\', '/');
        // Windows ignore la casse : l'empreinte aussi, sinon « l oree » et « L OREE » seraient deux projets.
        var hash = Convert.ToHexString(SHA1.HashData(Encoding.UTF8.GetBytes(full.ToLowerInvariant())))[..8].ToLowerInvariant();
        var name = new string(Path.GetFileName(full).Select(c => char.IsLetterOrDigit(c) ? c : '_').ToArray());
        return $"{name}-{hash}";
    }
}
