using System.Collections.ObjectModel;
using System.IO;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using SiaCheck.Viewer.Services;

namespace SiaCheck.Viewer.ViewModels;

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
    /// <summary>Une case par contrôle, dans l'ordre du moteur : pleine = présent. Le détail est sur la page du MDP.</summary>
    public IReadOnlyList<bool> Fingerprint { get; } = p.Checks.Select(c => c.Ok).ToList();

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

    /// <summary>Page d'un MDP de la base (clic sur sa ligne) : identité à remplir en priorité, puis ce qui manque.</summary>
    [ObservableProperty] [NotifyPropertyChangedFor(nameof(IsHome), nameof(IsBaseDetail))] private MdpDetail? _baseDetail;
    public bool IsBaseDetail => BaseDetail is not null;

    // Tri de la liste de la base : clic sur un en-tête (même en-tête : sens inversé)
    private string _baseSortKey = "donnees";
    private bool _baseSortDescending = true;
    /// <summary>Flèche fine du tri, à côté de l'en-tête de la colonne triée ; vide pour les autres.</summary>
    public string SortArrowId => SortArrow("id");
    public string SortArrowName => SortArrow("nom");
    public string SortArrowTypologie => SortArrow("typologie");
    public string SortArrowCanton => SortArrow("canton");
    public string SortArrowData => SortArrow("donnees");
    private string SortArrow(string key) => key == _baseSortKey ? (_baseSortDescending ? "↓" : "↑") : "";
    public string BenchmarkFolderTooltip => HasBenchmarkFolder ? $"Changer le dossier de la base\n{BenchmarkFolder}" : "Choisir le dossier de la base";

    [ObservableProperty] [NotifyPropertyChangedFor(nameof(HasBenchmarkFolder), nameof(BenchmarkEmptyMessage), nameof(BenchmarkFolderTooltip))]
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

    /// <summary>Liste de la base dans l'ordre choisi ; à égalité, fiables d'abord puis par ID.</summary>
    private void FillBenchmarkProjects()
    {
        BenchmarkProjects.Clear();
        if (_benchmarkData is null) return;
        static string Num(string id) => id.PadLeft(12, '0');     // « 1023 » avant « 1714 », comme des nombres
        var items = _benchmarkData.Projects.Select(p => new BenchmarkItem(p));
        Func<BenchmarkItem, IComparable> key = _baseSortKey switch
        {
            "id" => i => Num(i.Id),
            "nom" => i => i.Name,
            "typologie" => i => i.IsIdentified ? i.Typologie : "\uffff",       // non identifiés en fin de liste
            "canton" => i => i.Canton == "—" ? "\uffff" : i.Canton,
            _ => i => (i.IsReliable ? 1 : 0) + i.Project.Score,
        };
        var sorted = _baseSortDescending ? items.OrderByDescending(key, Comparer<IComparable>.Create(Compare))
                                         : items.OrderBy(key, Comparer<IComparable>.Create(Compare));
        foreach (var i in sorted.ThenByDescending(i => i.IsReliable).ThenBy(i => Num(i.Id))) BenchmarkProjects.Add(i);
        foreach (var h in new[] { nameof(SortArrowId), nameof(SortArrowName), nameof(SortArrowTypologie), nameof(SortArrowCanton), nameof(SortArrowData) })
            OnPropertyChanged(h);
    }

    private static int Compare(IComparable? a, IComparable? b) =>
        a is string sa && b is string sb ? string.Compare(sa, sb, StringComparison.CurrentCultureIgnoreCase) : Comparer<IComparable>.Default.Compare(a!, b!);

    [RelayCommand]
    private void SortBase(string key)
    {
        _baseSortDescending = key == _baseSortKey ? !_baseSortDescending : key == "donnees";
        _baseSortKey = key;
        FillBenchmarkProjects();
    }

    [RelayCommand]
    private void OpenBaseDetail(BenchmarkItem item) => BaseDetail = new MdpDetail(item);

    [RelayCommand]
    private void CloseBaseDetail() => BaseDetail = null;

    /// <summary>MDP modifié à la main (Excel) : relit la base ; la page reprend le même fichier.</summary>
    [RelayCommand]
    private Task ReloadBaseDetailAsync() => RefreshBenchmarkAsync();

    [RelayCommand]
    private void OpenBaseMdp()
    {
        if (BaseDetail is null || !HasBenchmarkFolder) return;
        var path = Path.Combine(BenchmarkFolder, BaseDetail.File);
        if (File.Exists(path)) _shell.OpenFile(path);
        else _shell.Notify($"Fichier introuvable : {path}", isError: true);
    }

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
        if (data is null || !HasBenchmarkFolder)
        {
            BaseDetail = null;
            return;
        }
        FillBenchmarkProjects();
        // Page d'un MDP ouverte : elle suit la relecture (même fichier), ou se ferme s'il a disparu
        if (BaseDetail is { } open)
        {
            var same = BenchmarkProjects.FirstOrDefault(i => i.Project.File == open.File)
                       ?? BenchmarkProjects.FirstOrDefault(i => i.Id == open.Item.Id);
            BaseDetail = same is null ? null : new MdpDetail(same);
        }
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
    private Task AddToBaseAsync(RecentItem recent) => AddProjectToBaseAsync(recent.Path, recent.Name, onValidation: false);

    /// <summary>
    /// Exporte le MDP du projet (surfaces corrigées, identité de la fiche) dans le dossier de la base, puis relit la base.
    /// <paramref name="onValidation"/> : appelé au passage en traité ; le projet reste traité si l'export n'a pas lieu,
    /// et chaque cas le dit (le bouton ⇥ de l'accueil permet de réessayer). true si le MDP est dans la base.
    /// </summary>
    internal async Task<bool> AddProjectToBaseAsync(string projectDir, string name, bool onValidation, bool republish = false)
    {
        // Messages : le nom de la fiche projet ; name (dossier) reste le repli de l'identité
        var label = _settings.FindMdpProject(projectDir)?.Name is { Length: > 0 } n ? n : name;
        var done = onValidation ? $"« {label} » passé en traité, " : "";
        void NotAdded(string why) => _shell.Notify($"{done}MDP non ajouté à la base : {why}" +
                                                   (onValidation ? " Réessayez avec ⇥ sur l'accueil." : ""), isError: true);
        if (_engine is null)
        {
            if (onValidation) NotAdded("moteur d'analyse introuvable.");
            return false;
        }
        if (IsBenchmarkLoading)
        {
            if (onValidation) NotAdded("la base est en cours de lecture.");
            return false;
        }
        if (!HasBenchmarkFolder)
        {
            await ChooseBenchmarkFolderAsync();
            if (!HasBenchmarkFolder)
            {
                if (onValidation) NotAdded("aucun dossier de base choisi.");
                return false;
            }
        }
        var hrs = await AskMdpProjectAsync(projectDir, name, IdentityMode.Base);
        if (hrs is null)
        {
            if (onValidation) NotAdded("l'identité du projet est incomplète.");
            return false;
        }
        var existing = BenchmarkBase.FindById(BenchmarkFolder, hrs.Id);
        // Republier : remplacer son propre MDP est le but, pas de question
        if (existing is not null && !republish && !await _shell.ConfirmAsync($"Remplacer {Path.GetFileName(existing)} ?",
                $"La base contient déjà un MDP pour le projet {hrs.Id}. Il sera remplacé par celui de « {label} », " +
                "exporté avec les surfaces corrigées.", "Remplacer", "Garder l'ancien"))
        {
            if (onValidation) _shell.Notify($"{done}le MDP déjà dans la base est gardé.");
            return false;
        }
        var path = existing ?? Path.Combine(BenchmarkFolder, $"MDP-{hrs.Id}-{AiReviewFiles.Prefix(hrs.Name)}.xlsx");
        IsBenchmarkLoading = true;
        BenchmarkActivity = $"Export du MDP de « {label} » dans la base…";
        EngineRun r;
        try
        {
            r = await _engine.ExportMdpAsync(projectDir, path, null, hrs.Id, hrs.Name, CurrentEngineInputs(projectDir),
                                             CancellationToken.None, ProjectIdentity.WriteEngineFile(hrs, IdentityFile));
        }
        catch (Exception ex) when (ex is IOException or System.ComponentModel.Win32Exception or InvalidOperationException)
        {
            NotAdded(ex.Message);
            return false;
        }
        finally
        {
            IsBenchmarkLoading = false;
            BenchmarkActivity = null;
        }
        if (!r.Succeeded)
        {
            NotAdded(r.ErrorMessage ?? "export du MDP impossible.");
            return false;
        }
        _shell.Notify(republish ? $"« {label} » republié dans la base : {Path.GetFileName(path)}."
                      : $"{(onValidation ? done + "et ajouté" : $"« {label} » ajouté")} à la base : {Path.GetFileName(path)}.");
        // MDP de la base à jour : un projet « Traité · modifié » redevient « Traité »
        if (_registry.StatusOf(projectDir) == ProjectStatus.DoneModified)
        {
            var record = _registry.SetStatus(projectDir, ProjectStatus.Done);
            if (ProjectDir is not null && ProjectFolder.Same(ProjectDir, projectDir)) ShowProjectStatus(record);
            FillRecents();
        }
        await RefreshBenchmarkAsync();
        return true;
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
