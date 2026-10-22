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
    private static readonly string[] InteriorCodes = ["SP", "SN", "SU", "SUP", "SUS", "SD", "SI", "SC", "SCP", "SCN"];

    private readonly IShell _shell;
    private readonly AppPaths _paths;
    private readonly AppSettings _settings;
    private readonly AnalysisService? _engine;
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
        Recents = new ObservableCollection<RecentProject>(settings.Recents.Where(r => Directory.Exists(r.Path)));
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

    public ObservableCollection<RecentProject> Recents { get; }
    [ObservableProperty] private string? _projectDir;
    [ObservableProperty] [NotifyPropertyChangedFor(nameof(HasDocument), nameof(IsHome))] private ViewerDocument? _document;
    [ObservableProperty] private SceneController? _scene;
    [ObservableProperty] private SiaPalette? _palette;
    [ObservableProperty] private string? _homeError;
    [ObservableProperty] [NotifyPropertyChangedFor(nameof(HasAnalysisError))] private string? _analysisError;
    public bool HasAnalysisError => !string.IsNullOrEmpty(AnalysisError);
    [ObservableProperty] private string? _lastLogFile;

    public bool HasDocument => Document is not null;
    public bool IsHome => Document is null;
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
    public bool IsBusy => IsAnalysing;
    public string[] AnalysisSteps { get; } = ["Lecture du .tgm", "Contrôles SIA 416", "Géométrie (cache VWR)"];

    [RelayCommand]
    private async Task OpenProjectAsync()
    {
        var dir = _shell.PickFolder("Dossier du projet Treegram (contient le fichier .tgm et le dossier VWR)", ProjectDir);
        if (dir is not null) await OpenAsync(dir);
    }

    [RelayCommand]
    private Task OpenRecentAsync(RecentProject recent) => OpenAsync(recent.Path);

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
        // Analyse encore valable : rouverture instantanée. Le .tgm a changé : on réanalyse.
        if (File.Exists(cached) && File.GetLastWriteTime(cached) > File.GetLastWriteTime(tgms[0]))
        {
            try { Load(ViewerDocument.Load(cached)); return; }
            catch (Exception ex) when (ex is IOException or InvalidDataException or System.Text.Json.JsonException) { /* réanalyse */ }
        }
        await AnalyseAsync();
    }

    [RelayCommand]
    private async Task AnalyseAsync()
    {
        if (ProjectDir is null || _engine is null || IsAnalysing) return;
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
            var run = await _engine.AnalyseAsync(ProjectDir, tmp, progress, _cts.Token);
            LastLogFile = _paths.LogFile(ProjectDir);
            await File.WriteAllTextAsync(LastLogFile, run.Log);
            if (!run.Succeeded || !File.Exists(tmp))
            {
                Fail(run.ErrorMessage ?? $"Le moteur s'est arrêté avec le code {run.ExitCode}.");
                return;
            }
            File.Move(tmp, json, overwrite: true);
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

    [RelayCommand]
    private async Task ExportAsync()
    {
        if (ProjectDir is null || _engine is null) return;
        var dir = _shell.PickFolder("Dossier des rapports xlsx, html et json", null);
        if (dir is null) return;
        try
        {
            var run = await _engine.ExportAsync(ProjectDir, dir, CancellationToken.None);
            if (run.Succeeded) _shell.Notify($"Rapports enregistrés dans {dir}.");
            else _shell.Notify(run.ErrorMessage ?? "Export impossible.", isError: true);
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
        Recents.Clear();
        foreach (var r in _settings.Recents.Where(r => Directory.Exists(r.Path))) Recents.Add(r);
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
            var surfaces = doc.Surfaces.Where(s => s.DisplayCode == cat.Code).ToList();
            if (surfaces.Count == 0) continue;   // ex. SHA, normalisé en SH par le moteur
            // Même règle que le moteur : le détail fait foi, le total de niveau sert quand il n'y a pas de détail.
            var counted = surfaces.Any(s => !s.IsLevelTotal) ? surfaces.Where(s => !s.IsLevelTotal).ToList() : surfaces;
            var group = cat.Status == "unknown" ? "Codes inconnus"
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

        Buildings.Clear();
        foreach (var b in doc.Levels.Select(l => l.Building).Distinct().Order())
        {
            var chip = new BuildingChip(b);
            chip.PropertyChanged += (_, e) => { if (e.PropertyName == nameof(BuildingChip.IsSelected)) OnBuildingsChanged(); };
            Buildings.Add(chip);
        }
        _store = ReviewStore.Open(_paths.ReviewFile(ProjectDir!), ProjectDir!);
        LoadIssues(doc);
        LoadAiReview(doc);
        Document = doc;
        _suspendSceneUpdates = false;
        OnBuildingsChanged();
        UpdateLayers();
        Explode = 0;
        _settings.Touch(ProjectDir!, doc.Project, DateTime.Now, doc.Issues.Count);
        _settings.Save(_paths);
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
            if (e.PropertyName == nameof(IssueItem.Status)) { SaveReview(item); IssuesView.Refresh(); UpdateAiCounts(); }
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
        Scene?.SetVisibleCodes(Layers.Where(l => l.IsVisible).Select(l => l.Code));
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
        if (ReferenceEquals(item, FocusedIssue)) ClearFocus();
        else FocusIssue(item);
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
        if (id is null || !_surfaceById.TryGetValue(id, out var s)) { SelectedSurface = null; return; }
        var linked = Issues.Where(i => i.SurfaceIds.Contains(id)).OrderBy(i => i.SortKey).ToList();
        foreach (var i in linked) i.IsLinked = true;
        SelectedSurface = new SurfaceInfo(s, linked);
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
    [ObservableProperty] private string? _balanceBuilding;
    [ObservableProperty] private bool _isBalanceCollapsed;

    partial void OnBalanceBuildingChanged(string? value) => FillBalance();

    partial void OnIsBalanceCollapsedChanged(bool value)
    {
        _settings.BalanceCollapsed = value;
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
        if (Document is null || BalanceBuilding is null) return;
        var levels = Document.Levels.Where(l => l.Building == BalanceBuilding).ToList();
        var scale = levels.Select(l => Math.Max(l.Value("SP"), l.Value("SEP"))).DefaultIfEmpty(1).Max();
        foreach (var l in levels.OrderByDescending(l => l.Rank ?? 0))
            BalanceRows.Add(new BalanceRow(l, scale <= 0 ? 1 : scale));
    }

    [RelayCommand]
    private void IsolateLevel(BalanceRow row)
    {
        if (Scene is null) return;
        var bounds = Scene.Focus(Scene.SurfacesOfLevel(row.Building, row.Level));
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
