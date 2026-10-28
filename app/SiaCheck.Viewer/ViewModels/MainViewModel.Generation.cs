using System.Collections.ObjectModel;
using System.ComponentModel;
using System.IO;
using System.Text.RegularExpressions;
using System.Windows.Data;
using System.Windows.Media;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using SiaCheck.Viewer.Models;
using SiaCheck.Viewer.Scene;
using SiaCheck.Viewer.Services;

namespace SiaCheck.Viewer.ViewModels;

/// <summary>
/// Génération depuis l'IFC (V4, docs/DESIGN_PLAN.md Évolution 4.0) : colonne de l'accueil, onglet « Espaces » de
/// l'espace de revue, décisions de classement et analyse IA. Le moteur fait tout le travail (--generer, --decider,
/// --accepter-ia, --questions-ia, --reponse-ia) ; l'app lit ses JSON et ne les écrit jamais.
/// </summary>
public sealed partial class MainViewModel
{
    public static readonly string[] SpaceCodes = ["SUP", "SUS", "SUT", "SD", "SI", "SEU", "SED", "SEI"];
    /// <summary>Sous-types Treegram par code : mêmes listes que generation/ia.py (TYPES).</summary>
    public static readonly Dictionary<string, string[]> SpaceTypes = new()
    {
        ["SUP"] = ["PieceDeVie", "Chambre", "PieceSecondaire_2PointsEau", "PieceSecondaire_3PointsEau", "PieceSecondaire_4PointsEau", "Distribution"],
        ["SUS"] = ["Parking", "Cave", "Buanderie", "LocalVelos", "LocalPoussettes", "LocalConcierge", "Depot", "Sanitaires", "LocauxCommuns"],
        ["SUT"] = ["Commerce"], ["SD"] = ["CirculationH", "Escalier", "Ascenseur"], ["SI"] = ["Gaine", "Local"],
        ["SEU"] = ["Balcon", "Terrasse"], ["SED"] = ["CirculationExt"], ["SEI"] = [],
    };

    private GenerationReport? _genReport;
    private List<GenerationDecision> _genDecisions = [];

    // ------------------------------------------------------------------ accueil

    public ObservableCollection<GeneratedItem> GeneratedProjects { get; } = [];

    private const string GenerationFolderName = "SIA Check - projets generes";

    /// <summary>
    /// Dossier choisi, sinon « Documents\SIA Check - projets generes » : celui du profil s'il existe (Documents redirigé
    /// vers OneDrive ou non), sinon celui de Windows.
    /// </summary>
    private string GenerationFolder => _settings.GenerationFolder is { Length: > 0 } f ? f
        : new[] { Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments),
                  Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "Documents") }
              .Select(d => Path.Combine(d, GenerationFolderName)).FirstOrDefault(Directory.Exists)
          ?? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments), GenerationFolderName);

    /// <summary>Projets générés : tout sous-dossier du dossier des projets générés qui a un rapport de génération.</summary>
    private void FillGenerated()
    {
        GeneratedProjects.Clear();
        if (!Directory.Exists(GenerationFolder)) return;
        var items = new List<GeneratedItem>();
        foreach (var dir in Directory.EnumerateDirectories(GenerationFolder).Where(GenerationReport.Exists))
        {
            try
            {
                var report = GenerationReport.Load(dir);
                items.Add(new GeneratedItem(Path.GetFileName(dir), dir, report.Source, File.GetLastWriteTime(GenerationReport.PathOf(dir)),
                                            GenerationState.Of(report, GenerationDecision.Load(dir))));
            }
            catch (Exception ex) when (ex is IOException or System.Text.Json.JsonException) { /* rapport illisible : ignoré */ }
        }
        foreach (var i in items.OrderByDescending(i => i.Date)) GeneratedProjects.Add(i);
    }

    /// <summary>Générer depuis un IFC… : la maquette, puis le nom et le dossier du projet, puis la génération et l'ouverture.</summary>
    [RelayCommand]
    private async Task GenerateFromIfcAsync()
    {
        if (_engine is null) return;
        var ifc = _shell.PickOpenFile("Maquette architecte IFC (avec ses IfcSpace)", "Maquette IFC|*.ifc");
        if (ifc is null) return;
        var answer = await _shell.AskAsync("Générer depuis un IFC",
            "Le moteur lit la maquette, classe ses espaces et écrit les surfaces SIA au modèle Treegram. Comptez de 30 s à quelques minutes.",
            [("Nom du projet", CleanName(Path.GetFileNameWithoutExtension(ifc))), ("Dossier des projets générés", GenerationFolder)], "Générer");
        if (answer is not [var name, var folder] || CleanName(name) is not { Length: > 0 } project) return;
        if (!string.Equals(folder, GenerationFolder, StringComparison.OrdinalIgnoreCase))
        {
            _settings.GenerationFolder = folder;
            _settings.Save(_paths);
        }
        await RunGenerationAsync(ifc, folder, project);
    }

    /// <summary>Nom utilisable par le moteur (assemble.clean) : pas de « _ », pas d'espace.</summary>
    private static string CleanName(string name) => Regex.Replace(name.Trim(), @"[-_\s]+", "-").Trim('-');

    [RelayCommand]
    private Task OpenGeneratedAsync(GeneratedItem item) => OpenGeneratedDirAsync(item.Path);

    private async Task OpenGeneratedDirAsync(string dir)
    {
        await OpenAsync(dir);
        if (IsGenerated) ShowSpacesTab();
    }

    [RelayCommand]
    private Task RegenerateItemAsync(GeneratedItem item) => RegenerateDirAsync(item.Path, item.Source);

    // ------------------------------------------------------------------ génération

    /// <summary>Projet ouvert généré depuis l'IFC : onglet Espaces, Régénérer, calque Maquette IFC.</summary>
    public bool IsGenerated => _genReport is not null;

    [RelayCommand]
    private Task RegenerateAsync() =>
        ProjectDir is null || _genReport is null ? Task.CompletedTask : RegenerateDirAsync(ProjectDir, _genReport.Source);

    /// <summary>Régénère un projet depuis sa maquette (décisions acceptées appliquées) ; maquette déplacée : on la redemande.</summary>
    private async Task RegenerateDirAsync(string dir, string source)
    {
        if (!File.Exists(source))
        {
            _shell.Notify($"Maquette introuvable : {source}. Choisissez-la.", isError: true);
            source = _shell.PickOpenFile($"Maquette IFC de {Path.GetFileName(dir)}", "Maquette IFC|*.ifc") ?? "";
            if (source.Length == 0) return;
        }
        await RunGenerationAsync(source, Path.GetDirectoryName(Path.GetFullPath(dir))!, Path.GetFileName(Path.GetFullPath(dir)));
    }

    private async Task RunGenerationAsync(string ifc, string outDir, string project)
    {
        if (_engine is null || IsAnalysing) return;
        HomeError = null;
        AnalysisError = null;
        (OverlayTitle, OverlayStepCount, OverlayStepsText) = ($"Génération de {project}", 4, "maquette, plans, classement, surfaces SIA et USPI");
        AnalysisCorrections = "";
        AnalysisStep = 0;
        AnalysisLabel = $"Lecture de {Path.GetFileName(ifc)}";
        IsAnalysing = true;
        _cts = new CancellationTokenSource();
        var dir = Path.Combine(outDir, project);
        var keepTab = ShowSpaces;
        try
        {
            var progress = new Progress<AnalysisProgress>(p => { AnalysisStep = p.Step; AnalysisLabel = p.Label; });
            var run = await _engine.GenerateAsync(ifc, outDir, project, progress, _cts.Token);
            if (!run.Succeeded)
            {
                // Audit bloquant (code 1) : les points du moteur, mot pour mot
                var blocking = run.Log.Split('\n').Select(l => l.Trim()).Where(l => l.StartsWith("ERROR ")).Select(l => l[6..]).ToList();
                Fail(blocking.Count > 0 ? "Génération impossible : " + string.Join(" · ", blocking)
                     : run.ErrorMessage ?? $"Le moteur s'est arrêté avec le code {run.ExitCode}.");
                return;
            }
        }
        catch (OperationCanceledException)
        {
            _shell.Notify("Génération annulée. Le projet précédent est conservé.");
            return;
        }
        catch (Exception ex) when (ex is IOException or System.ComponentModel.Win32Exception)
        {
            Fail(ex.Message);
            return;
        }
        finally
        {
            IsAnalysing = false;
            _cts?.Dispose();
            _cts = null;
        }
        if (HasDocument && ProjectDir is not null && ProjectFolder.Same(ProjectDir, dir)) await AnalyseAsync();
        else await OpenAsync(dir);
        if (IsGenerated && (keepTab || !HasSubjects)) ShowSpacesTab();
        FillGenerated();
    }

    // ------------------------------------------------------------------ onglet Espaces

    public ObservableCollection<SpaceItem> Spaces { get; } = [];
    private ICollectionView? _spacesView;
    public ICollectionView SpacesView => _spacesView ??= CreateSpacesView();
    public IReadOnlyList<ChoiceItem> SpaceFilters { get; } =
        [new("À trancher", "todo"), new("Proposés par l'IA", "ia"), new("Décidés", "done"), new("Tous", "all")];

    [ObservableProperty] [NotifyPropertyChangedFor(nameof(ShowPoints))] private bool _showSpaces;
    [ObservableProperty] private string _spaceFilter = "todo";
    [ObservableProperty] [NotifyPropertyChangedFor(nameof(HasSelectedSpace), nameof(EditTypes))] private SpaceItem? _selectedSpace;
    [ObservableProperty] [NotifyPropertyChangedFor(nameof(EditTypes))] private string? _editCode;
    [ObservableProperty] private string? _editType;
    [ObservableProperty] private GenerationState _genState = new(0, 0, 0);

    public bool HasSelectedSpace => SelectedSpace is not null;
    public IReadOnlyList<string> EditTypes => EditCode is not null && SpaceTypes.TryGetValue(EditCode, out var t) ? t : [];
    public int SpacesShown => SpacesView.Cast<object>().Count();
    public bool HasNoSpaceToShow => IsGenerated && SpacesShown == 0;
    public string SpacesEmptyText => SpaceFilter == "todo"
        ? "Les règles et vos décisions couvrent tous les espaces." : "Aucun espace pour ce filtre.";
    public string ToApplyText => GenState.ToApply switch
    {
        0 => "",
        1 => "1 décision s'appliquera à la prochaine génération.",
        var n => $"{n} décisions s'appliqueront à la prochaine génération.",
    };
    public bool CanAnalyseIa => IsGenerated && GenState.ToDecide > 0;
    public string AnalyseIaTooltip => CanAnalyseIa
        ? $"{GenState.ToDecide} espaces où les règles hésitent : demander à l'IA (estimation du coût et accord avant l'appel)"
        : "Les règles n'hésitent sur aucun espace";

    [ObservableProperty] private bool _showIfcContext;
    public bool HasIfcContext => Scene?.HasContext ?? false;
    private string _ifcContextTooltip = "";
    public string IfcContextTooltip => _ifcContextTooltip;

    private ICollectionView CreateSpacesView()
    {
        var v = new ListCollectionView(Spaces) { Filter = o => o is SpaceItem s && s.Matches(SpaceFilter) };
        v.SortDescriptions.Add(new SortDescription(nameof(SpaceItem.SortKey), ListSortDirection.Ascending));
        return v;
    }

    [RelayCommand]
    private void ShowSpacesTab()
    {
        if (!IsGenerated) return;
        ShowSubjects = false;
        ShowSpaces = true;
    }

    partial void OnSpaceFilterChanged(string value) => RefreshSpaces();
    partial void OnShowIfcContextChanged(bool value)
    {
        Scene?.ShowContext(value);
        if (_settings.ShowIfcContext == value) return;
        _settings.ShowIfcContext = value;
        _settings.Save(_paths);
    }

    partial void OnSelectedSpaceChanged(SpaceItem? value)
    {
        EditCode = value?.TargetCode;
        EditType = value?.TargetType;
        if (value?.Space.Surface is not { } id || Scene is null) return;
        var bounds = Scene.Focus([id]);
        if (bounds is not null) _shell.Frame(bounds);
    }

    partial void OnEditCodeChanged(string? value)
    {
        if (value is null || EditType is not null && EditTypes.Contains(EditType)) return;
        EditType = EditTypes.FirstOrDefault();
    }

    /// <summary>Projet ouvert : rapport et journal relus s'il vient du moteur de génération, sinon rien.</summary>
    private void LoadGeneration()
    {
        _genReport = null;
        if (ProjectDir is not null && ProjectFolder.Sources(ProjectDir) is [var src] && ProjectFolder.IsSiagen(src)
            && GenerationReport.Exists(ProjectDir))
        {
            try { _genReport = GenerationReport.Load(ProjectDir); }
            catch (Exception ex) when (ex is IOException or System.Text.Json.JsonException)
            {
                _shell.Notify($"Rapport de génération illisible : {ex.Message}", isError: true);
            }
        }
        ReloadDecisions(keepSelection: false);
        if (Scene is not null && ProjectDir is not null && IsGenerated)
        {
            ContextModel? context = null;
            try { context = ContextModel.Load(ProjectDir); }
            catch (Exception ex) when (ex is IOException or System.Text.Json.JsonException or FormatException) { /* calque grisé */ }
            Scene.SetContext(context, Color.FromArgb(0x38, 0x9B, 0xA1, 0xAD));
            _ifcContextTooltip = context is null ? "Régénérez le projet pour afficher sa maquette."
                : context.Elements.Count == 0 ? "La maquette ne contient ni murs, ni dalles, ni toits, ni poteaux (export des seules pièces ?)."
                : "Murs, dalles, toits et poteaux de la maquette, en gris translucide.";
            ShowIfcContext = _settings.ShowIfcContext && Scene.HasContext;
            Scene.ShowContext(ShowIfcContext);
        }
        if (!IsGenerated) ShowSpaces = false;
        OnPropertyChanged(nameof(IsGenerated));
        OnPropertyChanged(nameof(HasIfcContext));
        OnPropertyChanged(nameof(IfcContextTooltip));
    }

    /// <summary>Journal relu (après une décision du moteur) : lignes, état, bandeau, aperçu 3D.</summary>
    private void ReloadDecisions(bool keepSelection = true)
    {
        var selected = keepSelection ? SelectedSpace?.Space.Gid : null;
        try { _genDecisions = ProjectDir is null || _genReport is null ? [] : GenerationDecision.Load(ProjectDir); }
        catch (Exception ex) when (ex is IOException or System.Text.Json.JsonException)
        {
            _genDecisions = [];
            _shell.Notify($"Journal des décisions illisible : {ex.Message}", isError: true);
        }
        var by = _genDecisions.GroupBy(d => d.Id).ToDictionary(g => g.Key, g => g.Last());
        Spaces.Clear();
        if (_genReport is not null && Palette is not null)
            foreach (var s in _genReport.Spaces.Where(s => s.IsClassified))
                Spaces.Add(new SpaceItem(s, by.GetValueOrDefault(s.Gid), Palette));
        GenState = _genReport is null ? new(0, 0, 0) : GenerationState.Of(_genReport, _genDecisions);
        RefreshSpaces();
        SelectedSpace = selected is null ? null : Spaces.FirstOrDefault(x => x.Space.Gid == selected);
        UpdateScenePreview();
    }

    private void RefreshSpaces()
    {
        SpacesView.Refresh();
        OnPropertyChanged(nameof(SpacesShown));
        OnPropertyChanged(nameof(HasNoSpaceToShow));
        OnPropertyChanged(nameof(SpacesEmptyText));
        OnPropertyChanged(nameof(ToApplyText));
        OnPropertyChanged(nameof(CanAnalyseIa));
        OnPropertyChanged(nameof(AnalyseIaTooltip));
    }

    /// <summary>Aperçu 3D : une surface dont la décision acceptée attend la régénération prend déjà sa couleur cible.</summary>
    private IEnumerable<ScenePreview> GenerationPreview() =>
        Spaces.Where(s => s.IsWaiting && s.Space.Surface is not null)
              .Select(s => new ScenePreview("gen:" + s.Space.Gid, [], [s.Space.Surface!], s.TargetCode, null, null, null));

    [RelayCommand]
    private Task AcceptProposalAsync() => SettleAsync(accept: true);

    [RelayCommand]
    private Task RejectProposalAsync() => SettleAsync(accept: false);

    private async Task SettleAsync(bool accept)
    {
        if (_engine is null || ProjectDir is null || SelectedSpace is not { IsOpenProposal: true } s) return;
        var run = await _engine.SettleIaAsync(ProjectDir, [s.Space.Gid], accept, CancellationToken.None);
        if (!run.Succeeded) { _shell.Notify(run.ErrorMessage ?? "Décision non enregistrée.", isError: true); return; }
        ReloadDecisions();
    }

    /// <summary>Enregistrer ce choix : décision manuelle (code et type des listes), qui remplace toute proposition.</summary>
    [RelayCommand]
    private async Task SaveSpaceChoiceAsync()
    {
        if (_engine is null || ProjectDir is null || SelectedSpace is not { } s || EditCode is null) return;
        var type = EditTypes.Contains(EditType ?? "") ? EditType : null;
        var run = await _engine.DecideAsync(ProjectDir, [s.Space.Gid], EditCode, type, CancellationToken.None);
        if (!run.Succeeded) { _shell.Notify(run.ErrorMessage ?? "Choix non enregistré.", isError: true); return; }
        ReloadDecisions();
        _shell.Notify($"{s.Label} : {EditCode}{(type is null ? "" : " " + type)}, appliqué à la prochaine génération.");
    }

    /// <summary>✦ Analyse IA… : questions du moteur, estimation, accord, appel (clé DPAPI), propositions au journal.</summary>
    [RelayCommand]
    private async Task AnalyseGenerationIaAsync()
    {
        if (_engine is null || ProjectDir is null || !IsGenerated) return;
        const string title = "Analyse IA de la génération";
        var key = Keys.Load();
        if (key is null)
        {
            _shell.Notify("Aucune clé API : saisissez-la dans la revue IA (bouton « Revue IA »).", isError: true);
            return;
        }
        var dir = ProjectDir;
        try
        {
            var service = new AiGenerationService(_engine);
            var prompt = await service.PrepareAsync(dir, CancellationToken.None);
            if (prompt.IssueCount == 0) { _shell.Notify("Les règles n'hésitent sur aucun espace : rien à demander à l'IA."); return; }
            var client = new AiReviewClient(key);
            var cost = await client.EstimateAsync(prompt, CancellationToken.None);
            if (!await _shell.ConfirmAsync(title,
                    $"{prompt.IssueCount} espaces où les règles hésitent seront soumis à {AiPricing.ModelLabel}.\n\n" +
                    $"Entrée : {cost.InputTokens:N0} jetons · sortie estimée : {cost.MinOutputTokens:N0} à {cost.MaxOutputTokens:N0} jetons.\n" +
                    $"Coût estimé : {cost.MinUsd:0.00} à {cost.MaxUsd:0.00} $.\n\n" +
                    "Les réponses deviennent des propositions : rien n'est appliqué sans votre accord.", "Lancer l'analyse", "Annuler"))
                return;
            (OverlayTitle, OverlayStepCount, OverlayStepsText) = ($"Analyse IA de {Path.GetFileName(dir)}", 1, "réponse du modèle");
            AnalysisCorrections = "";
            AnalysisStep = 0;
            AnalysisLabel = $"{prompt.IssueCount} questions envoyées à {AiPricing.ModelLabel}";
            IsAnalysing = true;
            _cts = new CancellationTokenSource();
            var progress = new Progress<AiStreamProgress>(p => AnalysisLabel = p.Writing
                ? $"Réponse en cours : ~{p.ApproxTokens:N0} jetons · {p.Elapsed:mm\\:ss}" : $"Réflexion du modèle · {p.Elapsed:mm\\:ss}");
            var response = await client.RunAsync(prompt, progress, _cts.Token);
            AiGenerationService.SaveResponse(dir, response, DateTime.Now);
            var summary = await service.RecordAsync(dir, CancellationToken.None);
            IsAnalysing = false;
            ReloadDecisions(keepSelection: false);
            SpaceFilter = "ia";
            _shell.Notify($"{summary.Replace("INFO ", "")} Coût réel : {response.CostUsd:0.00} $.");
        }
        catch (OperationCanceledException) { _shell.Notify("Analyse IA annulée."); }
        catch (AiReviewException ex) { _shell.Notify(ex.Message, isError: true); }
        finally
        {
            IsAnalysing = false;
            _cts?.Dispose();
            _cts = null;
        }
    }
}

/// <summary>Projet généré de la colonne Génération de l'accueil.</summary>
public sealed record GeneratedItem(string Name, string Path, string Source, DateTime Date, GenerationState State)
{
    public bool IsSettled => State.ToDecide == 0;
    public string StateText => IsSettled ? "tout tranché" : $"{State.ToDecide} à trancher";
}

/// <summary>Ligne de l'onglet Espaces : un espace de la maquette, sa décision éventuelle, le changement qu'elle porte.</summary>
public sealed class SpaceItem(GeneratedSpace space, GenerationDecision? decision, SiaPalette palette)
{
    public GeneratedSpace Space { get; } = space;
    public GenerationDecision? Decision { get; } = decision;

    /// <summary>Liste : le nom long (« Réduit », « TECHNIQUE CUISINE »), plus parlant qu'un numéro de pièce.</summary>
    public string Label => new[] { Space.LongName, Space.Name }.FirstOrDefault(s => !string.IsNullOrWhiteSpace(s)) ?? Space.Gid;
    /// <summary>Détail : nom et nom long.</summary>
    public string FullLabel => Space.Label.Length > 0 ? Space.Label : Space.Gid;
    public string Level => Space.Level ?? Space.Storey ?? "";
    public string ConfidenceText => Space.Confidence.ToString("0.00");
    public string AreaText => (Space.Area ?? Space.AreaPlan) is { } a ? $"{a:N1} m²" : "";
    public bool IsOpenProposal => Decision?.IsOpenProposal ?? false;
    public bool IsDoubtful => Space.IsDoubtful && !(Decision?.IsSettled ?? false);
    /// <summary>Code et type visés : la décision ouverte ou acceptée, sinon le classement actuel.</summary>
    public string? TargetCode => Decision is { Status: "proposée" or "acceptée" } d ? d.Code : Space.Code;
    public string? TargetType => Decision is { Status: "proposée" or "acceptée" } d ? d.Type : Space.Type;
    public bool HasChange => TargetCode != Space.Code;
    /// <summary>Décision acceptée que la dernière génération n'a pas encore appliquée.</summary>
    public bool IsWaiting => Decision is { IsAccepted: true } d && (Space.Code != d.Code || d.Type is not null && Space.Type != d.Type);
    public Brush FromBrush => palette.BrushOf(Space.Code ?? "");
    public Brush ToBrush => palette.BrushOf(TargetCode ?? "");
    public string Origin => Decision?.Origin switch
    {
        "ia" => "✦ IA",
        "manuel" => "manuel",
        _ => Space.Source switch { "ia" => "✦ IA", "manuel" => "manuel", _ => "règle" },
    };
    public string RulesText => $"{Space.Code} {Space.Type} · {Space.Source ?? "aucune source"} · confiance {ConfidenceText}";
    public string RulesReason => Space.Reason;
    public string Conflicts => string.Join(" · ", Space.Conflicts);
    public bool HasConflicts => Space.Conflicts.Count > 0;
    public bool HasIa => Decision is { Origin: "ia" };
    public string IaText => Decision is { Origin: "ia" } d ? $"{d.Code} {d.Type} · {d.Certainty} · {StatusText(d.Status)}" : "";
    public string IaReason => Decision?.Origin == "ia" ? Decision.Reason ?? "" : "";
    public string Neighbours => string.Join(" · ", Space.Neighbours);
    public bool HasNeighbours => Space.Neighbours.Count > 0;
    public string Lot => Space.InLot ? Space.Lot ?? "" : "";

    private static string StatusText(string s) => s switch
    {
        "proposée" => "proposée", "acceptée" => "acceptée", "rejetée" => "rejetée", "confirmée" => "classement des règles confirmé", _ => s,
    };

    /// <summary>Plus douteux d'abord, propositions ouvertes avec eux.</summary>
    public string SortKey => $"{(IsOpenProposal || IsDoubtful ? 0 : 1)}{Space.Confidence:0.000}{Level}{Label}";

    public bool Matches(string filter) => filter switch
    {
        "todo" => IsDoubtful || IsOpenProposal,
        "ia" => Decision is { Origin: "ia", IsOpenProposal: true },
        "done" => Decision is { IsAccepted: true } || Space.Source is "ia" or "manuel",
        _ => true,
    };
}
