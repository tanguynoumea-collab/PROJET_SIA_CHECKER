using System.Collections.ObjectModel;
using System.IO;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using SiaCheck.Viewer.Services;

namespace SiaCheck.Viewer.ViewModels;

/// <summary>Un MDP de la base sur l'accueil, avec son empreinte de fiabilité (un segment par contrôle du moteur).</summary>
public sealed class BenchmarkItem(BenchmarkProject p)
{
    public string Id { get; } = p.Id;
    public string Name { get; } = p.Name;
    public string Canton { get; } = p.Info("canton") ?? "—";
    public bool IsReliable { get; } = p.Reliable;
    public string Verdict => IsReliable ? "OK" : "ALERTE";
    public IReadOnlyList<bool> Fingerprint { get; } = p.Checks.Select(c => c.Ok).ToList();
    public string Tooltip { get; } =
        $"{p.File}\n" + (p.Reliable ? "Dans les références" : "Écarté des références : SP et SN ne décrivent pas le même périmètre") +
        (p.Checks.Where(c => !c.Ok).ToList() is { Count: > 0 } missing
            ? "\n\nManque :\n• " + string.Join("\n• ", missing.Select(c => c.Detail.Length > 0 ? $"{c.Label} ({c.Detail})" : c.Label))
            : "\n\nToutes les données sont présentes.");
}

/// <summary>
/// Section Benchmark de l'accueil (plan de design, Évolution 3.0) : la base des MDP lue par le moteur
/// (<c>sia-check --benchmark</c>) et son état. Le moteur n'est relancé que si un MDP a changé depuis la dernière lecture.
/// </summary>
public sealed partial class MainViewModel
{
    /// <summary>En dessous, le groupe de projets similaires est trop petit pour servir de référence (V3_PLAN §4.4).</summary>
    public const int MinReferenceProjects = 3;

    public ObservableCollection<BenchmarkItem> BenchmarkProjects { get; } = [];

    [ObservableProperty] [NotifyPropertyChangedFor(nameof(HasBenchmarkFolder), nameof(BenchmarkEmptyMessage))]
    private string _benchmarkFolder = "";
    [ObservableProperty] private bool _isBenchmarkLoading;
    [ObservableProperty] private string? _benchmarkActivity;
    [ObservableProperty] private string? _benchmarkError;
    [ObservableProperty] private string? _benchmarkSummary;
    [ObservableProperty] private string? _benchmarkWarning;
    [ObservableProperty] private string? _benchmarkEmptyMessage;

    public bool HasBenchmarkFolder => BenchmarkFolder.Length > 0;
    private bool IsBenchmarkStale => HasBenchmarkFolder && Directory.Exists(BenchmarkFolder) &&
                                     BenchmarkBase.IsStale(BenchmarkFolder, _paths.BenchmarkFile);

    private void InitBenchmark()
    {
        BenchmarkFolder = _settings.BenchmarkFolder;
        ShowBenchmark(BenchmarkBase.Load(_paths.BenchmarkFile));
        if (IsBenchmarkStale) _ = RefreshBenchmarkAsync();
    }

    /// <summary>Le dashboard arrive en phase 11 (HTML dans WebView2).</summary>
    [RelayCommand(CanExecute = nameof(CanOpenBenchmark))]
    private void OpenBenchmark() { }

    private static bool CanOpenBenchmark() => false;

    [RelayCommand]
    private async Task ChooseBenchmarkFolderAsync()
    {
        var dir = _shell.PickFolder("Dossier des tableaux MDP de la base du benchmark", HasBenchmarkFolder ? BenchmarkFolder : null);
        if (dir is null) return;
        BenchmarkFolder = dir;
        _settings.BenchmarkFolder = dir;
        _settings.Save(_paths);
        await RefreshBenchmarkAsync();
    }

    [RelayCommand]
    private async Task RefreshBenchmarkAsync()
    {
        if (!HasBenchmarkFolder || IsBenchmarkLoading) return;
        if (_engine is null)
        {
            BenchmarkError = "Moteur d'analyse introuvable : la base ne peut pas être lue.";
            return;
        }
        if (!Directory.Exists(BenchmarkFolder))
        {
            BenchmarkError = $"Dossier de la base introuvable : {BenchmarkFolder}. Choisissez-le à nouveau.";
            return;
        }
        IsBenchmarkLoading = true;
        BenchmarkActivity = "Lecture de la base…";
        try
        {
            var r = await _engine.BenchmarkAsync(BenchmarkFolder, _paths.BenchmarkFile, CancellationToken.None);
            if (!r.Succeeded)
            {
                BenchmarkError = r.ErrorMessage ?? "Lecture de la base impossible.";
                return;
            }
            ShowBenchmark(BenchmarkBase.Load(_paths.BenchmarkFile));
        }
        catch (Exception ex) when (ex is IOException or System.ComponentModel.Win32Exception or InvalidOperationException)
        {
            BenchmarkError = ex.Message;
        }
        finally
        {
            IsBenchmarkLoading = false;
            BenchmarkActivity = null;
        }
    }

    private void ShowBenchmark(BenchmarkData? data)
    {
        BenchmarkProjects.Clear();
        BenchmarkError = null;
        BenchmarkWarning = null;
        BenchmarkSummary = null;
        BenchmarkEmptyMessage = !HasBenchmarkFolder ? null
            : !BenchmarkBase.MdpFiles(BenchmarkFolder).Any()
                ? "Aucun fichier MDP-*.xlsx dans ce dossier. Exportez un MDP depuis un projet traité, ou choisissez un autre dossier."
                : null;
        if (data is null || !HasBenchmarkFolder) return;
        foreach (var p in data.Projects.OrderByDescending(p => p.Reliable).ThenByDescending(p => p.Score).ThenBy(p => p.Id))
            BenchmarkProjects.Add(new BenchmarkItem(p));
        var reliable = data.Projects.Count(p => p.Reliable);
        if (data.Projects.Count > 0)
            BenchmarkSummary = $"{reliable} projet{S(reliable)} de référence sur {data.Projects.Count} · lue le {data.Generated:dd.MM.yyyy HH:mm}";
        if (data.Projects.Count > 0 && reliable < MinReferenceProjects)
            BenchmarkWarning = $"{reliable} projet{S(reliable)} de référence : trop peu pour comparer.";
        if (data.Errors.Count > 0)
            BenchmarkError = $"{data.Errors.Count} fichier{S(data.Errors.Count)} ignoré{S(data.Errors.Count)} : " + string.Join(" · ", data.Errors);
    }

    /// <summary>
    /// Le MDP d'un projet traité, exporté directement dans la base (surfaces corrigées), puis la base relue. Un MDP du même
    /// ID déjà présent est remplacé : le moteur ne garde qu'un fichier par ID.
    /// </summary>
    [RelayCommand]
    private async Task AddToBaseAsync(RecentItem recent)
    {
        if (_engine is null || IsBenchmarkLoading) return;
        if (!HasBenchmarkFolder)
        {
            await ChooseBenchmarkFolderAsync();
            if (!HasBenchmarkFolder) return;
        }
        var hrs = await AskMdpProjectAsync(recent.Path, recent.Name);
        if (hrs is null) return;
        var existing = BenchmarkBase.FindById(BenchmarkFolder, hrs.Id);
        if (existing is not null && !await _shell.ConfirmAsync($"Remplacer {Path.GetFileName(existing)} ?",
                $"La base contient déjà un MDP pour le projet {hrs.Id}. Il sera remplacé par celui de « {recent.Name} », " +
                "exporté avec les surfaces corrigées.", "Remplacer", "Annuler"))
            return;
        var path = existing ?? Path.Combine(BenchmarkFolder, $"MDP-{hrs.Id}-{AiReviewFiles.Prefix(hrs.Name)}.xlsx");
        IsBenchmarkLoading = true;
        BenchmarkActivity = $"Export du MDP de « {recent.Name} »…";
        EngineRun r;
        try
        {
            r = await _engine.ExportMdpAsync(recent.Path, path, null, hrs.Id, hrs.Name, CurrentEngineInputs(recent.Path),
                                             CancellationToken.None);
        }
        catch (Exception ex) when (ex is IOException or System.ComponentModel.Win32Exception or InvalidOperationException)
        {
            _shell.Notify(ex.Message, isError: true);
            return;
        }
        finally
        {
            IsBenchmarkLoading = false;
            BenchmarkActivity = null;
        }
        if (!r.Succeeded)
        {
            _shell.Notify(r.ErrorMessage ?? "Export du MDP impossible.", isError: true);
            return;
        }
        _shell.Notify($"« {recent.Name} » ajouté à la base : {Path.GetFileName(path)}.");
        await RefreshBenchmarkAsync();
    }
}
