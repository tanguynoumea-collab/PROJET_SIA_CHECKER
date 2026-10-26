using System.Text.Json;
using System.Windows;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using SiaCheck.Viewer.Models;

namespace SiaCheck.Viewer.ViewModels;

/// <summary>
/// Module de tracé (plan, Évolution 2.1) et édition des surfaces : volet ouvert sur une correction (« Tracer… »,
/// touche T), sur une surface cliquée en 3D (« Modifier la surface… » : emprise et type ; « Découper… » : une part
/// change de catégorie), ou pour une nouvelle surface (« Nouvelle surface » : bâtiment, niveau, type, puis contour).
/// Ce qui est enregistré devient une correction « manuel » du journal ; elle s'applique à la prochaine analyse.
/// Une modification, une création ou une suppression faite à la main est acceptée d'emblée ; une découpe reste
/// une proposition à accepter, comme celles du moteur.
/// </summary>
public sealed partial class MainViewModel
{
    public const string ManualSubject = "manuel";
    private CorrectionItem? _tracedItem;

    /// <summary>Catégories proposées pour une surface modifiée ou créée : la chaîne SIA 416, intérieur puis extérieur.</summary>
    public static readonly string[] SurfaceTypes = ["SUP", "SUS", "SD", "SI", "SC", "SEU", "SED", "SEI", "SEC", "SA", "SP", "SEP"];

    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(IsTraceOpen), nameof(IsTraceManual), nameof(IsTraceCreate), nameof(ShowTraceTargets))]
    private TraceSession? _trace;
    public bool IsTraceOpen => Trace is not null;
    /// <summary>Découpe créée depuis une surface : la catégorie cible se choisit dans le volet.</summary>
    public bool IsTraceManual => Trace is not null && _tracedItem is null;
    public bool IsTraceCreate => Trace?.IsCreate == true;
    /// <summary>Liste des catégories dans l'en-tête : découpe, emprise ou création depuis la 3D (pas une correction retracée).</summary>
    public bool ShowTraceTargets => IsTraceManual;

    /// <summary>Catégories cibles : abords d'abord pour une découpe de SEP, la chaîne SIA sinon.</summary>
    public IReadOnlyList<string> TraceTargets { get; private set; } = [];
    [ObservableProperty] private string _traceTarget = "SA";

    /// <summary>Nouvelle surface : bâtiment et niveau, choisis dans l'en-tête du volet.</summary>
    public IReadOnlyList<string> TraceBuildings { get; private set; } = [];
    public IReadOnlyList<string> TraceLevels { get; private set; } = [];
    [ObservableProperty] private string? _traceBuilding;
    [ObservableProperty] private string? _traceLevel;

    /// <summary>La fenêtre cadre le plan (F, ou à l'ouverture).</summary>
    public event Action? TraceFitRequested;

    public bool CanTraceSelected => SelectedCorrection is { } c && IsTraceable(c.Model);

    private static bool IsTraceable(Correction c) =>
        c.Op is "découper" or "remodeler" or "créer" || c.Op == "exclure" && c.Area is not null;

    private static TraceKind KindOf(Correction c) => c.Op switch { "remodeler" => TraceKind.Reshape, "créer" => TraceKind.Create, _ => TraceKind.Cut };

    [RelayCommand]
    private void OpenTraceForCorrection()
    {
        if (SelectedCorrection is not { } c || !IsTraceable(c.Model)) return;
        var kind = KindOf(c.Model);
        var source = kind == TraceKind.Create ? NewSurface(c.Model)
            : c.TargetIds.Select(id => _surfaceById.GetValueOrDefault(id)).FirstOrDefault(s => s is not null);
        if (source is null) { _shell.Notify("La surface visée n'existe plus dans l'analyse."); return; }
        var target = kind switch { TraceKind.Cut => c.Model.Op == "exclure" ? "" : c.Model.To ?? "SA", _ => c.Model.To ?? source.DisplayCode };
        OpenTrace(source, target, c, kind);
    }

    /// <summary>« Découper… » : une part de la surface change de catégorie.</summary>
    [RelayCommand]
    private void OpenTraceForSurface()
    {
        if (SelectedSurface?.Surface is not { } s) return;
        SetTraceTargets(s.DisplayCode == "SEP" ? ["SA", "SEU", "SED", "SEI", "SEC"] : ["SUP", "SUS", "SD", "SI", "SC", "SEU", "SED", "SA"]);
        OpenTrace(s, TraceTarget, null, TraceKind.Cut);
    }

    /// <summary>« Modifier la surface… » : son emprise sur le plan (sommets, arêtes) et son type.</summary>
    [RelayCommand]
    private void OpenReshapeForSurface()
    {
        if (SelectedSurface?.Surface is not { } s) return;
        SetTraceTargets(SurfaceTypes.Contains(s.DisplayCode) ? SurfaceTypes : [s.DisplayCode, .. SurfaceTypes], s.DisplayCode);
        OpenTrace(s, s.DisplayCode, null, TraceKind.Reshape);
    }

    /// <summary>« Nouvelle surface » : niveau de la surface sélectionnée, sinon du filtre, sinon le premier.</summary>
    [RelayCommand]
    private void OpenCreateSurface()
    {
        if (Document is null) return;
        TraceBuildings = Document.Levels.Select(l => l.Building).Distinct().OrderBy(b => b, StringComparer.Ordinal).ToList();
        OnPropertyChanged(nameof(TraceBuildings));
        var building = SelectedSurface?.Surface.Building ?? BalanceBuilding ?? TraceBuildings.FirstOrDefault();
        if (building is null) return;
        _creating = true;
        TraceBuilding = building;
        TraceLevels = LevelsOf(building);
        OnPropertyChanged(nameof(TraceLevels));
        TraceLevel = SelectedSurface?.Surface.Level is { } l && TraceLevels.Contains(l) ? l
            : SelectedLevel is { } f && f != AllLevels && TraceLevels.Contains(f) ? f : TraceLevels.FirstOrDefault();
        SetTraceTargets(SurfaceTypes, "SUS");
        _creating = false;
        OpenCreate(null);
    }

    private bool _creating;   // pickers remplis par le code : ne pas rouvrir le volet à chaque champ

    private List<string> LevelsOf(string building) =>
        Document!.Levels.Where(l => l.Building == building).OrderBy(l => l.Rank ?? 0).Select(l => l.Level).ToList();

    partial void OnTraceBuildingChanged(string? value)
    {
        if (_creating || value is null || !IsTraceCreate) return;
        _creating = true;
        TraceLevels = LevelsOf(value);
        OnPropertyChanged(nameof(TraceLevels));
        if (TraceLevel is null || !TraceLevels.Contains(TraceLevel)) TraceLevel = TraceLevels.FirstOrDefault();
        _creating = false;
        OpenCreate(Trace?.Polygons);
    }

    partial void OnTraceLevelChanged(string? value)
    {
        if (_creating || value is null || !IsTraceCreate) return;
        OpenCreate(Trace?.Polygons);   // le contour déjà dessiné est gardé (mêmes coordonnées)
    }

    private void OpenCreate(IReadOnlyList<IReadOnlyList<Point>>? polygons)
    {
        if (TraceBuilding is not { } b || TraceLevel is not { } l) return;
        var source = new Surface { Id = "", Building = b, Level = l, Category = TraceTarget, Code = TraceTarget, Kind = "leaf" };
        OpenTrace(source, TraceTarget, null, TraceKind.Create, polygons);
    }

    private void SetTraceTargets(IReadOnlyList<string> targets, string? selected = null)
    {
        TraceTargets = targets;
        OnPropertyChanged(nameof(TraceTargets));
        TraceTarget = selected ?? targets[0];
    }

    private static Surface NewSurface(Correction c)
    {
        var niveau = c.Extra?.GetValueOrDefault("niveau");
        string? Field(string name) =>
            niveau is { ValueKind: JsonValueKind.Object } n && n.TryGetProperty(name, out var v) ? v.GetString() : null;
        return new Surface { Id = "", Building = Field("building"), Level = Field("level"), Category = c.To ?? "", Code = c.To, Kind = "leaf" };
    }

    private void OpenTrace(Surface source, string target, CorrectionItem? item, TraceKind kind,
                           IReadOnlyList<IReadOnlyList<Point>>? initial = null)
    {
        if (Document is null || source.Building is null || source.Level is null) return;
        if (kind != TraceKind.Create && source.Mesh is null)
        {
            _shell.Notify("Pas de géométrie pour ce niveau dans le cache VWR : ajustez l'aire avec Modifier.");
            return;
        }
        var level = Document.Surfaces.Where(s => s.Building == source.Building && s.Level == source.Level).ToList();
        var levels = Document.Levels.Where(l => l.Building == source.Building).ToList();
        var rank = levels.FirstOrDefault(l => l.Level == source.Level)?.Rank ?? 0;
        var belowLevel = levels.Where(l => (l.Rank ?? 0) < rank).OrderByDescending(l => l.Rank ?? 0).FirstOrDefault()?.Level;
        var below = belowLevel is null ? [] : Document.Surfaces.Where(s => s.Building == source.Building && s.Level == belowLevel).ToList();
        var lv = levels.FirstOrDefault(l => l.Level == source.Level);
        var r3 = lv?.R3?.Diff ?? 0;
        var applied = item?.State == CorrectionState.Applied ? item.Model.Area ?? 0 : 0;
        _tracedItem = item;
        Trace = new TraceSession(source, level, below, target, item?.Model, r3, applied, Document.Tolerance, kind, initial);
        IsAiReportOpen = false;
        TraceFitRequested?.Invoke();
    }

    partial void OnTraceTargetChanged(string value)
    {
        if (Trace is not null && IsTraceManual) Trace.Target = value;
        OnPropertyChanged(nameof(TraceTitle));
    }

    /// <summary>Titre du volet : « B03·N00 · SEP → SA » ; la cible d'une découpe manuelle suit le choix.</summary>
    public string TraceTitle => Trace is null ? ""
        : IsTraceCreate ? "Nouvelle surface"
        : IsTraceManual && Trace.IsCut ? $"{Trace.Source.Building}·{Trace.Source.Level} · {Trace.Source.DisplayCode} →"
        : IsTraceManual && Trace.IsReshape ? $"{Trace.Source.Building}·{Trace.Source.Level} · emprise et type"
        : Trace.Title;

    partial void OnTraceChanged(TraceSession? value) => OnPropertyChanged(nameof(TraceTitle));

    [RelayCommand]
    private void SaveTrace()
    {
        if (Trace is not { CanSave: true } t || _journal is null) return;
        if (_tracedItem is { } item)
        {
            var c = t.BuildCorrection(item.Id, item.Model.Subject);
            item.ReplaceModel(c);
            _journal.Decide(c);
            CloseTrace();
            OnCorrectionsChanged();
            RefreshSubjects();
            SelectedCorrection = item;
            FocusCorrection(item);
            _shell.Notify($"Tracé enregistré : {c.Area:#,##0.00} m². Il s'appliquera à la prochaine analyse.");
            return;
        }
        var source = t.Source;
        var (prefix, message) = t.Kind switch
        {
            TraceKind.Reshape => ("modif", "Surface modifiée"),
            TraceKind.Create => ("creation", "Surface créée"),
            _ => ("", "Découpe créée"),
        };
        var created = t.BuildCorrection(NewManualId(prefix, source.Building, source.Level), SubjectOf(t.IsCreate ? null : source.Id));
        if (t.IsCut)
            created.Explanation = $"{source.Building} {source.Level} : {created.Area:#,##0.00} m² de {source.DisplayCode} tracés → {TraceTarget}.";
        else created.Status = Correction.Accepted;   // geste direct de l'utilisateur : décidé d'emblée
        AddManualCorrection(created);
        _shell.Notify(t.IsCut
            ? $"Découpe créée ({created.Area:#,##0.00} m² → {TraceTarget}) : acceptez-la, puis Analyser."
            : $"{message} ({created.Area:#,##0.00} m²) : elle s'appliquera à la prochaine analyse (Analyser).");
    }

    /// <summary>« Supprimer » sur la fiche d'une surface : exclusion acceptée d'emblée, après confirmation.</summary>
    [RelayCommand]
    private async Task DeleteSelectedSurfaceAsync()
    {
        if (SelectedSurface?.Surface is not { } s || _journal is null) return;
        var area = s.Area is double a ? $" ({a:#,##0.00} m²)" : "";
        if (!await _shell.ConfirmAsync($"Supprimer la {s.DisplayCode} ?",
                $"{s.Building} {s.Level} · {s.Id}{area} sera retirée des sommes et des exports à la prochaine analyse. " +
                "La correction reste dans le journal : vous pourrez la rejeter pour revenir en arrière.", "Supprimer", "Annuler"))
            return;
        var c = new Correction
        {
            Id = NewManualId("suppression", s.Building, s.Level), Op = "exclure", Subject = SubjectOf(s.Id),
            Target = JsonSerializer.SerializeToElement(new { ids = new[] { s.Id } }), Status = Correction.Accepted, Origin = "manuel",
            M2 = s.Area, Explanation = $"{s.Building} {s.Level} : {s.DisplayCode} {s.Id}{area} supprimée à la main.",
        };
        AddManualCorrection(c);
        _shell.Notify($"{s.DisplayCode} supprimée : elle sortira des sommes à la prochaine analyse (Analyser).");
    }

    private string NewManualId(string prefix, string? building, string? level)
    {
        var n = 1;
        var stem = prefix == "" ? $"manuel-{building}-{level}" : $"manuel-{prefix}-{building}-{level}";
        string id;
        do id = $"{stem}-{n++}"; while (_journal!.Get(id) is not null);
        return id;
    }

    /// <summary>Sujet qui couvre déjà la surface, sinon « Corrections manuelles ».</summary>
    private string SubjectOf(string? surfaceId) =>
        surfaceId is null ? ManualSubject
        : Subjects.FirstOrDefault(s => s.SurfaceIds.Contains(surfaceId) && s.Id != ManualSubject && s.Id != "à revoir")?.Id ?? ManualSubject;

    private void AddManualCorrection(Correction c)
    {
        _journal!.Decide(c);
        CloseTrace();
        LoadSubjects(Document!);
        ShowSubjects = true;
        SelectedSubject = Subjects.FirstOrDefault(s => s.Id == c.Subject) ?? Subjects.FirstOrDefault(s => s.Id == ManualSubject);
        SelectedCorrection = SelectedSubject?.Corrections.FirstOrDefault(x => x.Id == c.Id);
    }

    /// <summary>Annuler, ✕ ou Échap : confirme l'abandon d'un tracé modifié.</summary>
    [RelayCommand]
    private async Task CancelTraceAsync()
    {
        if (Trace is null) return;
        if (Trace.IsDirty && !await _shell.ConfirmAsync("Abandonner le tracé ?",
                "Les modifications du tracé seront perdues.", "Abandonner", "Continuer le tracé"))
            return;
        CloseTrace();
    }

    private void CloseTrace()
    {
        Trace = null;
        _tracedItem = null;
    }

    [RelayCommand] private void TraceUndo() => Trace?.Undo();
    [RelayCommand] private void TraceRedo() => Trace?.Redo();
    [RelayCommand] private void TraceClear() => Trace?.Clear();
    [RelayCommand] private void TraceFit() => TraceFitRequested?.Invoke();
}
