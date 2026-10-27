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

    /// <summary>Registre des projets et de leur statut (en traitement / traité) : lu par les automatisations (n8n).</summary>
    public string ProjectsFile => Path.Combine(roamingRoot, "projets.json");

    /// <summary>Statuts et commentaires : suivent l'utilisateur (profil itinérant).</summary>
    public string ReviewFile(string projectDir) => Path.Combine(roamingRoot, "reviews", $"{Slug(projectDir)}.review.json");

    /// <summary>Décisions sur les corrections (journal lu par <c>sia-check --corrections</c>) : suivent l'utilisateur.</summary>
    public string CorrectionsFile(string projectDir) => Path.Combine(roamingRoot, "corrections", $"{Slug(projectDir)}.json");

    /// <summary>Dernier résultat d'analyse : régénérable, reste local.</summary>
    public string AnalysisFile(string projectDir) => Path.Combine(localRoot, "analyses", $"{Slug(projectDir)}.viewer.json");

    /// <summary>Surfaces lues par la dernière analyse, avant corrections : base de l'aperçu en direct (régénérable, local).</summary>
    public string SurfacesCacheFile(string projectDir) => Path.Combine(localRoot, "analyses", $"{Slug(projectDir)}.surfaces.pkl");

    /// <summary>Bilan par niveau et ratios de l'aperçu en direct des corrections.</summary>
    public string PreviewFile(string projectDir) => Path.Combine(localRoot, "analyses", $"{Slug(projectDir)}.apercu.json");

    /// <summary>Base du benchmark lue par le moteur (sia-check --benchmark) : régénérable, reste locale.</summary>
    public string BenchmarkFile => Path.Combine(localRoot, "benchmark", "benchmark.json");

    /// <summary>Profil du navigateur intégré (WebView2) du dashboard : cache, régénérable, local.</summary>
    public string WebViewDataDir => Path.Combine(localRoot, "webview2");

    public string LogFile(string projectDir) => Path.Combine(localRoot, "analyses", $"{Slug(projectDir)}.log");

    /// <summary>Revues IA lancées depuis l'app (rapport, verdicts, preuves) : suivent l'utilisateur, comme les statuts.</summary>
    public string AiReviewDir(string projectDir) => Path.Combine(roamingRoot, "revue-ia", Slug(projectDir));

    /// <summary>
    /// Efface tout ce que l'application garde d'un projet : statuts et commentaires, décisions de corrections, dernière
    /// analyse et son journal, revues IA lancées depuis l'app. Le dossier Treegram et les exports ne sont pas touchés.
    /// </summary>
    public void DeleteProject(string projectDir)
    {
        foreach (var f in new[] { ReviewFile(projectDir), CorrectionsFile(projectDir), AnalysisFile(projectDir), LogFile(projectDir) })
            if (File.Exists(f)) File.Delete(f);
        if (Directory.Exists(AiReviewDir(projectDir))) Directory.Delete(AiReviewDir(projectDir), recursive: true);
    }

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
