using System.Globalization;
using CommunityToolkit.Mvvm.ComponentModel;
using SiaCheck.Viewer.Models;

namespace SiaCheck.Viewer.ViewModels;

/// <summary>État affiché d'une correction : décision de l'utilisateur, puis résultat de la dernière analyse.</summary>
public enum CorrectionState { Proposed, Accepted, Rejected, Applied, Failed }

/// <summary>Décision de l'utilisateur (raccourcis 1 / 2 / 3, comme les statuts de points).</summary>
public enum CorrectionDecision { Proposed, Accepted, Rejected }

/// <summary>Une correction proposée, avec la décision du journal et son application par le moteur.</summary>
public sealed partial class CorrectionItem : ObservableObject
{
    private static readonly NumberFormatInfo Format = new() { NumberGroupSeparator = " ", NumberDecimalSeparator = "," };
    private readonly CorrectionLogEntry? _log;
    private readonly Surface? _target;

    public CorrectionItem(Correction model, CorrectionLogEntry? log, Surface? target, bool orphan = false)
    {
        Model = model;
        _log = log;
        _target = target;
        IsOrphan = orphan;
        _decision = model.Status switch
        {
            Correction.Accepted => CorrectionDecision.Accepted,
            Correction.Rejected => CorrectionDecision.Rejected,
            _ => CorrectionDecision.Proposed,
        };
    }

    public Correction Model { get; private set; }
    public string Id => Model.Id;
    /// <summary>Décision dont la cible a disparu d'une livraison à l'autre : « à revoir ».</summary>
    public bool IsOrphan { get; }

    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(State), nameof(IsRejected), nameof(StateLabel))]
    private CorrectionDecision _decision;

    partial void OnDecisionChanged(CorrectionDecision value) =>
        Model.Status = value switch
        {
            CorrectionDecision.Accepted => Correction.Accepted,
            CorrectionDecision.Rejected => Correction.Rejected,
            _ => Correction.Proposed,
        };

    /// <summary>Appliquée par la dernière analyse, telle quelle (pas modifiée depuis).</summary>
    public bool WasApplied => _log?.Application == CorrectionLogEntry.Applied && _log.Status == Correction.Accepted;

    public CorrectionState State => IsOrphan ? CorrectionState.Failed
        : Decision == CorrectionDecision.Rejected ? CorrectionState.Rejected
        : Decision == CorrectionDecision.Proposed ? CorrectionState.Proposed
        : _log is { Status: Correction.Accepted } l && l.Application != CorrectionLogEntry.Applied ? CorrectionState.Failed
        : WasApplied ? CorrectionState.Applied
        : CorrectionState.Accepted;

    /// <summary>Proposition pour le tableau MDP (affectation, typologie, forme) : on la prend ou l'on répond « Inconnu ».</summary>
    public bool IsProposal => Model.Op is "affecter" or "renseigner";
    /// <summary>Libellé du refus : « Inconnu » pour une proposition MDP (écrit tel quel dans le MDP), sinon « Rejetée ».</summary>
    public string RejectLabel => IsProposal ? "Inconnu" : "Rejetée";

    public string StateLabel => State switch
    {
        CorrectionState.Accepted => "acceptée · s'appliquera à la prochaine analyse",
        CorrectionState.Applied => IsProposal ? "appliquée · écrite dans le MDP" : "appliquée",
        CorrectionState.Rejected => IsProposal ? "« Inconnu » dans le MDP" : "rejetée",
        CorrectionState.Failed => IsOrphan ? "à revoir : la surface visée n'existe plus" : $"inapplicable : {_log?.Reason}",
        _ => "proposée",
    };

    public bool IsRejected => Decision == CorrectionDecision.Rejected;

    /// <summary>« A01·N07 », « E09·N00 2/3 » pour un morceau de la part d'un niveau, ou les critères d'une sélection (« Gaine », « 2 ch. »).</summary>
    public string Location => (_target is { Building: { } b, Level: { } l } ? $"{b}·{l}"
                               : Level() is { } nl ? nl
                               : Model.TargetIds.Count > 0 ? Model.TargetIds[0] : Selection())
        + (Piece is { } p ? $" {p}" : "");

    /// <summary>Niveau d'une surface créée (`niveau`) : « B03·N01 ».</summary>
    private string? Level() =>
        Model.Extra?.TryGetValue("niveau", out var n) == true && n.ValueKind == System.Text.Json.JsonValueKind.Object
        && n.TryGetProperty("building", out var b) && n.TryGetProperty("level", out var l) ? $"{b}·{l}" : null;

    /// <summary>« 2/3 » : morceau d'un seul tenant de la part tracée d'un niveau (sujets.py), décidé à part.</summary>
    public string? Piece =>
        Model.Extra?.TryGetValue("morceau", out var m) == true && m.ValueKind == System.Text.Json.JsonValueKind.String ? m.GetString() : null;

    private string Selection()
    {
        if (Model.Target.ValueKind != System.Text.Json.JsonValueKind.Object || !Model.Target.TryGetProperty("selection", out var sel))
            return "sélection";
        var parts = new List<string>();
        if (sel.TryGetProperty("room_type", out var rt)) parts.Add(rt.ToString());
        if (sel.TryGetProperty("bedrooms", out var bd)) parts.Add(bd.GetInt32() == 0 ? "studio" : $"{bd} ch.");
        if (sel.TryGetProperty("building", out var bl)) parts.Add(bl.ToString());
        if (sel.TryGetProperty("level", out var lv)) parts.Add(lv.ToString());
        if (sel.TryGetProperty("avec_lot", out var al) && al.ValueKind == System.Text.Json.JsonValueKind.True) parts.Add("logt");
        return parts.Count > 0 ? string.Join(" ", parts) : "sélection";
    }

    /// <summary>Champs d'une proposition « renseigner » (Nom typologie, pièces, forme…).</summary>
    private string Fields() =>
        Model.Extra?.TryGetValue("champs", out var ch) == true && ch.ValueKind == System.Text.Json.JsonValueKind.Object
            ? string.Join(" · ", ch.EnumerateObject().Select(p => p.Value.ToString())) : "";
    public string TargetCode => _target?.DisplayCode ?? "";

    /// <summary>Ce que fait la correction, en mots : « SEP entière », « part retirée », « SEP → SA ».</summary>
    public string Summary => Model.Op switch
    {
        "exclure" when Model.Area is null => $"{TargetCode} entière".Trim(),
        "exclure" => TargetCode == "" ? "une part" : $"part de {TargetCode}",
        "découper" when IsToAbords => $"{TargetCode} →".Trim(),   // suivi de la pastille SA
        "découper" => $"{TargetCode} → {Model.To}".Trim(),
        "reclasser" => $"{TargetCode} → {Model.To}".Trim(),
        "ajuster" => "aire fixée",
        "remodeler" => Model.To is { } to && to != TargetCode ? $"{TargetCode} emprise → {to}".Trim() : $"{TargetCode} emprise".Trim(),
        "créer" => $"nouvelle {Model.To}",
        "affecter" => $"→ {Model.Assignment}",
        "renseigner" => Fields(),
        _ => Model.Op,
    };

    public bool IsToAbords => Model.To == "SA";
    public double? Area => Model.Area ?? Model.M2;
    public string AreaText => Area is double a ? a.ToString("#,##0.00", Format) + " m²" : "";
    public string OriginLabel => Model.Origin switch { "ia" => "IA", "manuel" => "manuel", _ => "règle" };
    public string Explanation => Model.Explanation;
    public bool HasTrace => Model.Trace is { Indices.Length: > 0 };
    public bool HasNoTrace => Model.Op == "découper" && !HasTrace;
    public IReadOnlyList<string> TargetIds => Model.TargetIds;
    /// <summary>Découpe ou exclusion partielle : se trace dans le plan (« Tracer… »).</summary>
    public bool CanTrace => Model.Op is "découper" or "remodeler" or "créer" || Model.Op == "exclure" && Model.Area is not null;

    /// <summary>Correction retracée (module de tracé) : même identifiant, même décision.</summary>
    public void ReplaceModel(Correction c)
    {
        c.Status = Model.Status;
        Model = c;
        OnPropertyChanged(string.Empty);
    }

    // ------------------------------------------------------------------ destination de la part visée

    /// <summary>Choix « Exclure » de la liste des destinations : la part sort des sommes SIA (toiture non accessible…).</summary>
    public const string ExcludeChoice = "exclure";

    private static readonly IReadOnlyList<ChoiceItem> SepDestinations =
    [
        new("SEP · même type (scission)", "SEP"), new("SEU · balcons, terrasses", "SEU"), new("SED · coursives", "SED"), new("SEI · installations", "SEI"),
        new("SEC · garde-corps, murets", "SEC"), new("SA · abords (contact terrain)", "SA"),
        new("NC · non comptabilisée (toiture non accessible)", "NC"), new("Exclure · retirer du modèle", ExcludeChoice),
    ];
    private static readonly IReadOnlyList<ChoiceItem> SpDestinations =
    [
        new("SP · même type (scission)", "SP"), new("SUP · utile principale", "SUP"), new("SUT · utile hors logement (Treegram)", "SUT"),
        new("SUS · utile secondaire", "SUS"), new("SD · dégagement", "SD"),
        new("SI · installations", "SI"), new("SC · construction (murs)", "SC"),
        new("NC · non comptabilisée", "NC"), new("Exclure · retirer du modèle", ExcludeChoice),
    ];

    /// <summary>
    /// Catégories possibles pour la part visée d'une SEP ou d'une SP (découpe, exclusion partielle) : la correction
    /// d'un résidu « non classé » se règle en choisissant ce qu'il est. Vide pour les autres corrections.
    /// </summary>
    public IReadOnlyList<ChoiceItem> Destinations =>
        IsOrphan || Model.Area is null || Model.Op is not ("découper" or "exclure") ? []
        : TargetCode switch
        {
            "SEP" => SepDestinations,
            "SP" => SpDestinations,
            _ => Model.Op == "découper" ? AnyDestinations : [],   // part scindée d'une autre surface : tous les types
        };

    private static readonly IReadOnlyList<ChoiceItem> AnyDestinations =
        [.. MainViewModel.SurfaceTypes.Select(c => new ChoiceItem(c, c)), new("Exclure · retirer du modèle", ExcludeChoice)];
    public bool HasDestinations => Destinations.Count > 0;

    /// <summary>Destination choisie : change l'opération (découper ↔ exclure) ; la correction devient « manuel ».</summary>
    public string? Destination
    {
        get => Model.Op == "exclure" ? ExcludeChoice : Model.To;
        set
        {
            if (value is null || value == Destination) return;
            var c = Model.Clone();
            c.Op = value == ExcludeChoice ? "exclure" : "découper";
            c.To = value == ExcludeChoice ? null : value;
            c.Origin = "manuel";
            Model = c;
            OnPropertyChanged(string.Empty);
        }
    }

    /// <summary>L'aire est modifiable pour les opérations qui en portent une ; celle d'un contour dessiné vient du tracé.</summary>
    public bool CanEditArea => Model.Op is "découper" or "ajuster" or "exclure";
    /// <summary>Surface créée : son niveau (`niveau`), pour la 3D.</summary>
    public (string Building, string Level)? CreatedOn =>
        Model.Op == "créer" && Model.Extra?.TryGetValue("niveau", out var n) == true && n.ValueKind == System.Text.Json.JsonValueKind.Object
        && n.TryGetProperty("building", out var b) && n.TryGetProperty("level", out var l)
            ? (b.GetString() ?? "", l.GetString() ?? "") : null;

    public string Tooltip => string.IsNullOrWhiteSpace(Explanation) ? StateLabel : $"{Explanation}\n\n{StateLabel}";

    // ------------------------------------------------------------------ édition en place

    [ObservableProperty] private bool _isEditing;
    [ObservableProperty] private string _editArea = "";
    [ObservableProperty] private string _editExplanation = "";
    [ObservableProperty] [NotifyPropertyChangedFor(nameof(HasEditError))] private string? _editError;
    public bool HasEditError => !string.IsNullOrEmpty(EditError);

    public void BeginEdit()
    {
        EditArea = Area?.ToString("0.##", Format) ?? "";
        EditExplanation = Explanation;
        EditError = null;
        IsEditing = true;
    }

    /// <summary>
    /// Valide l'édition ; renvoie la correction modifiée (origine « manuel »), ou null si la saisie est refusée
    /// (le message reste sous le champ, la saisie est gardée).
    /// </summary>
    public Correction? CommitEdit()
    {
        var c = Model.Clone();
        if (CanEditArea && !string.IsNullOrWhiteSpace(EditArea))
        {
            var text = EditArea.Replace(" ", "").Replace(" ", "").Replace(",", ".");
            if (!double.TryParse(text, NumberStyles.Float, CultureInfo.InvariantCulture, out var a) || a < 0)
            {
                EditError = "Aire attendue en m², positive (ex. 1 812,65).";
                return null;
            }
            var max = _target?.Area;
            if (Model.Op is "découper" or "exclure" && max is double m && a > m + 0.005)
            {
                EditError = $"L'aire dépasse celle de la surface visée ({m.ToString("#,##0.00", Format)} m²).";
                return null;
            }
            if (Model.Area is not double old || Math.Abs(old - a) > 0.005)
            {
                c.Area = Math.Round(a, 2);
                c.M2 = c.Area;
                if (c.Trace is not null) { c.Trace = null; c.NeedsRetrace = true; }
            }
        }
        c.Explanation = EditExplanation.Trim();
        c.Origin = "manuel";
        IsEditing = false;
        EditError = null;
        Model = c;
        OnPropertyChanged(string.Empty);
        return c;
    }

    public void CancelEdit()
    {
        IsEditing = false;
        EditError = null;
    }
}

/// <summary>Un sujet de l'onglet Sujets : titre, action, frise d'état de ses corrections.</summary>
public sealed partial class SubjectItem : ObservableObject
{
    private static readonly NumberFormatInfo Format = new() { NumberGroupSeparator = " ", NumberDecimalSeparator = "," };
    /// <summary>Au-delà, la frise d'un glyphe par correction devient une barre segmentée (plan, Passe B).</summary>
    public const int MaxGlyphs = 40;

    public SubjectItem(Subject subject, IReadOnlyList<CorrectionItem> corrections, IReadOnlyList<string> surfaceIds)
    {
        Subject = subject;
        Corrections = corrections;
        SurfaceIds = surfaceIds;
        foreach (var c in corrections)
            c.PropertyChanged += (_, e) => { if (e.PropertyName is nameof(CorrectionItem.Decision) or "") Refresh(); };
    }

    public Subject Subject { get; }
    public IReadOnlyList<CorrectionItem> Corrections { get; }
    public IReadOnlyList<string> SurfaceIds { get; }

    public string Id => Subject.Id;
    /// <summary>Repère court en tête de ligne (« S2 ») ; un sujet du moteur (« toitures ») se lit par son titre.</summary>
    public string ShortId => Id.Length <= 4 ? Id : "";
    public bool HasShortId => ShortId.Length > 0;
    public string Title => Subject.Title;
    public string Explanation => Subject.Explanation;
    public bool HasExplanation => !string.IsNullOrWhiteSpace(Explanation);
    public bool IsAi => Subject.Origin == "ia";
    public string OriginLabel => IsAi ? "IA" : Subject.Origin == "manuel" ? "manuel" : "règle";
    /// <summary>« IA · vrai sujet », ou l'origine seule.</summary>
    public string OriginTag => IsAi && !string.IsNullOrEmpty(Subject.Certainty) ? $"IA · {Subject.Certainty}" : OriginLabel;
    public string Action => Subject.Action;
    /// <summary>Trait de l'étiquette d'action : corriger = trait erreur, à vérifier = trait alerte, aucune = secondaire.</summary>
    public SiaCheck.Viewer.Services.AiVerdictKind ActionKind => Action switch
    {
        "corriger" => SiaCheck.Viewer.Services.AiVerdictKind.TrueIssue,
        "à vérifier" => SiaCheck.Viewer.Services.AiVerdictKind.ToConfirm,
        _ => SiaCheck.Viewer.Services.AiVerdictKind.Unknown,
    };
    public bool HasCorrections => Corrections.Count > 0;
    public bool CanDecide => Corrections.Any(c => !c.IsOrphan);
    public bool ShowGlyphs => HasCorrections && Corrections.Count <= MaxGlyphs;
    public bool ShowBar => Corrections.Count > MaxGlyphs;
    public int PointCount => Subject.Points.Count;
    public double M2 => Corrections.Where(c => !c.IsRejected).Sum(c => c.Area ?? 0);
    public string M2Text => HasCorrections && Action != "proposer" ? M2.ToString("#,##0", Format) + " m²" : "";
    public int DecidedCount => Corrections.Count(c => c.Decision != CorrectionDecision.Proposed);
    public int AcceptedCount => Corrections.Count(c => c.Decision == CorrectionDecision.Accepted);
    public int RejectedCount => Corrections.Count(c => c.Decision == CorrectionDecision.Rejected);
    public int ProposedCount => Corrections.Count(c => c.Decision == CorrectionDecision.Proposed);
    public string Counts => HasCorrections
        ? $"{PointCount} point{(PointCount > 1 ? "s" : "")} · {Corrections.Count} correction{(Corrections.Count > 1 ? "s" : "")}"
        : $"{PointCount} point{(PointCount > 1 ? "s" : "")}";
    public string Progress => $"{DecidedCount} / {Corrections.Count}";
    /// <summary>Toutes les corrections décidées (acceptées, appliquées ou rejetées) : le sujet est réglé.</summary>
    public bool IsSettled => CanDecide && Corrections.Where(c => !c.IsOrphan).All(c => c.Decision != CorrectionDecision.Proposed);

    /// <summary>Points du sujet encore « À traiter » (tenu à jour par le ViewModel).</summary>
    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(HasOpenPoints), nameof(SeenAllLabel), nameof(FalseAllLabel), nameof(PointsState))]
    private int _openPoints;
    [ObservableProperty] [NotifyPropertyChangedFor(nameof(PointsState))] private int _seenPoints;
    [ObservableProperty] [NotifyPropertyChangedFor(nameof(PointsState))] private int _falsePoints;
    public bool HasOpenPoints => OpenPoints > 0;
    public string SeenAllLabel => $"Vu pour les {OpenPoints}";
    public string FalseAllLabel => $"Faux positif pour les {OpenPoints}";
    /// <summary>« 12 vus · 3 faux positifs · 2 à traiter ».</summary>
    public string PointsState => string.Join(" · ", new[]
    {
        SeenPoints > 0 ? $"{SeenPoints} vu{(SeenPoints > 1 ? "s" : "")}" : null,
        FalsePoints > 0 ? $"{FalsePoints} faux positif{(FalsePoints > 1 ? "s" : "")}" : null,
        OpenPoints > 0 ? $"{OpenPoints} à traiter" : null,
    }.Where(t => t is not null));

    public string AcceptAllLabel => $"Accepter les {Corrections.Count(c => !c.IsOrphan)}";
    public string RejectAllLabel => Corrections.All(c => c.IsProposal)
        ? $"« Inconnu » pour les {Corrections.Count}" : $"Rejeter les {Corrections.Count(c => !c.IsOrphan)}";

    /// <summary>Tri : « corriger » (surface en jeu décroissante), « proposer » (MDP), « à vérifier », « aucune ».</summary>
    public (int, double, string) SortKey => (Action switch { "corriger" => 0, "proposer" => 1, "à vérifier" => 2, _ => 3 }, -Subject.M2, Id);

    private void Refresh()
    {
        OnPropertyChanged(nameof(M2));
        OnPropertyChanged(nameof(M2Text));
        OnPropertyChanged(nameof(DecidedCount));
        OnPropertyChanged(nameof(AcceptedCount));
        OnPropertyChanged(nameof(RejectedCount));
        OnPropertyChanged(nameof(ProposedCount));
        OnPropertyChanged(nameof(Progress));
    }
}
