using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using SiaCheck.Viewer.Models;

namespace SiaCheck.Viewer.ViewModels;

/// <summary>
/// Module de tracé (plan, Évolution 2.1) : volet ouvert sur une correction (« Tracer… », touche T) ou sur une
/// surface cliquée en 3D (« Découper cette surface… »). Le tracé enregistré devient une correction « manuel »
/// du journal ; il s'applique, comme les autres décisions, à la prochaine analyse.
/// </summary>
public sealed partial class MainViewModel
{
    public const string ManualSubject = "manuel";
    private CorrectionItem? _tracedItem;

    [ObservableProperty] [NotifyPropertyChangedFor(nameof(IsTraceOpen), nameof(IsTraceManual))] private TraceSession? _trace;
    public bool IsTraceOpen => Trace is not null;
    /// <summary>Découpe créée depuis une surface : la catégorie cible se choisit dans le volet.</summary>
    public bool IsTraceManual => Trace is not null && _tracedItem is null;

    /// <summary>Catégories cibles d'une découpe manuelle : abords d'abord pour une SEP, puis la chaîne SIA.</summary>
    public IReadOnlyList<string> TraceTargets { get; private set; } = [];
    [ObservableProperty] private string _traceTarget = "SA";

    /// <summary>La fenêtre cadre le plan (F, ou à l'ouverture).</summary>
    public event Action? TraceFitRequested;

    public bool CanTraceSelected => SelectedCorrection is { } c && IsTraceable(c.Model);

    private static bool IsTraceable(Correction c) => c.Op == "découper" || c.Op == "exclure" && c.Area is not null;

    [RelayCommand]
    private void OpenTraceForCorrection()
    {
        if (SelectedCorrection is not { } c || !IsTraceable(c.Model)) return;
        var source = c.TargetIds.Select(id => _surfaceById.GetValueOrDefault(id)).FirstOrDefault(s => s is not null);
        if (source is null) { _shell.Notify("La surface visée n'existe plus dans l'analyse."); return; }
        OpenTrace(source, c.Model.Op == "exclure" ? "" : c.Model.To ?? "SA", c);
    }

    [RelayCommand]
    private void OpenTraceForSurface()
    {
        if (SelectedSurface?.Surface is not { } s) return;
        TraceTargets = s.DisplayCode == "SEP" ? ["SA", "SEU", "SED", "SEI", "SEC"]
            : ["SUP", "SUS", "SD", "SI", "SC", "SEU", "SED", "SA"];
        TraceTarget = TraceTargets[0];
        OnPropertyChanged(nameof(TraceTargets));
        OpenTrace(s, TraceTarget, null);
    }

    private void OpenTrace(Surface source, string target, CorrectionItem? item)
    {
        if (Document is null || source.Building is null || source.Level is null) return;
        if (source.Mesh is null)
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
        Trace = new TraceSession(source, level, below, target, item?.Model, r3, applied, Document.Tolerance);
        IsAiReportOpen = false;
        TraceFitRequested?.Invoke();
    }

    partial void OnTraceTargetChanged(string value) => OnPropertyChanged(nameof(TraceTitle));

    /// <summary>Titre du volet : « B03·N00 · SEP → SA » ; la cible d'une découpe manuelle suit le choix.</summary>
    public string TraceTitle => Trace is null ? ""
        : IsTraceManual ? $"{Trace.Source.Building}·{Trace.Source.Level} · {Trace.Source.DisplayCode} →" : Trace.Title;

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
        var subject = Subjects.FirstOrDefault(s => s.SurfaceIds.Contains(source.Id) && s.Id != ManualSubject && s.Id != "à revoir")?.Id ?? ManualSubject;
        var n = 1;
        string id;
        do id = $"manuel-{source.Building}-{source.Level}-{n++}"; while (_journal.Get(id) is not null);
        var created = t.BuildCorrection(id, subject);
        created.To = TraceTarget;
        created.Explanation = $"{source.Building} {source.Level} : {created.Area:#,##0.00} m² de {source.DisplayCode} tracés → {TraceTarget}.";
        _journal.Decide(created);
        CloseTrace();
        LoadSubjects(Document!);
        ShowSubjects = true;
        SelectedSubject = Subjects.FirstOrDefault(s => s.Id == subject) ?? Subjects.FirstOrDefault(s => s.Id == ManualSubject);
        SelectedCorrection = SelectedSubject?.Corrections.FirstOrDefault(c => c.Id == id);
        _shell.Notify($"Découpe créée ({created.Area:#,##0.00} m² → {TraceTarget}) : acceptez-la, puis Analyser.");
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
