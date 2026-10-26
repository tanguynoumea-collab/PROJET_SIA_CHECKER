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
    /// <summary>NC : non comptabilisée (gardée, hors sommes et exports : toiture non accessible…).</summary>
    public static readonly string[] SurfaceTypes = ["SUP", "SUT", "SUS", "SD", "SI", "SC", "SEU", "SED", "SEI", "SEC", "SA", "SP", "SEP", "NC"];

    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(IsTraceOpen), nameof(IsTraceManual), nameof(IsTraceCreate), nameof(ShowTraceTargets))]
    private TraceSession? _trace;
    public bool IsTraceOpen => Trace is not null;
    /// <summary>Découpe créée depuis une surface : la catégorie cible se choisit dans le volet.</summary>
    public bool IsTraceManual => Trace is not null && _tracedItem is null;
    public bool IsTraceCreate => Trace?.IsCreate == true;
    /// <summary>Liste des catégories dans l'en-tête : découpe depuis la 3D, emprise et création (nouvelles ou reprises).</summary>
    public bool ShowTraceTargets => IsTraceManual || Trace is { IsCut: false };

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
        if (kind != TraceKind.Cut)   // emprise ou création reprise : le type reste modifiable, et le niveau d'une création
        {
            SetTraceTargets(SurfaceTypes.Contains(target) ? SurfaceTypes : [target, .. SurfaceTypes], target);
            if (kind == TraceKind.Create) SetCreatePickers(source.Building!, source.Level);
        }
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

    /// <summary>
    /// « Modifier la surface… » : son emprise sur le plan (sommets, arêtes) et son type. Une surface déjà modifiée ou
    /// créée, en attente d'analyse, reprend sa correction : pas de seconde correction sur la même surface.
    /// </summary>
    [RelayCommand]
    private void OpenReshapeForSurface()
    {
        if (SelectedSurface?.Pending is { } pending)
        {
            ReopenCorrection(pending);
            return;
        }
        if (SelectedSurface?.Surface is not { } s) return;
        if (s.IslandOf is null && PendingFor(s.Id, "remodeler") is { } existing) { ReopenCorrection(existing); return; }
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
        SetCreatePickers(building, SelectedSurface?.Surface.Level is { } l ? l : SelectedLevel != AllLevels ? SelectedLevel : null);
        SetTraceTargets(SurfaceTypes, "SUS");
        _tracedItem = null;
        OpenCreate(null);
    }

    /// <summary>Bâtiment et niveau d'une création (listes de l'en-tête), sans rouvrir le volet champ par champ.</summary>
    private void SetCreatePickers(string building, string? level)
    {
        _creating = true;
        if (TraceBuildings.Count == 0 && Document is not null)
        {
            TraceBuildings = Document.Levels.Select(x => x.Building).Distinct().OrderBy(b => b, StringComparer.Ordinal).ToList();
            OnPropertyChanged(nameof(TraceBuildings));
        }
        TraceBuilding = building;
        TraceLevels = LevelsOf(building);
        OnPropertyChanged(nameof(TraceLevels));
        TraceLevel = level is not null && TraceLevels.Contains(level) ? level : TraceLevels.FirstOrDefault();
        _creating = false;
    }

    /// <summary>Correction acceptée, pas encore appliquée, de cette opération sur cette surface.</summary>
    private CorrectionItem? PendingFor(string surfaceId, string op) =>
        Subjects.SelectMany(s => s.Corrections).FirstOrDefault(c =>
            c.Model.Op == op && c.State == CorrectionState.Accepted && c.TargetIds.Contains(surfaceId));

    private void ReopenCorrection(CorrectionItem c)
    {
        var keep = SelectedCorrection;
        SelectedCorrection = c;
        OpenTraceForCorrection();
        if (!IsTraceOpen) SelectedCorrection = keep;
    }

    /// <summary>Fiche d'une surface de l'aperçu 3D : telle qu'elle sera après la prochaine analyse.</summary>
    private SurfaceInfo? PendingSurface(string previewId)
    {
        var cid = previewId[SiaCheck.Viewer.Scene.SceneController.PreviewPrefix.Length..];
        if (Subjects.SelectMany(s => s.Corrections).FirstOrDefault(c => c.Id == cid) is not { } c) return null;
        var target = c.TargetIds.Select(id => _surfaceById.GetValueOrDefault(id)).FirstOrDefault(s => s is not null);
        var place = c.CreatedOn ?? (target is { Building: { } b, Level: { } l } ? (b, l) : null);
        var code = c.Model.To ?? target?.DisplayCode ?? "";
        var surface = new Surface
        {
            Id = target is not null && c.Model.Op == "remodeler" ? target.Id : c.Id,
            Building = place?.Item1, Level = place?.Item2, Category = code, Code = code, Kind = "leaf",
            Area = c.Model.Area, RoomType = target?.RoomType, Lot = target?.Lot,
        };
        var linked = target is null ? [] : Issues.Where(i => i.SurfaceIds.Contains(target.Id)).OrderBy(i => i.SortKey).ToList();
        return new SurfaceInfo(surface, linked, c);
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
        OpenTrace(source, TraceTarget, _tracedItem, TraceKind.Create, polygons);   // une création reprise garde sa correction
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
        // Géométrie telle qu'elle sera : parts déjà découpées ou exclues en attente retirées (sauf celle qu'on retrace).
        var cuts = PendingCuts();
        if (kind != TraceKind.Create) source = Current(source, cuts, item?.Id);
        if (kind != TraceKind.Create && source.Mesh is null)
        {
            _shell.Notify("Pas de géométrie pour ce niveau dans le cache VWR : ajustez l'aire avec Modifier.");
            return;
        }
        var level = Document.DisplaySurfaces.Where(s => s.Building == source.Building && s.Level == source.Level)
            .Select(s => Current(s, cuts, item?.Id)).Concat(PendingParts(source.Building, source.Level, item?.Id)).ToList();
        var siblings = source.IslandOf is { } parent && Document.Islands.TryGetValue(parent, out var parts)
            ? parts.Where(p => p.Id != source.Id).Select(p => Current(p, cuts, item?.Id)).Where(p => p.Mesh is not null).ToList() : null;
        var levels = Document.Levels.Where(l => l.Building == source.Building).ToList();
        var rank = levels.FirstOrDefault(l => l.Level == source.Level)?.Rank ?? 0;
        var belowLevel = levels.Where(l => (l.Rank ?? 0) < rank).OrderByDescending(l => l.Rank ?? 0).FirstOrDefault()?.Level;
        var below = belowLevel is null ? [] : Document.Surfaces.Where(s => s.Building == source.Building && s.Level == belowLevel).ToList();
        var lv = levels.FirstOrDefault(l => l.Level == source.Level);
        var r3 = lv?.R3?.Diff ?? 0;
        var applied = item?.State == CorrectionState.Applied ? item.Model.Area ?? 0 : 0;
        _tracedItem = item;
        Trace = new TraceSession(source, level, below, target, item?.Model, r3, applied, Document.Tolerance, kind, initial, siblings);
        IsAiReportOpen = false;
        TraceFitRequested?.Invoke();
    }

    partial void OnTraceTargetChanged(string value)
    {
        if (Trace is not null && ShowTraceTargets) Trace.Target = value;
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
        if (t.IsSplitMode)   // SPLIT : deux surfaces, la seconde découpée de l'origine, chacune avec son type
        {
            var split = t.BuildSplitCorrections(NewManualId("scission", t.Source.Building, t.Source.Level), SubjectOf(t.TargetSurfaceId));
            foreach (var c in split) { c.Status = Correction.Accepted; _journal.Decide(c); }
            AddManualCorrection(split[0]);
            _shell.Notify($"Surface scindée en deux ({t.SplitAreaAText} et {t.SplitAreaBText}) : appliquée à la prochaine analyse (Analyser).");
            return;
        }
        if (_tracedItem is { } item)
        {
            var c = t.BuildCorrection(item.Id, item.Model.Subject);
            item.ReplaceModel(c);
            _journal.Decide(c);
            CloseTrace();
            OnCorrectionsChanged();
            RefreshSubjects();
            SelectedSurface = null;
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
        var created = t.BuildCorrection(NewManualId(prefix, source.Building, source.Level), SubjectOf(t.IsCreate ? null : t.TargetSurfaceId));
        if (t.IsCut)
            created.Explanation = $"{source.Building} {source.Level} : {created.Area:#,##0.00} m² de {source.DisplayCode} tracés → {TraceTarget}.";
        else created.Status = Correction.Accepted;   // geste direct de l'utilisateur : décidé d'emblée
        AddManualCorrection(created);
        _shell.Notify(t.IsCut
            ? $"Découpe créée ({created.Area:#,##0.00} m² → {TraceTarget}) : acceptez-la, puis Analyser."
            : $"{message} ({created.Area:#,##0.00} m²) : elle s'appliquera à la prochaine analyse (Analyser).");
    }

    /// <summary>
    /// « Supprimer » sur la fiche d'une surface : exclusion acceptée d'emblée, après confirmation. Sur une surface créée
    /// ou une part découpée en attente, c'est la correction qui est rejetée ; une emprise redessinée est rejetée et la
    /// surface d'origine exclue.
    /// </summary>
    [RelayCommand]
    private async Task DeleteSelectedSurfaceAsync()
    {
        if (SelectedSurface?.Pending is { } pending)
        {
            if (!await _shell.ConfirmAsync($"Supprimer la {SelectedSurface.Surface.DisplayCode} ?",
                    pending.Model.Op == "remodeler"
                        ? "L'emprise redessinée est abandonnée et la surface d'origine retirée des sommes à la prochaine analyse."
                        : "La correction qui la crée est rejetée : la surface ne sera pas ajoutée.", "Supprimer", "Annuler"))
                return;
            pending.Decision = CorrectionDecision.Rejected;
            var original = pending.Model.Op == "remodeler" ? pending.TargetIds.Select(id => _surfaceById.GetValueOrDefault(id)).FirstOrDefault() : null;
            SelectedSurface = null;
            RefreshSubjects();
            if (original is not null) await DeleteSurfaceAsync(original, confirm: false);
            return;
        }
        if (SelectedSurface?.Surface is { } s) await DeleteSurfaceAsync(s, confirm: true);
    }

    private async Task DeleteSurfaceAsync(Surface s, bool confirm)
    {
        if (_journal is null) return;
        var area = s.Area is double a ? $" ({a:#,##0.00} m²)" : "";
        if (confirm && !await _shell.ConfirmAsync($"Supprimer la {s.DisplayCode} ?",
                $"{s.Building} {s.Level} · {s.Id}{area} sera retirée des sommes et des exports à la prochaine analyse. " +
                "La correction reste dans le journal : vous pourrez la rejeter pour revenir en arrière.", "Supprimer", "Annuler"))
            return;
        var target = s.IslandOf ?? s.Id;
        var c = new Correction
        {
            Id = NewManualId("suppression", s.Building, s.Level), Op = "exclure", Subject = SubjectOf(target),
            Target = JsonSerializer.SerializeToElement(new { ids = new[] { target } }), Status = Correction.Accepted, Origin = "manuel",
            M2 = s.Area, Explanation = $"{s.Building} {s.Level} : {s.DisplayCode} {s.Id}{area} supprimée à la main.",
        };
        if (s.IslandOf is not null)   // un îlot seul : exclusion partielle de la surface d'origine, à son emprise
        {
            var (polygon, trace, _) = TraceSession.Footprint(s);
            c.Area = s.Area;
            c.Trace = trace;
            c.Extra = new() { ["polygone"] = polygon };
            c.Explanation = $"{s.Building} {s.Level} : îlot {s.Id}{area} de la {s.DisplayCode} supprimé à la main.";
        }
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
