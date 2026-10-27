using System.Collections.ObjectModel;
using System.ComponentModel;
using System.IO;
using System.Windows.Data;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Clipper2Lib;
using SiaCheck.Viewer.Models;
using SiaCheck.Viewer.Scene;
using SiaCheck.Viewer.Services;

namespace SiaCheck.Viewer.ViewModels;

/// <summary>
/// Onglet Sujets (plan, Évolution 2.0) : sujets du moteur réorientés par la revue IA, décisions sur leurs
/// corrections (journal persistant), lien avec la 3D. Les décisions s'appliquent à la prochaine analyse :
/// « Analyser » reste la seule action primaire.
/// </summary>
public sealed partial class MainViewModel
{
    private CorrectionJournal? _journal;

    public ObservableCollection<SubjectItem> Subjects { get; } = [];
    private ICollectionView? _subjectsView;
    public ICollectionView SubjectsView => _subjectsView ??= CreateSubjectsView();

    private ICollectionView CreateSubjectsView()
    {
        var v = CollectionViewSource.GetDefaultView(Subjects);
        v.Filter = o => o is SubjectItem s && MatchesSubject(s);
        v.GroupDescriptions.Add(new PropertyGroupDescription(nameof(SubjectItem.Group)));   // intertitre « Tableau MDP »
        return v;
    }

    /// <summary>Onglet du panneau droit : Sujets (défaut quand il y en a) ou Points.</summary>
    [ObservableProperty] [NotifyPropertyChangedFor(nameof(ShowPoints))] private bool _showSubjects;
    public bool ShowPoints => !ShowSubjects;
    public bool HasSubjects => Subjects.Count > 0;

    [ObservableProperty] [NotifyPropertyChangedFor(nameof(HasSelectedSubject))] private SubjectItem? _selectedSubject;
    public bool HasSelectedSubject => SelectedSubject is not null;
    /// <summary>Points ouverts du sujet choisi, listés dans sa carte (clic : le point dans l'onglet Points).</summary>
    [ObservableProperty] [NotifyPropertyChangedFor(nameof(HasSelectedSubjectPoints))]
    private IReadOnlyList<IssueItem> _selectedSubjectPoints = [];
    public bool HasSelectedSubjectPoints => SelectedSubjectPoints.Count > 0;
    [ObservableProperty] [NotifyPropertyChangedFor(nameof(HasSelectedCorrection))] private CorrectionItem? _selectedCorrection;
    public bool HasSelectedCorrection => SelectedCorrection is not null;

    public IReadOnlyList<ChoiceItem> SubjectChoices { get; } =
    [
        new("Tous les sujets", ""), new("À décider", "todo"), new("Avec corrections acceptées", "accepted"),
        new("Avec corrections appliquées", "applied"),
    ];

    [ObservableProperty] private string _subjectFilter = "";
    partial void OnSubjectFilterChanged(string value) => RefreshSubjects();

    [RelayCommand]
    private void ResetSubjectFilter() => SubjectFilter = "";

    private bool MatchesSubject(SubjectItem s) => SubjectFilter switch
    {
        "todo" => s.ProposedCount > 0,
        "accepted" => s.Corrections.Any(c => c.State is CorrectionState.Accepted or CorrectionState.Applied),
        "applied" => s.Corrections.Any(c => c.State == CorrectionState.Applied),
        _ => true,
    };

    public string? SubjectsEmptyMessage => !HasSubjects || !SubjectsView.IsEmpty ? null
        : SubjectFilter == "applied" ? "Aucune correction appliquée pour l'instant."
        : SubjectFilter == "accepted" ? "Aucune correction acceptée pour l'instant."
        : "Aucun sujet pour ce filtre.";

    private void RefreshSubjects()
    {
        SubjectsView.Refresh();
        OnPropertyChanged(nameof(SubjectsEmptyMessage));
        OnPropertyChanged(nameof(CorrectionsSummary));
    }

    // ------------------------------------------------------------------ barre de commande

    /// <summary>Décisions pas encore appliquées par une analyse : compteur du bouton Analyser.</summary>
    public int PendingCorrections => _journal?.PendingCount ?? 0;
    public bool HasPendingCorrections => PendingCorrections > 0;
    public string AnalyseLabel => HasPendingCorrections ? $"Analyser · {PendingCorrections}" : "Analyser";
    public string AnalyseTooltip => HasPendingCorrections
        ? $"Réanalyser le projet et appliquer {PendingCorrections} décision{(PendingCorrections > 1 ? "s" : "")} sur les corrections (Ctrl+R)"
        : "Relancer l'analyse du projet (Ctrl+R)";

    public int AppliedCorrections => Document?.CorrectionsLog.Count(l => l.Application == CorrectionLogEntry.Applied) ?? 0;
    public bool HasAppliedCorrections => AppliedCorrections > 0;
    public string AppliedText => $"{AppliedCorrections} correction{(AppliedCorrections > 1 ? "s" : "")} appliquée{(AppliedCorrections > 1 ? "s" : "")}";

    public string CorrectionsSummary
    {
        get
        {
            var all = Subjects.SelectMany(s => s.Corrections).ToList();
            var accepted = all.Count(c => c.Decision == CorrectionDecision.Accepted);
            return all.Count == 0 ? "" : $"{all.Count} corrections · {accepted} acc.";
        }
    }

    // ------------------------------------------------------------------ revue IA écartée

    public IReadOnlyList<ReviewProblem> ReviewProblems => Document?.Review?.Problems ?? [];
    public bool HasReviewProblems => ReviewProblems.Count > 0;
    public string ReviewProblemsText => $"Revue IA : {ReviewProblems.Count} décision{(ReviewProblems.Count > 1 ? "s" : "")} écartée{(ReviewProblems.Count > 1 ? "s" : "")}";
    public string ReviewProblemsDetail => string.Join("\n", ReviewProblems.Select(p => $"{p.Subject} {p.Id} : {p.Reason}".Trim()));

    [RelayCommand]
    private void ShowReviewProblems() => _shell.Notify(ReviewProblemsDetail);

    // ------------------------------------------------------------------ chargement

    private void LoadSubjects(ViewerDocument doc)
    {
        _journal = CorrectionJournal.Open(_paths.CorrectionsFile(ProjectDir!), doc.Project);
        _journal.Changed += () => MarkModifiedIfDone(ProjectDir);
        var log = doc.CorrectionsLog.GroupBy(l => l.Id).ToDictionary(g => g.Key, g => g.Last());
        var issues = doc.Issues.ToDictionary(i => i.Key, i => i);
        Subjects.Clear();
        var unmatched = _journal.Orphans(doc.Subjects.SelectMany(s => s.Corrections).Select(c => c.Id));
        // Découpes tracées à la main depuis une surface : dans le sujet qui couvre cette surface s'il existe, sinon
        // dans « Corrections manuelles » ; les autres décisions sans proposition sont à revoir.
        var manual = unmatched.Where(c => c.Origin == "manuel" && c.Id.StartsWith("manuel-", StringComparison.Ordinal)).ToList();
        var orphans = unmatched.Except(manual).ToList();
        var subjectIds = doc.Subjects.Select(s => s.Id).ToHashSet();
        var open = Issues.Where(i => !i.IsResolved).Select(i => i.Key).ToHashSet();
        foreach (var s in doc.Subjects)
        {
            var items = s.Corrections.Select(c => MakeCorrection(_journal.Overlay(c), log))
                .Concat(manual.Where(c => c.Subject == s.Id).Select(c => MakeCorrection(c.Clone(), log))).ToList();
            // Sujet sans correction dont aucun point n'est encore ouvert (résolus par les corrections) : rien à montrer
            if (items.Count == 0 && !s.Points.Any(open.Contains)) continue;
            var ids = items.SelectMany(c => c.TargetIds)
                .Concat(s.Points.Where(issues.ContainsKey).SelectMany(k => issues[k].SurfaceIds))
                .Distinct().ToList();
            Subjects.Add(Track(new SubjectItem(s, items, ids)));
        }
        manual = manual.Where(c => c.Subject is null || !subjectIds.Contains(c.Subject)).ToList();
        if (manual.Count > 0)
        {
            var subject = new Subject
            {
                Id = ManualSubject, Title = "Corrections manuelles", Action = "corriger", Origin = "manuel",
                Explanation = "Découpes tracées dans le module de tracé, sans proposition du moteur ni de la revue IA.",
                M2 = manual.Sum(c => c.Area ?? 0),
            };
            var items = manual.Select(c => MakeCorrection(c.Clone(), log)).ToList();
            Subjects.Add(Track(new SubjectItem(subject, items, items.SelectMany(c => c.TargetIds).ToList())));
        }
        if (orphans.Count > 0)
        {
            var revisit = new Subject
            {
                Id = "à revoir", Title = "Décisions sans proposition", Action = "à vérifier",
                Explanation = "Ces corrections ne correspondent plus à aucune proposition : la surface visée a disparu ou a changé " +
                              "dans cette livraison. Vérifiez-les, puis rejetez-les ou modifiez-les.",
            };
            var items = orphans.Select(c => MakeCorrection(c.Clone(), log, orphan: true)).ToList();
            Subjects.Insert(0, Track(new SubjectItem(revisit, items, items.SelectMany(c => c.TargetIds).ToList())));
        }
        foreach (var i in Issues) i.SubjectId = null;
        var bySubject = doc.Subjects.SelectMany(s => s.Points.Select(k => (k, s.Id))).GroupBy(p => p.k).ToDictionary(g => g.Key, g => g.First().Id);
        foreach (var i in Issues) if (bySubject.TryGetValue(i.Key, out var sid)) i.SubjectId = sid;

        SelectedSubject = null;
        SelectedCorrection = null;
        SubjectFilter = "";
        ShowSubjects = Subjects.Count > 0;
        var sorted = Subjects.OrderBy(s => s.SortKey).ToList();
        Subjects.Clear();
        foreach (var s in sorted) Subjects.Add(s);
        foreach (var s in Subjects) SyncSettledPoints(s);   // sujets réglés avant cette analyse
        RefreshSubjects();
        OnCorrectionsChanged();
    }

    private CorrectionItem MakeCorrection(Correction c, Dictionary<string, CorrectionLogEntry> log, bool orphan = false)
    {
        var target = c.TargetIds.Select(id => _surfaceById.GetValueOrDefault(id)).FirstOrDefault(s => s is not null);
        return new CorrectionItem(c, log.GetValueOrDefault(c.Id), target, orphan);
    }

    private SubjectItem Track(SubjectItem s)
    {
        foreach (var c in s.Corrections)
            c.PropertyChanged += (_, e) =>
            {
                // "" : modèle remplacé (destination choisie, tracé, édition) ; enregistrer deux fois la même correction est sans effet.
                if (e.PropertyName != nameof(CorrectionItem.Decision) && !(e.PropertyName == "" && c.Model.Origin == "manuel"))
                    return;
                _journal?.Decide(c.Model);
                OnCorrectionsChanged();
                SyncSettledPoints(s);
            };
        return s;
    }

    // ------------------------------------------------------------------ points des sujets

    /// <summary>Commentaire posé sur les points d'un sujet réglé ; sert aussi à les reconnaître pour revenir en arrière.</summary>
    private static string SettledComment(SubjectItem s) => $"Sujet réglé : {s.Title}";

    private IEnumerable<IssueItem> PointsOf(SubjectItem s)
    {
        var keys = s.Subject.Points.ToHashSet();
        return Issues.Where(i => keys.Contains(i.Key) && !i.IsResolved);
    }

    /// <summary>
    /// Sujet réglé (toutes ses corrections décidées) : ses points « À traiter » passent « Vu », avec un commentaire qui le dit.
    /// Une décision qui repasse en « proposée » les remet « À traiter », s'ils n'ont pas été modifiés à la main depuis.
    /// </summary>
    private void SyncSettledPoints(SubjectItem s)
    {
        if (s.CanDecide)
        {
            var note = SettledComment(s);
            foreach (var i in PointsOf(s).ToList())
            {
                if (s.IsSettled && i.Status == ReviewStatus.ToReview)
                {
                    if (string.IsNullOrWhiteSpace(i.Comment)) i.Comment = note;
                    i.Status = ReviewStatus.Seen;   // enregistré par Track()
                }
                else if (!s.IsSettled && i.Status == ReviewStatus.Seen && i.Comment == note)
                {
                    i.Comment = "";
                    i.Status = ReviewStatus.ToReview;
                }
            }
            _commentSave.Stop();
        }
        UpdatePointCounts(s);
    }

    private void UpdatePointCounts(SubjectItem s)
    {
        var points = PointsOf(s).ToList();
        s.OpenPoints = points.Count(i => i.Status == ReviewStatus.ToReview);
        s.SeenPoints = points.Count(i => i.Status == ReviewStatus.Seen);
        s.FalsePoints = points.Count(i => i.Status == ReviewStatus.FalsePositive);
    }

    private void UpdateAllPointCounts()
    {
        foreach (var s in Subjects) UpdatePointCounts(s);
    }

    /// <summary>Sujet sans correction (à vérifier, aucune) : ses points « À traiter » passent « Vu ».</summary>
    [RelayCommand]
    private void MarkSubjectPointsSeen() => MarkSubjectPoints(ReviewStatus.Seen, "vus");

    /// <summary>Sujet sans correction : ses points « À traiter » passent « Faux positif ».</summary>
    [RelayCommand]
    private void MarkSubjectPointsFalse() => MarkSubjectPoints(ReviewStatus.FalsePositive, "en « Faux positif »");

    private void MarkSubjectPoints(ReviewStatus status, string label)
    {
        if (SelectedSubject is not { } s) return;
        var targets = PointsOf(s).Where(i => i.Status == ReviewStatus.ToReview).ToList();
        foreach (var i in targets)
        {
            if (string.IsNullOrWhiteSpace(i.Comment)) i.Comment = $"Sujet : {s.Title}";
            i.Status = status;
        }
        _commentSave.Stop();
        UpdatePointCounts(s);
        _shell.Notify($"{targets.Count} point{(targets.Count > 1 ? "s" : "")} du sujet passé{(targets.Count > 1 ? "s" : "")} {label}.");
    }

    /// <summary>
    /// 3D à jour sans attendre l'analyse : chaque correction acceptée, pas encore appliquée telle quelle, est montrée
    /// comme elle s'appliquera. Une surface déjà produite par une version antérieure de la correction (id « …#id »)
    /// est masquée, son nouveau tracé la remplace.
    /// </summary>
    private void UpdateScenePreview()
    {
        if (Scene is null || Document is null) return;
        var items = new List<ScenePreview>();
        var order = (_journal?.Decisions ?? []).Select((c, i) => (c.Id, i)).ToDictionary(x => x.Id, x => x.i);
        var accepted = Subjects.SelectMany(s => s.Corrections)
            .Where(c => c.State == CorrectionState.Accepted && !c.IsOrphan && !c.TargetIds.Any(Document.RedundantTotals.Contains))
            .OrderBy(c => order.GetValueOrDefault(c.Id, -1)).ToList();
        // Deux emprises redessinées pour la même surface : la plus récente l'emporte (le moteur les applique dans l'ordre).
        var lastReshape = accepted.Where(c => c.Model.Op == "remodeler" && c.TargetIds.Count == 1)
            .GroupBy(c => c.TargetIds[0]).ToDictionary(g => g.Key, g => g.Last().Id);
        // Surfaces amputées tout de suite des parts découpées ou exclues : la 3D les montre telles qu'elles seront.
        var cuts = PendingCuts();
        var replaced = new Dictionary<string, MeshData?>(StringComparer.Ordinal);
        foreach (var target in cuts.Keys)
            foreach (var shown in Document.Islands.TryGetValue(target, out var parts) ? parts
                     : _surfaceById.GetValueOrDefault(target) is { } t ? [t] : [])
                if (Current(shown, cuts) is var now && !ReferenceEquals(now, shown)) replaced[shown.Id] = now.Mesh;
        foreach (var c in accepted.Where(c => c.Model.Op != "remodeler" || c.TargetIds.Count != 1 || lastReshape[c.TargetIds[0]] == c.Id))
        {
            var m = c.Model;
            var targets = m.TargetIds;
            var former = Document.Surfaces.Where(s => s.Id.EndsWith("#" + m.Id, StringComparison.Ordinal)).Select(s => s.Id).ToList();
            var targetCode = targets.Select(id => _surfaceById.GetValueOrDefault(id)?.DisplayCode).FirstOrDefault(x => x is not null);
            var on = c.CreatedOn ?? (_surfaceById.GetValueOrDefault(targets.FirstOrDefault() ?? "") is { Building: { } b, Level: { } l } ? (b, l) : null);
            ScenePreview? p = m.Op switch
            {
                "exclure" when m.Area is null => new(m.Id, targets, [], null, null, null, null),
                "reclasser" when m.To is not null => new(m.Id, [], targets, m.To, null, null, null),
                "remodeler" when m.Trace is not null => new(m.Id, [.. targets, .. former], [], m.To ?? targetCode, m.Trace, on?.Item1, on?.Item2),
                "remodeler" when m.To is not null => new(m.Id, [], targets, m.To, null, null, null),
                "créer" when m.Trace is not null => new(m.Id, former, [], m.To, m.Trace, on?.Item1, on?.Item2),
                "découper" when m.Trace is not null => new(m.Id, former, [], m.To, m.Trace, on?.Item1, on?.Item2),
                _ => null,
            };
            if (p is not null) items.Add(p);
        }
        Scene.SetPreview(items, replaced);
    }

    /// <summary>
    /// Parts tracées que les corrections acceptées, pas encore appliquées, découpent ou excluent d'une surface :
    /// surface visée → (correction, tracé).
    /// </summary>
    private Dictionary<string, List<(string Id, PathsD Paths)>> PendingCuts()
    {
        var cuts = new Dictionary<string, List<(string, PathsD)>>(StringComparer.Ordinal);
        foreach (var c in Subjects.SelectMany(s => s.Corrections).Where(c => c.State == CorrectionState.Accepted && !c.IsOrphan
                     && c.TargetIds.Count == 1 && (c.Model.Op == "découper" || c.Model.Op == "exclure" && c.Model.Area is not null)))
            if (TraceSession.PolygonOf(c.Model) is { Count: > 0 } paths)
                (cuts.TryGetValue(c.TargetIds[0], out var list) ? list : cuts[c.TargetIds[0]] = []).Add((c.Id, paths));
        return cuts;
    }

    /// <summary>
    /// La surface (ou l'îlot) telle qu'elle sera après la prochaine analyse : moins ses parts découpées ou exclues en
    /// attente, sauf celle de la correction <paramref name="except"/> (en cours de retracé). Aire au prorata ; maillage
    /// nul si rien ne reste. La même surface si rien ne la touche.
    /// </summary>
    internal Surface Current(Surface s, Dictionary<string, List<(string Id, PathsD Paths)>>? cuts = null, string? except = null)
    {
        cuts ??= PendingCuts();
        if (s.Mesh is null || !cuts.TryGetValue(s.IslandOf ?? s.Id, out var list)) return s;
        var removed = new PathsD(list.Where(x => x.Id != except).SelectMany(x => x.Paths));
        if (removed.Count == 0) return s;
        var outline = TraceSession.Outline(s.Mesh);
        var rest = Clipper.Difference(outline, removed, FillRule.NonZero, 3);
        var (full, left) = (Math.Abs(Clipper.Area(outline)), Math.Abs(Clipper.Area(rest)));
        if (full - left < 0.01) return s;
        return new Surface
        {
            Id = s.Id, IslandOf = s.IslandOf, Building = s.Building, Level = s.Level, Category = s.Category, Code = s.Code,
            Kind = s.Kind, Status = s.Status, RoomType = s.RoomType, Lot = s.Lot,
            Mesh = left < 0.01 ? null : TraceSession.ToMesh(rest, TraceSession.TopZ(s.Mesh)),
            Area = s.Area is double a && full > 0 ? Math.Round(a * left / full, 2) : Math.Round(left, 2),
        };
    }

    /// <summary>Parts découpées ou créées en attente sur un niveau, comme surfaces du plan (sauf la correction retracée).</summary>
    private IEnumerable<Surface> PendingParts(string building, string level, string? except)
    {
        foreach (var c in Subjects.SelectMany(s => s.Corrections).Where(c => c.State == CorrectionState.Accepted && !c.IsOrphan
                     && c.Id != except && c.Model.Op is "découper" or "créer" && c.Model.Trace is not null && c.Model.To is not null))
        {
            var on = c.CreatedOn ?? (_surfaceById.GetValueOrDefault(c.TargetIds.FirstOrDefault() ?? "") is { Building: { } b, Level: { } l } ? (b, l) : null);
            if (on != (building, level)) continue;
            var t = c.Model.Trace!;
            yield return new Surface
            {
                Id = SiaCheck.Viewer.Scene.SceneController.PreviewPrefix + c.Id, Building = building, Level = level,
                Category = c.Model.To!, Code = c.Model.To, Kind = "leaf", Status = "checked", Area = c.Model.Area,
                Mesh = new MeshData
                {
                    Vertices = Enumerable.Range(0, t.Vertices.Length / 2).SelectMany(k => new[] { (float)t.Vertices[2 * k], (float)t.Vertices[2 * k + 1], (float)t.Z }).ToArray(),
                    Indices = t.Indices,
                },
            };
        }
    }

    private void OnCorrectionsChanged()
    {
        UpdateScenePreview();
        ScheduleBalancePreview();
        OnPropertyChanged(nameof(PendingCorrections));
        OnPropertyChanged(nameof(HasPendingCorrections));
        OnPropertyChanged(nameof(AnalyseLabel));
        OnPropertyChanged(nameof(AnalyseTooltip));
        OnPropertyChanged(nameof(CorrectionsSummary));
        OnPropertyChanged(nameof(HasSubjects));
    }

    /// <summary>Entrées du moteur : dernière revue IA du projet et journal des décisions, s'il y en a.</summary>
    internal EngineInputs CurrentEngineInputs(string projectDir)
    {
        var name = Document?.Project ?? Path.GetFileNameWithoutExtension(Directory.GetFiles(projectDir, "*.tgm").FirstOrDefault() ?? projectDir);
        var review = AiReviewFiles.FindLatest(name, AiReviewFiles.SearchDirs(_paths.AiReviewDir(projectDir), AiSearchBaseDir));
        var journal = _paths.CorrectionsFile(projectDir);
        return new EngineInputs(review?.VerdictsPath, File.Exists(journal) ? journal : null, _paths.SurfacesCacheFile(projectDir));
    }

    /// <summary>Analyse réussie avec le journal : ses décisions sont désormais appliquées.</summary>
    private void MarkCorrectionsAnalysed(EngineInputs inputs)
    {
        if (inputs.Journal is null || ProjectDir is null) return;
        CorrectionJournal.Open(inputs.Journal, null).MarkAnalysed();
    }

    // ------------------------------------------------------------------ onglets

    [RelayCommand]
    private void ShowSubjectsTab() { if (HasSubjects) ShowSubjects = true; }

    [RelayCommand]
    private void ShowPointsTab() => ShowSubjects = false;

    /// <summary>Étiquette de sujet d'un point (onglet Points) : ouvre ce sujet dans l'onglet Sujets.</summary>
    [RelayCommand]
    private void ShowSubjectOf(IssueItem? issue)
    {
        var id = issue?.Ai?.Subject ?? issue?.SubjectId;
        if (Subjects.FirstOrDefault(s => s.Id == id) is not { } s) return;
        SubjectFilter = "";
        ShowSubjects = true;
        SelectedSubject = s;
    }

    /// <summary>Point listé dans la carte d'un sujet : ouvert dans l'onglet Points, isolé en 3D.</summary>
    [RelayCommand]
    private void OpenSubjectPoint(IssueItem? issue)
    {
        if (issue is null) return;
        ShowSubjects = false;
        FocusIssue(issue);
    }

    [RelayCommand]
    private void ShowAppliedCorrections()
    {
        ShowSubjects = true;
        SubjectFilter = "applied";
    }

    // ------------------------------------------------------------------ décisions

    partial void OnSelectedSubjectChanged(SubjectItem? value)
    {
        SelectedSubjectPoints = value is null ? [] : PointsOf(value).OrderBy(i => i.SortKey).ToList();
        SelectedCorrection = null;
        if (value is not null) FocusSubject(value);
    }

    partial void OnSelectedCorrectionChanged(CorrectionItem? oldValue, CorrectionItem? newValue)
    {
        OnPropertyChanged(nameof(CanTraceSelected));
        if (oldValue?.IsEditing == true) oldValue.CancelEdit();
        if (newValue is not null) FocusCorrection(newValue);
    }

    [RelayCommand]
    private void AcceptAllCorrections() => DecideAll(CorrectionDecision.Accepted);

    [RelayCommand]
    private void RejectAllCorrections() => DecideAll(CorrectionDecision.Rejected);

    private void DecideAll(CorrectionDecision d)
    {
        if (SelectedSubject is not { } s) return;
        foreach (var c in s.Corrections.Where(c => !c.IsOrphan)) c.Decision = d;
        RefreshSubjects();
    }

    /// <summary>1 / 2 / 3 sur la correction sélectionnée : proposée / acceptée / rejetée.</summary>
    [RelayCommand]
    private void SetCorrectionDecision(string decision)
    {
        if (SelectedCorrection is not { } c) return;
        c.Decision = decision switch
        {
            "accepted" => CorrectionDecision.Accepted,
            "rejected" => CorrectionDecision.Rejected,
            _ => CorrectionDecision.Proposed,
        };
        RefreshSubjects();
    }

    [RelayCommand]
    private void EditCorrection() => SelectedCorrection?.BeginEdit();

    [RelayCommand]
    private void CommitCorrectionEdit()
    {
        if (SelectedCorrection is not { IsEditing: true } c) return;
        if (c.CommitEdit() is not { } edited) return;
        _journal?.Decide(edited);
        OnCorrectionsChanged();
        RefreshSubjects();
        FocusCorrection(c);
    }

    [RelayCommand]
    private void CancelCorrectionEdit() => SelectedCorrection?.CancelEdit();

    // ------------------------------------------------------------------ 3D

    /// <summary>
    /// Sujet avec corrections : ses seules cibles, et pour une correction tracée la seule part en cause (la zone déjà
    /// classée de la même surface, SED d'une SEP par exemple, reste en fantôme). Sans correction : les surfaces des points.
    /// </summary>
    private void FocusSubject(SubjectItem s)
    {
        if (Scene is null || s.SurfaceIds.Count == 0) return;
        var corrections = s.Corrections.Where(c => !c.IsOrphan && (c.TargetIds.Count > 0 || c.CreatedOn is not null)).ToList();
        var bounds = corrections.Count == 0 ? Scene.Focus(s.SurfaceIds)
            : Scene.Focus(corrections.Where(c => !c.HasTrace).SelectMany(c => c.TargetIds), Parts(corrections), _shell.AccentColor);
        SetFocused(null);
        _shell.Frame(bounds);
    }

    /// <summary>Parts tracées : posées sur leur surface ; une surface créée l'est sur la SP de son niveau (ou une autre surface).</summary>
    private List<(string, TraceMesh)> Parts(IEnumerable<CorrectionItem> corrections) =>
        corrections.Where(c => c.HasTrace).Select(c => (Id: c.TargetIds.Count == 1 ? c.TargetIds[0] : AnchorOf(c), c.Model.Trace!))
            .Where(p => p.Id is not null).Select(p => (p.Id!, p.Item2)).ToList();

    private string? AnchorOf(CorrectionItem c) =>
        c.CreatedOn is not { } on || Document is null ? null
        : Document.Surfaces.Where(s => s.Building == on.Building && s.Level == on.Level && s.Mesh is not null)
            .OrderBy(s => s.DisplayCode == "SP" ? 0 : 1).FirstOrDefault()?.Id;

    private void FocusCorrection(CorrectionItem c)
    {
        if (Scene is null) return;
        var parts = Parts([c]);
        var bounds = parts.Count > 0 ? Scene.Focus([], parts, _shell.AccentColor) : Scene.Focus(c.TargetIds);
        SetFocused(null);
        if (bounds is null) _shell.Notify("La surface visée n'a pas de géométrie dans le cache VWR.");
        _shell.Frame(bounds);
        if (_surfaceById.GetValueOrDefault(c.TargetIds.FirstOrDefault() ?? "")?.Building is { } bld) BalanceBuilding = bld;
    }
}
