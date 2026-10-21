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

/// <summary>Pilote le moteur Python sia-check (exécutable livré avec l'application).</summary>
public sealed partial class AnalysisService(string enginePath)
{
    [GeneratedRegex(@"ÉTAPE (\d+)/(\d+) (.+)$")]
    private static partial Regex StepLine();

    public string EnginePath { get; } = enginePath;

    public Task<EngineRun> AnalyseAsync(string projectDir, string viewerJson, IProgress<AnalysisProgress>? progress,
                                         CancellationToken ct) =>
        RunAsync(["-q", projectDir, "--viewer-json", viewerJson], progress, ct);

    public Task<EngineRun> ExportAsync(string projectDir, string outDir, CancellationToken ct) =>
        RunAsync(["-q", projectDir, "--out", outDir], null, ct);

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
