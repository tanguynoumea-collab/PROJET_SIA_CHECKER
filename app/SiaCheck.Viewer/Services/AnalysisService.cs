using System.Diagnostics;
using System.IO;
using System.Text;
using System.Text.RegularExpressions;

namespace SiaCheck.Viewer.Services;

public sealed record AnalysisProgress(int Step, int StepCount, string Label);

public sealed record EngineRun(int ExitCode, string Log)
{
    /// <summary>Codes de sortie de sia-check : 0 aucun écart, 1 écarts, 2 erreur.</summary>
    public bool Succeeded => ExitCode is 0 or 1;

    /// <summary>Dernière ligne « ERROR … » du journal, à montrer telle quelle à l'utilisateur.</summary>
    public string? ErrorMessage => Log.Split('\n').Select(l => l.Trim())
        .LastOrDefault(l => l.StartsWith("ERROR ", StringComparison.Ordinal))?[6..];
}

/// <summary>
/// Ce que l'app ajoute au .tgm à chaque exécution : dernière revue IA (<c>--revue</c>, réoriente les sujets),
/// journal des décisions (<c>--corrections</c>, appliqué avant les contrôles et les exports) et fichier où garder
/// les surfaces lues (<c>--surfaces-cache</c>), base de l'aperçu en direct.
/// </summary>
public sealed record EngineInputs(string? Review = null, string? Journal = null, string? SurfacesCache = null)
{
    public static EngineInputs None { get; } = new();

    public IEnumerable<string> Args()
    {
        if (Review is not null) { yield return "--revue"; yield return Review; }
        if (Journal is not null) { yield return "--corrections"; yield return Journal; }
        if (SurfacesCache is not null) { yield return "--surfaces-cache"; yield return SurfacesCache; }
    }
}

/// <summary>Pilote le moteur Python sia-check (exécutable livré avec l'application).</summary>
public sealed partial class AnalysisService(string enginePath)
{
    [GeneratedRegex(@"ÉTAPE (\d+)/(\d+) (.+)$")]
    private static partial Regex StepLine();

    public string EnginePath { get; } = enginePath;

    /// <summary>
    /// Date du moteur : celle de l'exécutable, et en développement (.venv du dépôt, installation éditable) celle du
    /// code et de la configuration du dépôt, qui changent sans que l'exécutable ou la version bougent. Une analyse
    /// plus ancienne est refaite à l'ouverture du projet.
    /// </summary>
    public DateTime EngineModified { get; } = ModifiedOf(enginePath);

    internal static DateTime ModifiedOf(string enginePath)
    {
        var newest = File.Exists(enginePath) ? File.GetLastWriteTime(enginePath) : DateTime.MinValue;
        var scripts = Path.GetDirectoryName(enginePath);
        if (scripts is null || !string.Equals(Path.GetFileName(Path.GetDirectoryName(scripts)), ".venv", StringComparison.OrdinalIgnoreCase))
            return newest;
        var repo = Path.GetDirectoryName(Path.GetDirectoryName(scripts))!;
        var sources = Path.Combine(repo, "src", "sia_check");
        var files = Directory.Exists(sources) ? Directory.EnumerateFiles(sources, "*", SearchOption.AllDirectories) : [];
        foreach (var f in files.Append(Path.Combine(repo, "config.yaml")).Where(File.Exists))
            if (!f.Contains("__pycache__") && File.GetLastWriteTime(f) is var t && t > newest) newest = t;
        return newest;
    }

    public Task<EngineRun> AnalyseAsync(string projectDir, string viewerJson, EngineInputs inputs,
                                         IProgress<AnalysisProgress>? progress, CancellationToken ct) =>
        RunAsync(["-q", projectDir, "--viewer-json", viewerJson, .. inputs.Args()], progress, ct);

    /// <summary>Analyse + preuves géométriques de la revue IA (sia_check.preuves), en une seule exécution (4 étapes).</summary>
    public Task<EngineRun> AnalyseWithEvidenceAsync(string projectDir, string viewerJson, string evidenceJson, EngineInputs inputs,
                                                    IProgress<AnalysisProgress>? progress, CancellationToken ct) =>
        RunAsync(["-q", projectDir, "--viewer-json", viewerJson, "--preuves", evidenceJson, .. inputs.Args()], progress, ct);

    /// <summary>Rapports d'analyse xlsx / html / json (et bilan des corrections) dans un dossier.</summary>
    public Task<EngineRun> ExportAsync(string projectDir, string outDir, EngineInputs inputs, CancellationToken ct) =>
        RunAsync(["-q", projectDir, "--out", outDir, .. inputs.Args()], null, ct);

    /// <summary>Tableau MDP HRS (sia_check.mdp) ; gabarit vierge livré si <paramref name="template"/> est null.</summary>
    public Task<EngineRun> ExportMdpAsync(string projectDir, string mdpPath, string? template, string? projectId,
                                          string? projectName, EngineInputs inputs, CancellationToken ct) =>
        RunAsync(["-q", projectDir, "--mdp", mdpPath,
                  .. template is null ? Array.Empty<string>() : ["--mdp-template", template],
                  .. string.IsNullOrWhiteSpace(projectId) ? Array.Empty<string>() : ["--project-id", projectId.Trim()],
                  .. string.IsNullOrWhiteSpace(projectName) ? Array.Empty<string>() : ["--project-name", projectName.Trim()],
                  .. inputs.Args()], null, ct);

    /// <summary>Excel de correction (treegram.write_corrections) : demande le journal (<paramref name="inputs"/>).</summary>
    public Task<EngineRun> ExportCorrectionsAsync(string projectDir, string xlsxPath, EngineInputs inputs, CancellationToken ct) =>
        RunAsync(["-q", projectDir, "--corrections-xlsx", xlsxPath, .. inputs.Args()], null, ct);

    /// <summary>
    /// Aperçu en direct : le journal réappliqué aux surfaces gardées par la dernière analyse, sans relire le .tgm ni le
    /// cache VWR (quelques secondes) ; écrit le bilan par niveau et les ratios.
    /// </summary>
    public Task<EngineRun> PreviewAsync(string surfacesCache, string journal, string outJson, CancellationToken ct) =>
        RunAsync(["--depuis-cache", surfacesCache, "--corrections", journal, "--apercu", outJson], null, ct);

    /// <summary>Premier aperçu, sans surfaces gardées : le moteur lit le projet et les garde pour les suivants.</summary>
    public Task<EngineRun> PreviewFromProjectAsync(string projectDir, string surfacesCache, string journal, string outJson, CancellationToken ct) =>
        RunAsync([projectDir, "--surfaces-cache", surfacesCache, "--corrections", journal, "--apercu", outJson], null, ct);

    /// <summary>Exports au gabarit Excel Treegram (sia_check.treegram) dans un dossier.</summary>
    public Task<EngineRun> ExportTreegramAsync(string projectDir, string outDir, EngineInputs inputs, CancellationToken ct) =>
        RunAsync(["-q", projectDir, "--treegram", outDir, .. inputs.Args()], null, ct);

    /// <summary>Base du benchmark : les MDP d'un dossier lus, normalisés et comparés (sia_check.benchmark).</summary>
    public Task<EngineRun> BenchmarkAsync(string folder, string json, CancellationToken ct) =>
        RunAsync(["--benchmark", folder, "--benchmark-json", json], null, ct);

    private async Task<EngineRun> RunAsync(IEnumerable<string> args, IProgress<AnalysisProgress>? progress,
                                           CancellationToken ct)
    {
        var psi = new ProcessStartInfo(EnginePath)
        {
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardError = true,
            RedirectStandardOutput = true,
            StandardErrorEncoding = Encoding.UTF8,
            StandardOutputEncoding = Encoding.UTF8,
        };
        foreach (var a in args) psi.ArgumentList.Add(a);
        psi.Environment["PYTHONIOENCODING"] = "utf-8";
        psi.Environment["PYTHONUTF8"] = "1";

        using var p = new Process { StartInfo = psi };
        var log = new StringBuilder();
        p.ErrorDataReceived += (_, e) =>
        {
            if (e.Data is null) return;
            lock (log) log.AppendLine(e.Data);
            var m = StepLine().Match(e.Data);
            if (m.Success)
                progress?.Report(new AnalysisProgress(int.Parse(m.Groups[1].Value), int.Parse(m.Groups[2].Value),
                                                      m.Groups[3].Value));
        };
        p.OutputDataReceived += (_, _) => { };
        if (!p.Start()) throw new InvalidOperationException($"Impossible de lancer {EnginePath}.");
        p.BeginErrorReadLine();
        p.BeginOutputReadLine();
        try
        {
            await p.WaitForExitAsync(ct);
        }
        catch (OperationCanceledException)
        {
            try { p.Kill(entireProcessTree: true); } catch (InvalidOperationException) { /* déjà terminé */ }
            throw;
        }
        p.WaitForExit(); // vide les tampons de sortie asynchrones
        lock (log) return new EngineRun(p.ExitCode, log.ToString());
    }

    /// <summary>
    /// Moteur livré (engine\sia-check.exe à côté de l'application), sinon variable SIA_CHECK_EXE,
    /// sinon environnement de développement (.venv du dépôt).
    /// </summary>
    public static string? Locate(string appDir)
    {
        var candidates = new List<string?>
        {
            Environment.GetEnvironmentVariable("SIA_CHECK_EXE"),
            Path.Combine(appDir, "engine", "sia-check.exe"),
        };
        for (var dir = new DirectoryInfo(appDir); dir is not null; dir = dir.Parent)
            candidates.Add(Path.Combine(dir.FullName, ".venv", "Scripts", "sia-check.exe"));
        return candidates.FirstOrDefault(c => !string.IsNullOrEmpty(c) && File.Exists(c));
    }
}
