using System.Collections.ObjectModel;
using System.IO;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using SiaCheck.Viewer.Services;

namespace SiaCheck.Viewer.ViewModels;

/// <summary>Une case de l'empreinte : un contrôle du moteur, présent ou non, avec son infobulle.</summary>
public sealed record FingerprintCell(bool Ok, bool Required, string Tooltip);

/// <summary>Un MDP de la base sur l'accueil, avec son empreinte de fiabilité (un segment par contrôle du moteur).</summary>
public sealed class BenchmarkItem(BenchmarkProject p)
{
    /// <summary>Contrôles qui décident de l'entrée dans les références (benchmark.REQUIS).</summary>
    public static readonly IReadOnlySet<string> Required = new HashSet<string> { "coherence", "plausible" };

    public BenchmarkProject Project { get; } = p;
    public string Id { get; } = p.Id;
    /// <summary>Typologie (catégorie d'ouvrage) en libellé court ; « Non identifié » sans typologie.</summary>
    public string Typologie { get; } = ProjectIdentity.Short(p.Info("categorie"));
    public bool IsIdentified { get; } = !string.IsNullOrWhiteSpace(p.Info("categorie"));
    public string Name { get; } = p.Name;
    public string Canton { get; } = p.Info("canton") ?? "—";
    public bool IsReliable { get; } = p.Reliable;
    public string Verdict => IsReliable ? "OK" : "ALERTE";
    public IReadOnlyList<FingerprintCell> Fingerprint { get; } = p.Checks.Select((c, i) => Cell(i + 1, c)).ToList();
    /// <summary>Pourquoi le projet est (ou n'est pas) dans les références : infobulle du verdict.</summary>
    public string VerdictText { get; } = p.Reliable
        ? "Dans les références : SP ≥ SN et part de construction plausible."
        : $"Écarté des références : {RejectReason(p)}";
    public string Tooltip { get; } =
        $"{p.File} · cliquer pour compléter son identité\n" +
        (p.Reliable ? "Dans les références" : $"Écarté des références : {RejectReason(p)}") +
        (p.Checks.Where(c => !c.Ok).ToList() is { Count: > 0 } missing
            ? "\n\nManque :\n• " + string.Join("\n• ", missing.Select(c => c.Detail.Length > 0 ? $"{c.Label} ({c.Detail})" : c.Label))
            : "\n\nToutes les données sont présentes.");

    private static FingerprintCell Cell(int n, BenchmarkCheck c)
    {
        var required = Required.Contains(c.Id);
        var state = c.Ok ? "✓ présent" : "✗ absent ou hors plage";
        var detail = c.Detail.Length > 0 ? $" · {c.Detail}" : "";
        var role = required ? "Requis pour entrer dans les références." : "Enrichit certains ratios ; ne bloque pas l'entrée dans les références.";
        return new FingerprintCell(c.Ok, required, $"{n}. {c.Label}\n{state}{detail}\n{role}");
    }

    /// <summary>
    /// La vraie raison d'un écart, du plus élémentaire au plus fin : surfaces absentes, puis SP &lt; SN, puis part de
    /// construction hors de la fourchette plausible (trop haute : nettes incomplètes ; trop basse : SP incomplète).
    /// </summary>
    internal static string RejectReason(BenchmarkProject p)
    {
        var checks = p.Checks.ToDictionary(c => c.Id);
        bool Ok(string id) => !checks.TryGetValue(id, out var c) || c.Ok;     // contrôle absent : pas en cause
        string Detail(string id) => checks.TryGetValue(id, out var c) ? c.Detail : "";
        if (!Ok("brutes") && !Ok("nettes")) return "le MDP ne contient ni surfaces brutes (SP) ni surfaces nettes.";
        if (!Ok("brutes")) return "le MDP ne contient pas de surfaces brutes (SP) : impossible de comparer brut et net.";
        if (!Ok("nettes")) return "le MDP ne contient pas de surfaces nettes : impossible de comparer brut et net.";
        if (!Ok("coherence"))
            return $"la SP est inférieure à la SN ({Detail("coherence")}) : brut et net ne décrivent pas le même périmètre.";
        if (!Ok("plausible"))
        {
            var range = checks.TryGetValue("plausible", out var c) && c.Label.IndexOf("entre ", StringComparison.Ordinal) is >= 0 and var i
                ? c.Label[i..] : "dans la fourchette plausible";
            var m = System.Text.RegularExpressions.Regex.Match(Detail("plausible"), @"(\d+)\s*%");
            var why = !m.Success ? ""
                : int.Parse(m.Groups[1].Value) > 20 ? " : trop de construction, il manque probablement des surfaces nettes."
                : " : trop peu de construction, la SP est probablement incomplète.";
            return $"part de construction {Detail("plausible")}, attendue {range}{why}";
        }
        return "données incomplètes.";
    }
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
    /// <summary>Légende de la colonne « Données du MDP » : les contrôles du moteur, dans l'ordre des cases.</summary>
    [ObservableProperty] private string _fingerprintLegend = "";

    [ObservableProperty] [NotifyPropertyChangedFor(nameof(HasBenchmarkFolder), nameof(BenchmarkEmptyMessage))]
    private string _benchmarkFolder = "";
    [ObservableProperty] private bool _isBenchmarkLoading;
    [ObservableProperty] private string? _benchmarkActivity;
    [ObservableProperty] private string? _benchmarkError;
    [ObservableProperty] private string? _benchmarkSummary;
    [ObservableProperty] private string? _benchmarkWarning;
    [ObservableProperty] private string? _benchmarkEmptyMessage;

    /// <summary>Écran Dashboard affiché (page HTML dans WebView2, docs/DESIGN_PLAN.md Évolution 3.1).</summary>
    [ObservableProperty] [NotifyPropertyChangedFor(nameof(IsHome), nameof(IsReviewing), nameof(CloseDashboardTooltip))]
    private bool _isDashboard;
    /// <summary>
    /// « Mon projet » venu de SIA Check : le projet ouvert lu par le moteur (sia-check --benchmark-projet), au format d'un
    /// projet du benchmark ; null quand le dashboard est ouvert depuis l'accueil (la page reprend alors la saisie).
    /// </summary>
    public string? MyProjectJson { get; private set; }
    public string CloseDashboardTooltip => HasDocument ? $"Retour au projet « {ProjectName} »" : "Retour à l'accueil";
    /// <summary>Change à chaque lecture de la base : la vue recharge alors la page.</summary>
    [ObservableProperty] private int _dashboardVersion;
    /// <summary>Le dashboard ne peut pas s'afficher (composant WebView2 absent) : dit pourquoi et comment corriger.</summary>
    [ObservableProperty] private string? _dashboardError;

    public string BenchmarkFile => _paths.BenchmarkFile;
    /// <summary>Fiche d'identité transmise au moteur (--identite) : régénérée à chaque usage.</summary>
    private string IdentityFile => Path.Combine(Path.GetDirectoryName(_paths.BenchmarkFile)!, "identite.json");
    private BenchmarkData? _benchmarkData;
    /// <summary>Listes de la fiche Identité : celles du gabarit transmises par le moteur, sinon la copie livrée.</summary>
    internal IdentityLists IdentityLists => IdentityLists.From(_benchmarkData?.Lists);
    public string DashboardTheme => _settings.Theme == "Dark" ? "dark" : "light";

    public bool HasBenchmarkFolder => BenchmarkFolder.Length > 0;
    /// <summary>Base à relire : un MDP a changé, ou le moteur est plus récent que la dernière lecture (comme une analyse).</summary>
    private bool IsBenchmarkStale => HasBenchmarkFolder && Directory.Exists(BenchmarkFolder) &&
                                     (BenchmarkBase.IsStale(BenchmarkFolder, _paths.BenchmarkFile) ||
                                      _engine is not null && File.GetLastWriteTime(_paths.BenchmarkFile) < _engine.EngineModified);

    private void InitBenchmark()
    {
        BenchmarkFolder = _settings.BenchmarkFolder;
        ShowBenchmark(BenchmarkBase.Load(_paths.BenchmarkFile));
        if (IsBenchmarkStale) _ = RefreshBenchmarkAsync();
    }

    [RelayCommand(CanExecute = nameof(CanOpenBenchmark))]
    private void OpenBenchmark()
    {
        HomeError = null;
        MyProjectJson = null;
        IsDashboard = true;
    }

    /// <summary>Quitte le dashboard : retour au projet ouvert s'il y en a un, sinon à l'accueil.</summary>
    [RelayCommand]
    private void CloseDashboard()
    {
        IsDashboard = false;
        if (!HasDocument) GoHome();
    }

    /// <summary>
    /// Le projet ouvert, corrections comprises, comparé aux projets similaires de la base : le moteur relit le .tgm comme
    /// pour l'export MDP (toujours à jour, sans réanalyse), puis le dashboard s'ouvre sur « Mon projet ».
    /// </summary>
    [RelayCommand]
    private async Task CompareToBenchmarkAsync()
    {
        if (ProjectDir is null || _engine is null || Document is null || IsBenchmarkLoading) return;
        if (!HasBenchmarkFolder || BenchmarkProjects.Count == 0)
        {
            _shell.Notify("Base du benchmark vide : choisissez son dossier depuis l'accueil.", isError: true);
            return;
        }
        var json = Path.Combine(Path.GetDirectoryName(_paths.BenchmarkFile)!, "mon-projet.json");
        MyProjectJson = null;
        IsDashboard = true;
        IsBenchmarkLoading = true;
        BenchmarkActivity = $"Lecture des surfaces de « {ProjectName} »…";
        try
        {
            var r = await _engine.BenchmarkProjectAsync(ProjectDir, json, ProjectName, CurrentEngineInputs(ProjectDir), CancellationToken.None);
            if (!r.Succeeded)
            {
                _shell.Notify(r.ErrorMessage ?? "Lecture du projet impossible.", isError: true);
                return;
            }
            MyProjectJson = System.Text.Json.Nodes.JsonNode.Parse(await File.ReadAllTextAsync(json))?["projet"]?.ToJsonString();
            DashboardVersion++;
        }
        catch (Exception ex) when (ex is IOException or System.ComponentModel.Win32Exception or InvalidOperationException
                                       or System.Text.Json.JsonException)
        {
            _shell.Notify(ex.Message, isError: true);
        }
        finally
        {
            IsBenchmarkLoading = false;
            BenchmarkActivity = null;
        }
    }

    private bool CanOpenBenchmark() => BenchmarkProjects.Count > 0;

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
        _benchmarkData = data;
        BenchmarkProjects.Clear();
        OpenBenchmarkCommand.NotifyCanExecuteChanged();
        BenchmarkError = null;
        BenchmarkWarning = null;
        BenchmarkSummary = null;
        BenchmarkEmptyMessage = !HasBenchmarkFolder ? null
            : !BenchmarkBase.MdpFiles(BenchmarkFolder).Any()
                ? "Aucun fichier MDP-*.xlsx dans ce dossier. Exportez un MDP depuis un projet traité, ou choisissez un autre dossier."
                : null;
        if (data is null || !HasBenchmarkFolder) return;
        FingerprintLegend = data.Projects.FirstOrDefault()?.Checks is { Count: > 0 } checks
            ? "Une case par contrôle du MDP, de gauche à droite (pleine = présent) :\n"
              + string.Join("\n", checks.Select((c, i) => $"{i + 1}. {c.Label}" + (BenchmarkItem.Required.Contains(c.Id) ? "  (requis)" : "")))
              + "\n\nLes contrôles requis décident de l'entrée dans les références (✓) ; les autres enrichissent certains ratios."
            : "";
        foreach (var p in data.Projects.OrderByDescending(p => p.Reliable).ThenByDescending(p => p.Score).ThenBy(p => p.Id))
            BenchmarkProjects.Add(new BenchmarkItem(p));
        var reliable = data.Projects.Count(p => p.Reliable);
        if (data.Projects.Count > 0)
            BenchmarkSummary = $"{reliable} projet{S(reliable)} de référence sur {data.Projects.Count} · lue le {data.Generated:dd.MM.yyyy HH:mm}";
        if (data.Projects.Count > 0 && reliable < MinReferenceProjects)
            BenchmarkWarning = $"{reliable} projet{S(reliable)} de référence : trop peu pour comparer.";
        if (data.Errors.Count > 0)
            BenchmarkError = $"{data.Errors.Count} fichier{S(data.Errors.Count)} ignoré{S(data.Errors.Count)} : " + string.Join(" · ", data.Errors);
        OpenBenchmarkCommand.NotifyCanExecuteChanged();
        DashboardVersion++;
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
        var hrs = await AskMdpProjectAsync(recent.Path, recent.Name, IdentityMode.Base);
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
                                             CancellationToken.None, ProjectIdentity.WriteEngineFile(hrs, IdentityFile));
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

    private BenchmarkProject? BaseProject(string id) =>
        string.IsNullOrWhiteSpace(id) ? null : _benchmarkData?.Projects.FirstOrDefault(p => p.Id == id.Trim());

    /// <summary>Complète les champs vides d'une identité avec ce que porte le MDP de la base.</summary>
    private static void FillFromBase(MdpProject id, BenchmarkProject p)
    {
        static string Clean(string? v) => v is null ? "" : v.EndsWith(".0") ? v[..^2] : v;     // 53.0 -> 53 (Excel)
        if (id.Id.Length == 0) id.Id = p.Id;
        if (id.Name.Length == 0) id.Name = p.Name;
        if (id.Canton.Length == 0) id.Canton = Clean(p.Info("canton"));
        if (id.Commune.Length == 0) id.Commune = Clean(p.Info("commune"));
        if (id.Typologie.Length == 0) id.Typologie = Clean(p.Info("categorie"));
        if (id.Intervention.Length == 0) id.Intervention = Clean(p.Info("intervention"));
        if (id.Phase.Length == 0) id.Phase = Clean(p.Info("phase"));
    }

    /// <summary>
    /// Identité d'un MDP déjà dans la base, complétée ou corrigée depuis l'accueil : écrite dans sa feuille InfosProjet
    /// (le MDP fait foi), puis la base relue. L'ID ne change pas : il relie les tables du MDP.
    /// </summary>
    [RelayCommand]
    private async Task EditBaseIdentityAsync(BenchmarkItem item)
    {
        if (_engine is null || IsBenchmarkLoading || !HasBenchmarkFolder) return;
        var initial = new MdpProject();
        FillFromBase(initial, item.Project);
        var hrs = await _shell.AskIdentityAsync(initial, IdentityLists, IdentityMode.EditBase, "Enregistrer dans le MDP");
        if (hrs is null) return;
        hrs.Id = initial.Id;
        var path = Path.Combine(BenchmarkFolder, item.Project.File);
        IsBenchmarkLoading = true;
        BenchmarkActivity = $"Écriture de l'identité dans {item.Project.File}…";
        EngineRun r;
        try
        {
            r = await _engine.WriteMdpIdentityAsync(path, ProjectIdentity.WriteEngineFile(hrs, IdentityFile), CancellationToken.None);
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
            _shell.Notify(r.ErrorMessage ?? "Identité non écrite.", isError: true);
            return;
        }
        _shell.Notify($"Identité de « {hrs.Name} » enregistrée dans {item.Project.File}.");
        await RefreshBenchmarkAsync();
    }
}
