using System.Collections.ObjectModel;
using System.ComponentModel;
using System.IO;
using System.Windows.Data;
using System.Windows.Threading;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using SiaCheck.Viewer.Models;
using SiaCheck.Viewer.Scene;
using SiaCheck.Viewer.Services;

namespace SiaCheck.Viewer.ViewModels;

public sealed partial class MainViewModel : ObservableObject
{
    public const string AllLevels = "Tous les niveaux";
    private static readonly string[] InteriorCodes = ["SP", "SN", "SU", "SUP", "SUT", "SUS", "SD", "SI", "SC", "SCP", "SCN"];

    private readonly IShell _shell;
    private readonly AppPaths _paths;
    private readonly AppSettings _settings;
    private readonly AnalysisService? _engine;
    private readonly ProjectRegistry _registry;
    private readonly DispatcherTimer _commentSave;
    private ReviewStore? _store;
    private CancellationTokenSource? _cts;
    private Dictionary<string, Surface> _surfaceById = [];
    private bool _suspendSceneUpdates;

    public MainViewModel(IShell shell, AppPaths paths, AppSettings settings, string? enginePath)
    {
        _shell = shell;
        _paths = paths;
        _settings = settings;
        _engine = enginePath is null ? null : new AnalysisService(enginePath);
        _isBalanceCollapsed = settings.BalanceCollapsed;
        _showRatios = settings.ShowRatios;
        _registry = new ProjectRegistry(paths.ProjectsFile);
        FillRecents();
        InitBenchmark();
        LayersView = new ListCollectionView(Layers);
        LayersView.GroupDescriptions.Add(new PropertyGroupDescription(nameof(LayerItem.Group)));
        IssuesView = CollectionViewSource.GetDefaultView(Issues);
        IssuesView.SortDescriptions.Add(new SortDescription(nameof(IssueItem.SortKey), ListSortDirection.Ascending));
        IssuesView.Filter = o => o is IssueItem i && Matches(i);
        _commentSave = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(600) };
        _commentSave.Tick += (_, _) => { _commentSave.Stop(); SaveReview(SelectedIssue); };
        if (_engine is null)
            HomeError = "Moteur d'analyse introuvable : réinstallez l'application (dossier engine\\sia-check.exe) " +
                        "ou indiquez son chemin dans la variable SIA_CHECK_EXE.";
    }

    // ------------------------------------------------------------------ état général

    public ObservableCollection<RecentItem> Recents { get; } = [];
    [ObservableProperty] private string? _projectDir;
    [ObservableProperty] [NotifyPropertyChangedFor(nameof(HasDocument), nameof(IsHome), nameof(IsReviewing))] private ViewerDocument? _document;
    [ObservableProperty] private SceneController? _scene;
    [ObservableProperty] private SiaPalette? _palette;
    [ObservableProperty] private string? _homeError;
    [ObservableProperty] [NotifyPropertyChangedFor(nameof(HasAnalysisError))] private string? _analysisError;
    public bool HasAnalysisError => !string.IsNullOrEmpty(AnalysisError);
    [ObservableProperty] private string? _lastLogFile;

    public bool HasDocument => Document is not null;
    /// <summary>Espace de revue visible : un projet est ouvert et le dashboard n'est pas affiché par-dessus.</summary>
    public bool IsReviewing => HasDocument && !IsDashboard;
    public bool IsHome => Document is null && !IsDashboard;
    public string ProjectName => Document?.Project ?? "";
    public string AnalysedAt => Document is null ? "" : $"analysé le {File.GetLastWriteTime(_paths.AnalysisFile(ProjectDir!)):dd.MM HH:mm}";
    public bool CacheIsStale => Document?.Cache.Stale ?? false;
    public string CacheWarning => Document?.Cache is { } c && c.Stale
        ? $"Cache 3D du {c.Newest:dd.MM} antérieur au projet ({c.SourceModified:dd.MM}) : la géométrie peut être périmée. Ouvrez le projet dans le viewer Treegram pour la régénérer."
        : "";
    public string MissingGeometryWarning => Document?.Cache.SurfacesWithoutMesh is > 0 and var n
        ? $"{n} surfaces sans géométrie dans le cache VWR (ouvrez le projet dans le viewer Treegram pour le régénérer)."
        : "";
    public bool HasNoGeometry => Document is not null && (Scene?.SurfacesWithGeometry ?? 0) == 0;
    public string StatusText => Document is null ? "" :
        $"{Document.Surfaces.Count:N0} surfaces · {Buildings.Count} bâtiments · {Document.Levels.Count} niveaux · " +
        $"tolérance {Document.Tolerance.AbsM2:0.##} m² et {Document.Tolerance.Rel * 100:0.##} % · sia-check {Document.ToolVersion}";

    // ------------------------------------------------------------------ analyse

    [ObservableProperty] [NotifyPropertyChangedFor(nameof(IsBusy))] private bool _isAnalysing;
    [ObservableProperty] private int _analysisStep;
    [ObservableProperty] private string _analysisLabel = "";
    /// <summary>Ligne de la superposition d'analyse quand le journal des corrections est joint.</summary>
    [ObservableProperty] private string _analysisCorrections = "";
    public bool IsBusy => IsAnalysing;
    public string[] AnalysisSteps { get; } = ["Lecture du .tgm", "Contrôles SIA 416", "Géométrie (cache VWR)"];

    [RelayCommand]
    private async Task OpenProjectAsync()
    {
        var dir = _shell.PickFolder("Dossier du projet Treegram (contient le fichier .tgm et le dossier VWR)", ProjectDir);
        if (dir is not null) await OpenAsync(dir);
    }

    [RelayCommand]
    private Task OpenRecentAsync(RecentItem recent) => OpenAsync(recent.Path);

    /// <summary>Supprime un projet de l'application (récents, statuts, corrections, analyse, revues IA, ID MDP) : repartir de zéro.</summary>
    [RelayCommand]
    private async Task DeleteRecentAsync(RecentItem recent)
    {
        var ok = await _shell.ConfirmAsync($"Supprimer « {recent.Name} » ?",
            "Les statuts et commentaires des points, les décisions sur les corrections, la dernière analyse, les revues IA " +
            "lancées depuis l'app, l'ID MDP et le statut (en traitement / traité) de ce projet seront effacés.\n\n" +
            "Le dossier Treegram (.tgm, VWR) et les fichiers exportés ne sont pas touchés : le projet pourra être rouvert et " +
            "réanalysé de zéro.",
            "Supprimer", "Annuler");
        if (!ok) return;
        try
        {
            _paths.DeleteProject(recent.Path);
            _registry.Forget(recent.Path);
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            _shell.Notify($"Suppression incomplète : {ex.Message}", isError: true);
            return;
        }
        _settings.Forget(recent.Path);
        _settings.Save(_paths);
        Recents.Remove(recent);
        _shell.Notify($"« {recent.Name} » supprimé de SIA Check.");
    }

    public async Task OpenAsync(string dir)
    {
        HomeError = null;
        var tgms = Directory.Exists(dir) ? Directory.GetFiles(dir, "*.tgm") : [];
        if (tgms.Length != 1)
        {
            HomeError = tgms.Length == 0
                ? $"Ce dossier ne contient pas de fichier .tgm. Choisissez le dossier du projet Treegram (celui qui contient Nom.tgm et VWR\\)."
                : $"Ce dossier contient {tgms.Length} fichiers .tgm. Choisissez le dossier d'un seul projet Treegram.";
            return;
        }
        ProjectDir = dir;
        var cached = _paths.AnalysisFile(dir);
        // Analyse encore valable : rouverture instantanée. Le .tgm a changé, ou l'analyse vient d'un autre
        // moteur (mise à jour de l'application : nouveaux contrôles, ratios ; en développement, code du moteur
        // modifié depuis l'analyse) : on réanalyse.
        if (File.Exists(cached) && File.GetLastWriteTime(cached) > File.GetLastWriteTime(tgms[0]))
        {
            try
            {
                var doc = ViewerDocument.Load(cached);
                if (_engine is null || doc.ToolVersion == AppVersion && File.GetLastWriteTime(cached) > _engine.EngineModified)
                {
                    Load(doc);
                    return;
                }
            }
            catch (Exception ex) when (ex is IOException or InvalidDataException or System.Text.Json.JsonException) { /* réanalyse */ }
        }
        await AnalyseAsync();
    }

    /// <summary>Version de l'application, alignée sur celle du moteur embarqué (pyproject.toml).</summary>
    public static string AppVersion { get; } = typeof(MainViewModel).Assembly.GetName().Version is { } v
        ? $"{v.Major}.{v.Minor}.{v.Build}" : "";

    [RelayCommand]
    private async Task AnalyseAsync()
    {
        if (ProjectDir is null || _engine is null || IsAnalysing) return;
        if (IsTraceOpen) { _shell.Notify("Enregistrez ou annulez le tracé avant d'analyser."); return; }
        AnalysisError = null;
        IsAnalysing = true;
        AnalysisStep = 0;
        AnalysisLabel = "Démarrage du moteur";
        _cts = new CancellationTokenSource();
        var json = _paths.AnalysisFile(ProjectDir);
        var tmp = json + ".new";
        try
        {
            Directory.CreateDirectory(Path.GetDirectoryName(json)!);
            var progress = new Progress<AnalysisProgress>(p => { AnalysisStep = p.Step; AnalysisLabel = p.Label; });
            var inputs = CurrentEngineInputs(ProjectDir);
            AnalysisCorrections = inputs.Journal is null ? "" : $"Corrections : {PendingCorrections} décision(s) à appliquer, journal joint";
            var run = await _engine.AnalyseAsync(ProjectDir, tmp, inputs, progress, _cts.Token);
            LastLogFile = _paths.LogFile(ProjectDir);
            await File.WriteAllTextAsync(LastLogFile, run.Log);
            if (!run.Succeeded || !File.Exists(tmp))
            {
                Fail(run.ErrorMessage ?? $"Le moteur s'est arrêté avec le code {run.ExitCode}.");
                return;
            }
            File.Move(tmp, json, overwrite: true);
            MarkCorrectionsAnalysed(inputs);
            Load(ViewerDocument.Load(json));
        }
        catch (OperationCanceledException)
        {
            _shell.Notify("Analyse annulée. Les résultats précédents sont conservés.");
        }
        catch (Exception ex) when (ex is IOException or InvalidDataException or System.Text.Json.JsonException
                                       or System.ComponentModel.Win32Exception)
        {
            Fail(ex.Message);
        }
        finally
        {
            IsAnalysing = false;
            _cts.Dispose();
            _cts = null;
        }
    }

    private void Fail(string message)
    {
        if (HasDocument) AnalysisError = message;
        else HomeError = message;
    }

    [RelayCommand]
    private void CancelAnalysis() => _cts?.Cancel();

    [RelayCommand]
    private void ShowLog()
    {
        if (LastLogFile is not null && File.Exists(LastLogFile)) _shell.OpenFile(LastLogFile);
    }

    /// <summary>Rapports d'analyse xlsx / html / json, sur les surfaces corrigées (bilan des corrections joint).</summary>
    [RelayCommand]
    private Task ExportAsync()
    {
        if (ProjectDir is null || _engine is null) return Task.CompletedTask;
        var dir = _shell.PickFolder("Dossier des rapports xlsx, html et json", null);
        return dir is null ? Task.CompletedTask
            : RunExportAsync(() => _engine.ExportAsync(ProjectDir, dir, CurrentEngineInputs(ProjectDir), CancellationToken.None),
                             $"Rapports enregistrés dans {dir}.");
    }

    /// <summary>Tableau MDP HRS rempli depuis le .tgm, surfaces corrigées ; « template » : choisir d'abord un gabarit.</summary>
    [RelayCommand]
    private async Task ExportMdpAsync(string? mode)
    {
        if (ProjectDir is null || _engine is null || Document is null) return;
        var hrs = await AskMdpProjectAsync(ProjectDir, Document.Project, IdentityMode.Export);
        if (hrs is null) return;
        string? template = null;
        if (mode == "template")
        {
            template = _shell.PickOpenFile("Gabarit MDP (un MDP vierge ou déjà rempli : ses tableaux seront remplacés)", "Classeur Excel|*.xlsx");
            if (template is null) return;
        }
        var path = _shell.PickSaveFile("Enregistrer le tableau MDP", $"MDP-{hrs.Id}-{AiReviewFiles.Prefix(hrs.Name)}.xlsx", "Classeur Excel|*.xlsx");
        if (path is null) return;
        var identity = ProjectIdentity.WriteEngineFile(hrs, IdentityFile);
        await RunExportAsync(() => _engine.ExportMdpAsync(ProjectDir, path, template, hrs.Id, hrs.Name, CurrentEngineInputs(ProjectDir),
                                                          CancellationToken.None, identity),
                             $"Tableau MDP enregistré : {path}.", path);
    }

    /// <summary>
    /// Fiche « Identité du projet » (ID, nom, typologie, canton…) : l'ID relie toutes les tables du MDP, la typologie et
    /// le canton rangent le projet dans le benchmark. Demandée à chaque export, préremplie avec la dernière réponse pour
    /// ce dossier, complétée par le MDP de la base de même ID ; null si annulée ou incomplète pour cet usage.
    /// </summary>
    internal async Task<MdpProject?> AskMdpProjectAsync(string projectDir, string folderName, IdentityMode mode)
    {
        var known = _settings.FindMdpProject(projectDir) ?? new MdpProject { Name = folderName };
        if (BaseProject(known.Id) is { } inBase) FillFromBase(known, inBase);
        if (known.Name.Length == 0) known.Name = folderName;
        var hrs = await _shell.AskIdentityAsync(known, IdentityLists, mode, mode == IdentityMode.Base ? "Exporter dans la base" : "Continuer");
        if (hrs is null) return null;
        if (ProjectIdentity.Missing(hrs, mode == IdentityMode.Base) is { Count: > 0 } missing)
        {
            _shell.Notify($"Identité incomplète ({string.Join(", ", missing)}) : le MDP n'a pas été exporté.", isError: true);
            return null;
        }
        if (hrs.Name.Length == 0) hrs.Name = folderName;
        _settings.SetMdpProject(projectDir, hrs);
        _settings.Save(_paths);
        return hrs;
    }

    /// <summary>Excel de correction : chaque surface telle que lue, son état corrigé, la correction et son explication.</summary>
    [RelayCommand]
    private Task ExportCorrectionsAsync()
    {
        if (ProjectDir is null || _engine is null || Document is null) return Task.CompletedTask;
        var inputs = CurrentEngineInputs(ProjectDir);
        if (inputs.Journal is null)
        {
            _shell.Notify("Aucune décision sur les corrections pour ce projet : l'Excel de correction serait vide.");
            return Task.CompletedTask;
        }
        var path = _shell.PickSaveFile("Enregistrer l'Excel de correction", $"{AiReviewFiles.Prefix(Document.Project)}-Corrections.xlsx", "Classeur Excel|*.xlsx");
        return path is null ? Task.CompletedTask
            : RunExportAsync(() => _engine.ExportCorrectionsAsync(ProjectDir, path, inputs, CancellationToken.None),
                             $"Excel de correction enregistré : {path}.", path);
    }

    /// <summary>Exports au gabarit Excel Treegram (SurfacesNettes, SurfacesBrutes), surfaces corrigées.</summary>
    [RelayCommand]
    private Task ExportTreegramAsync()
    {
        if (ProjectDir is null || _engine is null) return Task.CompletedTask;
        var dir = _shell.PickFolder("Dossier des exports au gabarit Treegram", null);
        return dir is null ? Task.CompletedTask
            : RunExportAsync(() => _engine.ExportTreegramAsync(ProjectDir, dir, CurrentEngineInputs(ProjectDir), CancellationToken.None),
                             $"Exports Treegram enregistrés dans {dir}.");
    }

    private async Task RunExportAsync(Func<Task<EngineRun>> run, string done, string? open = null)
    {
        try
        {
            var r = await run();
            if (r.Succeeded)
            {
                _shell.Notify(done);
                if (open is not null && File.Exists(open)) _shell.OpenFile(open);
            }
            else _shell.Notify(r.ErrorMessage ?? "Export impossible.", isError: true);
        }
        catch (Exception ex) when (ex is IOException or System.ComponentModel.Win32Exception)
        {
            _shell.Notify(ex.Message, isError: true);
        }
    }

    [RelayCommand]
    private void GoHome()
    {
        Document = null;
        Scene = null;
        IsDashboard = false;
        FillRecents();
        if (IsBenchmarkStale) _ = RefreshBenchmarkAsync();
    }

    // ------------------------------------------------------------------ chargement

    /// <summary>Charge un résultat d'analyse déjà produit (tests, ou rouverture).</summary>
    internal void LoadDocument(string projectDir, ViewerDocument doc)
    {
        ProjectDir = projectDir;
        Load(doc);
    }

    private void Load(ViewerDocument doc)
    {
        _suspendSceneUpdates = true;
        _surfaceById = doc.Surfaces.GroupBy(s => s.Id).ToDictionary(g => g.Key, g => g.First());
        var palette = Palette = new SiaPalette(doc.Categories);
        Scene = new SceneController(doc, palette, _shell.GhostColor);

        Layers.Clear();
        var withGeometry = Scene.Codes.ToHashSet();
        foreach (var cat in doc.Categories)
        {
            var surfaces = doc.Surfaces.Where(s => s.DisplayCode == cat.Code && !s.IsExcluded).ToList();
            if (surfaces.Count == 0) continue;   // ex. SHA, normalisé en SH par le moteur
            // Même règle que le moteur : le détail fait foi, le total de niveau sert quand il n'y a pas de détail.
            var counted = surfaces.Any(s => !s.IsLevelTotal) ? surfaces.Where(s => !s.IsLevelTotal).ToList() : surfaces;
            // Totaux sans aire ni géométrie (façades SFN : données d'enveloppe pour le MDP) : rien à montrer en calque.
            if (!withGeometry.Contains(cat.Code) && counted.All(s => (s.Area ?? 0) == 0)) continue;
            var group = cat.Status == "unknown" ? "Codes inconnus"
                : cat.Status != "ignored" && InteriorCodes.Contains(cat.Code) ? "Intérieur"   // SUT : code maison compté dans la SU
                : cat.Status == "ignored" || cat.Family == "custom" ? "USPI · Maison"
                : cat.Family == "uspi" ? "USPI · Maison"
                : InteriorCodes.Contains(cat.Code) ? "Intérieur" : "Extérieur";
            var (title, definition) = palette.Describe(cat.Code);
            var layer = new LayerItem(cat.Code, group, palette.BrushOf(cat.Code), counted.Count,
                                      counted.Sum(s => s.Area ?? 0), group is "Intérieur" or "Extérieur",
                                      withGeometry.Contains(cat.Code), title, definition);
            layer.PropertyChanged += (_, e) => { if (e.PropertyName == nameof(LayerItem.IsVisible)) UpdateLayers(); };
            Layers.Add(layer);
        }

        // SA (abords, SIA 416 §1.2) : toujours un calque, même avant la première découpe appliquée, pour voir les
        // abords créés par les corrections (aperçu 3D) et pouvoir les masquer.
        if (!Layers.Any(l => l.Code == "SA"))
        {
            var (saTitle, saDef) = palette.Describe("SA");
            var sa = new LayerItem("SA", "Extérieur", palette.BrushOf("SA"), 0, 0, true, true, saTitle, saDef);
            sa.PropertyChanged += (_, e) => { if (e.PropertyName == nameof(LayerItem.IsVisible)) UpdateLayers(); };
            var after = Layers.Select((l, i) => (l, i)).LastOrDefault(x => x.l.Group == "Extérieur");
            Layers.Insert(after.l is null ? Layers.Count : after.i + 1, sa);
        }

        Buildings.Clear();
        foreach (var b in doc.Levels.Select(l => l.Building).Distinct().Order())
        {
            var chip = new BuildingChip(b);
            chip.PropertyChanged += (_, e) => { if (e.PropertyName == nameof(BuildingChip.IsSelected)) OnBuildingsChanged(); };
            Buildings.Add(chip);
        }
        BalanceChoices.Clear();
        if (Buildings.Count > 1) BalanceChoices.Add(new ChoiceItem("Tous les bâtiments", Ratio.AllBuildings));
        foreach (var b in Buildings) BalanceChoices.Add(new ChoiceItem(b.Name, b.Name));
        ClearBalancePreview();
        _store = ReviewStore.Open(_paths.ReviewFile(ProjectDir!), ProjectDir!);
        LoadIssues(doc);
        LoadAiReview(doc);
        Document = doc;
        LoadSubjects(doc);
        _suspendSceneUpdates = false;
        OnBuildingsChanged();
        UpdateLayers();
        Explode = 0;
        _settings.Touch(ProjectDir!, doc.Project, DateTime.Now, doc.Issues.Count);
        _settings.Save(_paths);
        try
        {
            LoadProjectStatus(ProjectDir!, doc.Project, doc.Issues.Count);
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            _shell.Notify($"Registre des projets illisible : {ex.Message}", isError: true);
        }
        OnPropertyChanged(string.Empty);   // en-têtes, bandeaux, barre d'état
        _shell.Frame(null);
    }

    private void LoadIssues(ViewerDocument doc)
    {
        Issues.Clear();
        foreach (var i in doc.Issues) Issues.Add(Track(new IssueItem(i, _store!.Get(i.Key))));
        foreach (var (key, entry) in _store!.Reconcile(doc.Issues, doc.Date)) Issues.Add(Track(new IssueItem(key, entry)));
        Rules.Clear();
        Rules.Add(new ChoiceItem("Toutes les règles", ""));
        foreach (var r in Issues.Select(i => i.Rule).Distinct().Order()) Rules.Add(new ChoiceItem(r, r));
        RuleFilter = "";
        ErrorCount = doc.Issues.Count(i => i.Verdict == "ERREUR");
        WarningCount = doc.Issues.Count(i => i.Verdict == "ALERTE");
        InfoCount = doc.Issues.Count(i => i.Verdict == "INFO");
        SelectedIssue = null;
        IssuesView.Refresh();
        OnPropertyChanged(nameof(IssuesEmptyMessage));
    }

    private IssueItem Track(IssueItem item)
    {
        item.PropertyChanged += (_, e) =>
        {
            if (e.PropertyName == nameof(IssueItem.Status)) { SaveReview(item); IssuesView.Refresh(); UpdateAiCounts(); UpdateAllPointCounts(); }
            else if (e.PropertyName == nameof(IssueItem.Comment)) { _commentSave.Stop(); _commentSave.Start(); }
        };
        return item;
    }

    private void SaveReview(IssueItem? item)
    {
        if (item is null || _store is null || Document is null) return;
        _store.Set(item.Key, item.Status, item.Comment, item.Issue, Document.Date);
    }

    // ------------------------------------------------------------------ calques et filtres

    public ObservableCollection<LayerItem> Layers { get; } = [];
    public ICollectionView LayersView { get; }
    public ObservableCollection<BuildingChip> Buildings { get; } = [];
    public ObservableCollection<string> Levels { get; } = [];
    [ObservableProperty] private string _selectedLevel = AllLevels;
    [ObservableProperty] private double _explode;

    public bool NoLayerVisible => Layers.Count > 0 && Layers.Where(l => l.HasGeometry).All(l => !l.IsVisible);

    partial void OnSelectedLevelChanged(string value) => UpdateFilter();
    partial void OnExplodeChanged(double value) => Scene?.SetExplode(value);

    private IEnumerable<string>? SelectedBuildings =>
        Buildings.Any(b => b.IsSelected) ? Buildings.Where(b => b.IsSelected).Select(b => b.Name).ToList() : null;

    private void OnBuildingsChanged()
    {
        if (_suspendSceneUpdates || Document is null) return;
        var keep = SelectedLevel;
        var sel = SelectedBuildings?.ToHashSet();
        Levels.Clear();
        Levels.Add(AllLevels);
        foreach (var l in Document.Levels.Where(l => sel is null || sel.Contains(l.Building))
                     .GroupBy(l => l.Level).OrderByDescending(g => g.Max(l => l.Rank ?? 0)))
            Levels.Add(l.Key);
        SelectedLevel = Levels.Contains(keep) ? keep : AllLevels;
        UpdateFilter();
        UpdateBalance();
        IssuesView.Refresh();
        OnPropertyChanged(nameof(IssuesEmptyMessage));
    }

    private void UpdateFilter()
    {
        if (_suspendSceneUpdates) return;
        Scene?.SetFilter(SelectedBuildings, SelectedLevel == AllLevels ? null : SelectedLevel);
    }

    private void UpdateLayers()
    {
        if (_suspendSceneUpdates) return;
        Scene?.SetVisibleCodes(Layers.Where(l => l.IsVisible).Select(l => l.Code), Layers.Select(l => l.Code));
        OnPropertyChanged(nameof(NoLayerVisible));
    }

    [RelayCommand]
    private void ShowAllLayers()
    {
        _suspendSceneUpdates = true;
        foreach (var l in Layers.Where(l => l.HasGeometry)) l.IsVisible = true;
        _suspendSceneUpdates = false;
        UpdateLayers();
    }

    [RelayCommand]
    private void SelectAllBuildings()
    {
        _suspendSceneUpdates = true;
        foreach (var b in Buildings) b.IsSelected = false;
        _suspendSceneUpdates = false;
        OnBuildingsChanged();
    }

    // ------------------------------------------------------------------ points d'attention

    public ObservableCollection<IssueItem> Issues { get; } = [];
    public ICollectionView IssuesView { get; }
    public ObservableCollection<ChoiceItem> Rules { get; } = [];
    public IReadOnlyList<ChoiceItem> StatusChoices { get; } =
    [
        new("À traiter", "todo"), new("Vus", "seen"), new("Faux positifs", "false"),
        new("Résolus", "resolved"), new("Tous", "all"),
    ];

    [ObservableProperty] private bool _showErrors = true;
    [ObservableProperty] private bool _showWarnings = true;
    [ObservableProperty] private bool _showInfos = true;
    [ObservableProperty] private string _ruleFilter = "";
    [ObservableProperty] private string _statusFilter = "todo";
    [ObservableProperty] private int _errorCount;
    [ObservableProperty] private int _warningCount;
    [ObservableProperty] private int _infoCount;
    [ObservableProperty] [NotifyPropertyChangedFor(nameof(HasSelectedIssue))] private IssueItem? _selectedIssue;
    public bool HasSelectedIssue => SelectedIssue is not null;

    partial void OnShowErrorsChanged(bool value) => RefreshIssues();
    partial void OnShowWarningsChanged(bool value) => RefreshIssues();
    partial void OnShowInfosChanged(bool value) => RefreshIssues();
    partial void OnRuleFilterChanged(string value) => RefreshIssues();
    partial void OnStatusFilterChanged(string value) => RefreshIssues();

    private void RefreshIssues()
    {
        IssuesView.Refresh();
        OnPropertyChanged(nameof(IssuesEmptyMessage));
    }

    public bool Matches(IssueItem i)
    {
        var verdictOk = i.Verdict switch { "ERREUR" => ShowErrors, "ALERTE" => ShowWarnings, _ => ShowInfos };
        var statusOk = StatusFilter switch
        {
            "todo" => !i.IsResolved && i.Status == ReviewStatus.ToReview,
            "seen" => !i.IsResolved && i.Status == ReviewStatus.Seen,
            "false" => !i.IsResolved && i.Status == ReviewStatus.FalsePositive,
            "resolved" => i.IsResolved,
            _ => true,
        };
        var sel = SelectedBuildings?.ToHashSet();
        var buildingOk = sel is null || i.Building == "*" || sel.Contains(i.Building);
        return verdictOk && statusOk && buildingOk && (RuleFilter == "" || i.Rule == RuleFilter) && MatchesAi(i);
    }

    /// <summary>Message de liste vide : aucun écart (bonne nouvelle) ou filtres trop stricts (plan §5).</summary>
    public string? IssuesEmptyMessage =>
        Document is null || !IssuesView.IsEmpty ? null
        : Document.Issues.Count == 0 ? "Aucun écart au-delà de la tolérance."
        : "Aucun point pour ces filtres.";

    [RelayCommand]
    private void ResetFilters()
    {
        ShowErrors = ShowWarnings = ShowInfos = true;
        RuleFilter = "";
        AiFilter = "";
        StatusFilter = "all";
        SelectAllBuildings();
    }

    [RelayCommand]
    private void FocusIssue(IssueItem? item)
    {
        item ??= SelectedIssue;
        if (item is null || Scene is null) return;
        SelectedIssue = item;
        if (item.IsResolved || item.SurfaceIds.Count == 0)
        {
            _shell.Notify(item.IsResolved ? "Point résolu : il n'existe plus dans la dernière analyse." : "Aucune surface liée à ce point.");
            return;
        }
        var bounds = Scene.Focus(item.SurfaceIds);
        SetFocused(item);
        if (bounds is null) _shell.Notify("Les surfaces de ce point n'ont pas de géométrie dans le cache VWR.");
        _shell.Frame(bounds);
        if (item.Building != "*") BalanceBuilding = item.Building;
    }

    /// <summary>Clic sur un point : l'isole ; clic sur le point déjà isolé : quitte l'isolement (comme un BCF).</summary>
    [RelayCommand]
    private void ToggleFocus(IssueItem? item)
    {
        item ??= SelectedIssue;
        if (item is null) return;
        if (ReferenceEquals(item, FocusedIssue)) CloseIssue();   // second clic : fiche fermée, isolement quitté
        else FocusIssue(item);
    }

    /// <summary>✕ de la fiche du point, ou second clic sur le point : fiche fermée, isolement quitté.</summary>
    [RelayCommand]
    private void CloseIssue()
    {
        SelectedIssue = null;
        ClearFocus();
    }

    /// <summary>✕ de la fiche du sujet, ou second clic sur le sujet : fiche fermée, isolement quitté.</summary>
    [RelayCommand]
    private void CloseSubject()
    {
        SelectedSubject = null;
        ClearFocus();
    }

    [RelayCommand]
    private void ClearFocus()
    {
        Scene?.ClearFocus();
        SetFocused(null);
        SelectSurface(null);
    }

    /// <summary>Point actuellement isolé (null = aucun, ou niveau isolé depuis le bilan).</summary>
    [ObservableProperty] private IssueItem? _focusedIssue;
    [ObservableProperty] private bool _isFocused;

    private void SetFocused(IssueItem? item)
    {
        if (FocusedIssue is not null) FocusedIssue.IsFocused = false;
        FocusedIssue = item;
        if (item is not null) item.IsFocused = true;
        IsFocused = Scene?.IsFocused ?? false;
    }

    [RelayCommand]
    private void SetStatus(string status)
    {
        if (SelectedIssue is null || SelectedIssue.IsResolved) return;
        SelectedIssue.Status = status switch
        {
            "seen" => ReviewStatus.Seen,
            "false" => ReviewStatus.FalsePositive,
            _ => ReviewStatus.ToReview,
        };
    }

    [RelayCommand]
    private void FrameAll() => _shell.Frame(null);

    // ------------------------------------------------------------------ sélection 3D

    [ObservableProperty] [NotifyPropertyChangedFor(nameof(HasSelectedSurface))] private SurfaceInfo? _selectedSurface;
    public bool HasSelectedSurface => SelectedSurface is not null;

    /// <summary>
    /// Surface cliquée en 3D : fiche + marquage dans la liste des points qui la citent.
    /// La fenêtre fait défiler la liste jusqu'au premier (événement <see cref="LinkedIssuesChanged"/>).
    /// </summary>
    public void SelectSurface(string? id)
    {
        foreach (var i in Issues.Where(i => i.IsLinked)) i.IsLinked = false;
        if (id is not null && SiaCheck.Viewer.Scene.SceneController.IsPreview(id)) { SelectedSurface = PendingSurface(id); return; }
        if (id is not null && Document?.IslandById.TryGetValue(id, out var island) == true)
        {   // îlot d'une surface en plusieurs morceaux : sa propre fiche, les points de la surface d'origine
            var parentLinked = Issues.Where(i => i.SurfaceIds.Contains(island.IslandOf!)).OrderBy(i => i.SortKey).ToList();
            foreach (var i in parentLinked) i.IsLinked = true;
            SelectedSurface = new SurfaceInfo(Current(island), parentLinked);   // amputé des parts découpées en attente
            LinkedIssuesChanged?.Invoke(parentLinked.FirstOrDefault(Matches));
            return;
        }
        if (id is null || !_surfaceById.TryGetValue(id, out var s)) { SelectedSurface = null; return; }
        var linked = Issues.Where(i => i.SurfaceIds.Contains(id)).OrderBy(i => i.SortKey).ToList();
        foreach (var i in linked) i.IsLinked = true;
        SelectedSurface = new SurfaceInfo(Current(s), linked);
        LinkedIssuesChanged?.Invoke(linked.FirstOrDefault(Matches));
    }

    /// <summary>Premier point visible (selon les filtres) qui cite la surface cliquée, ou null.</summary>
    public event Action<IssueItem?>? LinkedIssuesChanged;

    [RelayCommand]
    private void SelectLinkedIssue(IssueItem item)
    {
        if (!Matches(item)) ResetFilters();
        SelectedIssue = item;
        FocusIssue(item);
    }

    // ------------------------------------------------------------------ bilan par niveau (signature)

    public ObservableCollection<BalanceRow> BalanceRows { get; } = [];
    /// <summary>Bâtiment du bilan et des ratios ; « * » (<see cref="Ratio.AllBuildings"/>) = tous les bâtiments.</summary>
    [ObservableProperty] [NotifyPropertyChangedFor(nameof(BalanceScopeLabel))] private string? _balanceBuilding;
    /// <summary>Choix du bilan : chaque bâtiment, et « Tous les bâtiments » quand il y en a plusieurs.</summary>
    public ObservableCollection<ChoiceItem> BalanceChoices { get; } = [];
    public string? BalanceScopeLabel => BalanceBuilding == Ratio.AllBuildings ? "Tous les bâtiments" : BalanceBuilding;
    private bool IsAllBuildings => BalanceBuilding == Ratio.AllBuildings;
    [ObservableProperty] private bool _isBalanceCollapsed;

    partial void OnBalanceBuildingChanged(string? value) => FillBalance();

    partial void OnIsBalanceCollapsedChanged(bool value)
    {
        _settings.BalanceCollapsed = value;
        _settings.Save(_paths);
    }

    /// <summary>Second onglet de la zone bilan : ratios informatifs du projet et du bâtiment choisi.</summary>
    public ObservableCollection<RatioRow> RatioRows { get; } = [];
    [ObservableProperty] private bool _showRatios;
    public bool HasRatios => RatioRows.Count > 0;

    partial void OnShowRatiosChanged(bool value)
    {
        _settings.ShowRatios = value;
        _settings.Save(_paths);
    }

    private void UpdateBalance()
    {
        var sel = SelectedBuildings?.ToList();
        BalanceBuilding = sel is { Count: 1 } ? sel[0] : BalanceBuilding ?? Buildings.FirstOrDefault()?.Name;
        FillBalance();
    }

    private void FillBalance()
    {
        BalanceRows.Clear();
        FillRatios();
        if (Document is null || BalanceBuilding is null) return;
        // Tous les bâtiments : une ligne par bâtiment, somme de ses niveaux ; sinon les niveaux du bâtiment choisi.
        var levels = IsAllBuildings
            ? BalanceLevels.GroupBy(l => l.Building).OrderByDescending(g => g.Key, StringComparer.Ordinal).Select(BuildingTotal).ToList()
            : BalanceLevels.Where(l => l.Building == BalanceBuilding).OrderByDescending(l => l.Rank ?? 0).ToList();
        var scale = levels.Select(l => Math.Max(Math.Max(l.Value("SP"), l.Value("SEP")),
                                                Math.Max(l.Before?.Value("SP") ?? 0, l.Before?.Value("SEP") ?? 0)))
                          .DefaultIfEmpty(1).Max();
        foreach (var l in levels)
            BalanceRows.Add(new BalanceRow(l, scale <= 0 ? 1 : scale));
    }

    private static readonly string[] VerdictOrder = ["OK", "INFO", "ALERTE", "ERREUR"];

    /// <summary>Bilan d'un bâtiment entier : valeurs et écarts sommés sur ses niveaux, verdict le plus grave.</summary>
    private static LevelBalance BuildingTotal(IGrouping<string, LevelBalance> levels)
    {
        static Dictionary<string, double> Sum(IEnumerable<Dictionary<string, double>> values) =>
            values.SelectMany(v => v).GroupBy(kv => kv.Key).ToDictionary(g => g.Key, g => g.Sum(kv => kv.Value));
        static CheckResult? Check(IEnumerable<CheckResult?> checks)
        {
            var list = checks.OfType<CheckResult>().ToList();
            return list.Count == 0 ? null : new CheckResult
            {
                Diff = list.Sum(c => c.Diff ?? 0),
                Verdict = list.Select(c => c.Verdict).MaxBy(v => Array.IndexOf(VerdictOrder, v)) ?? "",
            };
        }
        var all = levels.ToList();
        var befores = all.Select(l => l.Before).OfType<LevelBefore>().ToList();
        return new LevelBalance
        {
            Building = levels.Key, Level = levels.Key,
            Values = Sum(all.Select(l => l.Values)),
            R1 = Check(all.Select(l => l.R1)), R3 = Check(all.Select(l => l.R3)),
            Alerts = all.SelectMany(l => l.Alerts).Distinct().ToList(),
            Before = befores.Count == 0 ? null : new LevelBefore
            {
                Values = Sum(befores.Select(b => b.Values)), R1 = Check(befores.Select(b => b.R1)), R3 = Check(befores.Select(b => b.R3)),
            },
        };
    }

    private void FillRatios()
    {
        RatioRows.Clear();
        if (Document is not null)
            foreach (var p in BalanceRatios.Where(r => r.Building == Ratio.AllBuildings))
                RatioRows.Add(new RatioRow(p, IsAllBuildings ? null
                    : BalanceRatios.FirstOrDefault(r => r.Id == p.Id && r.Building == BalanceBuilding)));
        OnPropertyChanged(nameof(HasRatios));
    }

    [RelayCommand]
    private void IsolateLevel(BalanceRow row)
    {
        if (Scene is null || Document is null) return;
        // Ligne d'un bâtiment entier (bilan « Tous les bâtiments ») : tous ses niveaux.
        var ids = IsAllBuildings
            ? Document.Levels.Where(l => l.Building == row.Building).SelectMany(l => Scene.SurfacesOfLevel(l.Building, l.Level))
            : Scene.SurfacesOfLevel(row.Building, row.Level);
        var bounds = Scene.Focus(ids);
        SetFocused(null);
        _shell.Frame(bounds);
    }

    // ------------------------------------------------------------------ thème

    [RelayCommand]
    private void ToggleTheme()
    {
        _settings.Theme = _settings.Theme == "Dark" ? "Light" : "Dark";
        _settings.Save(_paths);
        _shell.ApplyTheme(_settings.Theme);
    }
}
