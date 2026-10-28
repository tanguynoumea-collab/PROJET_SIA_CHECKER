using System.Globalization;
using System.Windows.Media;
using CommunityToolkit.Mvvm.ComponentModel;
using SiaCheck.Viewer.Models;
using SiaCheck.Viewer.Services;

namespace SiaCheck.Viewer.ViewModels;

/// <summary>Un calque = une catégorie SIA (ou un code ignoré/inconnu).</summary>
public sealed partial class LayerItem(string code, string group, Brush swatch, int count, double area,
                                      bool visible, bool hasGeometry, string title, string? definition) : ObservableObject
{
    public string Code { get; } = code;
    /// <summary>Infobulle : « SUP · Surface utile principale (SIA 416 §2.1.1.1) ».</summary>
    public string Title { get; } = title;
    public string? Definition { get; } = definition;
    public bool HasDefinition => !string.IsNullOrEmpty(Definition);
    public string Group { get; } = group;
    public Brush Swatch { get; } = swatch;
    public int Count { get; } = count;
    public double Area { get; } = area;
    public bool HasGeometry { get; } = hasGeometry;
    [ObservableProperty] private bool _isVisible = visible;
}

public sealed partial class BuildingChip(string name) : ObservableObject
{
    public string Name { get; } = name;
    [ObservableProperty] private bool _isSelected;
}

/// <summary>Point d'attention de l'analyse courante, ou point suivi qui a disparu (résolu).</summary>
public sealed partial class IssueItem : ObservableObject
{
    public IssueItem(Issue issue, ReviewEntry review)
    {
        Issue = issue;
        Key = issue.Key;
        Rule = issue.Rule;
        Verdict = issue.Verdict;
        Building = issue.Building;
        Level = issue.Level;
        Lot = issue.Lot;
        Category = issue.Category;
        Message = issue.Message;
        Title = issue.Title ?? issue.Rule;
        Hint = issue.Hint;
        DiffM2 = issue.DiffM2;
        _status = review.Status;
        _comment = review.Comment;
    }

    public IssueItem(string key, ReviewEntry review)
    {
        var s = review.LastSeen!;
        Key = key;
        Rule = s.Rule;
        Verdict = s.Verdict;
        Building = s.Building;
        Level = s.Level;
        Lot = s.Lot;
        Category = s.Category;
        Message = s.Message;
        Title = s.Title ?? s.Rule;
        DiffM2 = s.DiffM2;
        IsResolved = true;
        ResolvedSince = s.AnalysisDate;
        _status = review.Status;
        _comment = review.Comment;
    }

    public Issue? Issue { get; }
    public string Key { get; }
    public string Rule { get; }
    public string Verdict { get; }
    public string Building { get; }
    public string Level { get; }
    public string? Lot { get; }
    public string Category { get; }
    public string Message { get; }
    /// <summary>Titre court (« Plancher non entièrement classé »), première lecture dans la liste.</summary>
    public string Title { get; }
    /// <summary>Ce qu'il faut vérifier ; null pour un point résolu.</summary>
    public string? Hint { get; }
    public bool HasHint => !string.IsNullOrEmpty(Hint);
    public string Tooltip => HasHint ? $"{Message}\n\nÀ vérifier : {Hint}" : Message;
    public double? DiffM2 { get; }
    public bool IsResolved { get; }
    public bool IsOpen => !IsResolved;
    public string? ResolvedSince { get; }

    public double? Expected => Issue?.Expected;
    public double? Obtained => Issue?.Obtained;
    public double? DiffPct => Issue?.DiffPct;
    public IReadOnlyList<string> SurfaceIds => Issue?.SurfaceIds ?? [];
    /// <summary>Agrégat (bâtiment ou projet entier) : somme de points de niveau, moins actionnable.</summary>
    public bool IsAggregate => Building == "*" || Level == "*";

    /// <summary>Tri : points de niveau d'abord, puis agrégats ; écart décroissant dans chaque groupe.</summary>
    public double SortKey => (IsAggregate ? 1e12 : 0) - Math.Abs(DiffM2 ?? 0);

    /// <summary>« B03·N00 », « B03 · tous niveaux », « Projet », complété du lot USPI.</summary>
    public string Location
    {
        get
        {
            var where = Building == "*" ? "Projet" : Level == "*" ? $"{Building} · tous niveaux" : $"{Building}·{Level}";
            return Lot is null ? where : $"{where} · {Lot.Split('_').Last()}";
        }
    }

    [ObservableProperty] private ReviewStatus _status;
    [ObservableProperty] private string _comment;
    /// <summary>Point actuellement isolé dans la 3D (recliquer dessus quitte l'isolement).</summary>
    [ObservableProperty] private bool _isFocused;
    /// <summary>Point qui cite la surface cliquée dans la 3D.</summary>
    [ObservableProperty] private bool _isLinked;

    /// <summary>Verdict de la dernière revue IA du projet (null : pas de revue, ou point absent de la revue).</summary>
    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(HasAi), nameof(AiKind), nameof(AiTag), nameof(AiReason), nameof(HasSubjectLink))]
    private AiVerdict? _ai;

    /// <summary>Sujet du moteur ou de la revue qui contient ce point (onglet Sujets).</summary>
    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(AiTag), nameof(HasSubjectLink))]
    private string? _subjectId;

    public bool HasAi => Ai is not null;
    public AiVerdictKind AiKind => Ai?.Kind ?? AiVerdictKind.Unknown;
    /// <summary>« S1 · vrai sujet », « faux positif » ; sans revue IA, le sujet du moteur (« toitures »).</summary>
    public string AiTag => Ai is null ? SubjectId ?? "" : Ai.Subject is { } s ? $"{s} · {AiVerdict.Label(AiKind)}" : AiVerdict.Label(AiKind);
    /// <summary>L'étiquette mène à un sujet de l'onglet Sujets.</summary>
    public bool HasSubjectLink => (Ai?.Subject ?? SubjectId) is not null;
    public string AiReason => Ai?.Reason ?? "";
}

/// <summary>Une ligne du bilan par niveau (élément signature, plan §6).</summary>
public sealed class BalanceRow(LevelBalance level, double scale)
{
    /// <summary>SUT : catégorie Treegram comptée dans la SU avec SUP et SUS (règle personnalisée P1).</summary>
    public static readonly string[] FloorParts = ["SUP", "SUT", "SUS", "SD", "SI"];
    public static readonly string[] ExternalParts = ["SEU", "SED"];

    public LevelBalance Source { get; } = level;
    public string Building => Source.Building;
    public string Level => Source.Level;
    /// <summary>Plus grande SP ou SEP du bâtiment : toutes les barres partagent la même échelle.</summary>
    public double Scale { get; } = scale;
    public double Sp => Source.Value("SP");
    public double Sep => Source.Value("SEP");
    public double R1Diff => Source.R1?.Diff ?? 0;
    public string? R1Verdict => Source.R1?.Verdict;
    /// <summary>Glyphe R1 seulement s'il signale quelque chose : le résidu courant (INFO) n'encombre pas le bilan.</summary>
    public bool ShowR1Glyph => HasFloor && R1Verdict is not (null or "INFO");
    public string Alerts => string.Join(" ", Source.Alerts);

    // Avant / après (plan, Évolution 2.0) : la barre montre l'état corrigé, le reste est une trace.
    public LevelBefore? Before => Source.Before;
    public double SpBefore => Before?.Value("SP") ?? Sp;
    public double SepBefore => Before?.Value("SEP") ?? Sep;
    /// <summary>Résidu qui a changé avec les corrections : la SEP (R3) d'abord, sinon le plancher (R1).</summary>
    private (string Code, double Before, double After)? Change =>
        Before is null ? null
        : Math.Abs((Before.R3?.Diff ?? 0) - (Source.R3?.Diff ?? 0)) > 0.005 ? ("SEP", Before.R3?.Diff ?? 0, Source.R3?.Diff ?? 0)
        : Math.Abs((Before.R1?.Diff ?? 0) - (Source.R1?.Diff ?? 0)) > 0.005 ? ("SP", Before.R1?.Diff ?? 0, Source.R1?.Diff ?? 0)
        : null;
    public bool HasChange => Change is not null;
    public string ChangeBefore => Change is { } c ? Format(c.Before) : "";
    public string ChangeAfter => Change is { } c ? Format(c.After) : "";
    /// <summary>Verdict du nouveau résidu ; un contrôle disparu (SEP entièrement exclue) vaut OK.</summary>
    public string? ChangeVerdict => (Change?.Code == "SEP" ? Source.R3?.Verdict : Source.R1?.Verdict) ?? (HasChange ? "OK" : null);
    public string ChangeTooltip => Change is { } c
        ? $"{c.Code} non classée : {Format(c.Before)} m² avant corrections, {Format(c.After)} m² après." : "";
    private static string Format(double v) =>
        v.ToString("#,##0.00", new System.Globalization.NumberFormatInfo { NumberGroupSeparator = " ", NumberDecimalSeparator = "," });
    public bool HasFloor => Sp > 0;

    // Cages d'escalier (V3.1) : étages de logements seulement (ratios.stairs) ; une ligne de bâtiment somme ses étages
    public bool IsHousing => Source.Values.ContainsKey("LOGEMENTS");
    public double Stairs => Source.Value("CAGES");
    /// <summary>Étage de logements sans cage : sous-type à vérifier (escalier typé circulation…).</summary>
    public bool HasNoStair => IsHousing && Stairs <= 0;
    public string StairsText => !IsHousing ? "" : Stairs > 0 ? $"{Stairs:0} cage{(Stairs > 1 ? "s" : "")}" : "aucune cage";
    public string StairsRatioText => Stairs > 0
        ? $"{Format0(Source.Value("SUP_CAGES") / Stairs)} m² · {Source.Value("LOG_CAGES") / Stairs:0.0} log." : "";
    public string StairsTooltip
    {
        get
        {
            if (!IsHousing) return "";
            var lines = new List<string> { $"Cages d'escalier {Building}·{Level}" };
            lines.Add($"SUP {Format0(Source.Value("SUP_ETAGE"))} m², {Source.Value("LOGEMENTS"):0} logement(s)");
            lines.Add(Stairs > 0
                ? $"{Stairs:0} cage(s) : {Format0(Source.Value("SUP_CAGES") / Stairs)} m² de SUP et {Source.Value("LOG_CAGES") / Stairs:0.0} logement(s) par cage"
                : "Aucune cage d'escalier : vérifier le sous-type des escaliers du niveau (Modifier… sur la surface).");
            lines.Add("Cage : surface SD de sous-type Escalier.");
            return string.Join("\n", lines);
        }
    }
    private static string Format0(double v) =>
        v.ToString("#,##0", new System.Globalization.NumberFormatInfo { NumberGroupSeparator = " ", NumberDecimalSeparator = "," });

    // Enveloppe (Évolution 3.6) : façade brute et vitrages du niveau, verticaux, hors des sommes de la barre
    public double Facade => Source.Value("SFN");
    public double Glazing => Source.Value("SRV");
    public bool HasFacade => Facade > 0;
    /// <summary>Plus grande façade du bâtiment : échelle propre, la façade ne se compare pas à la SP.</summary>
    public double FacadeScale { get; init; } = 1;
    public string GlazingShareText => HasFacade && Glazing > 0 ? $"{100 * Glazing / Facade:0} %" : "";
    public string FacadeTooltip
    {
        get
        {
            if (!HasFacade) return "";
            var lines = new List<string> { $"Façade {Building}·{Level} : {Format(Facade)} m² brute" };
            if (Source.Values.TryGetValue("SFN_NETTE", out var net) && Source.Values.TryGetValue("SFN_RESERVATIONS", out var res))
                lines.Add($"nette {Format(net)} m² + réservations {Format(res)} m²");
            lines.Add(Glazing > 0
                ? $"Vitrages (SRV) {Format(Glazing)} m², {100 * Glazing / Facade:0.0} % de la façade ; pleine {Format(Facade - Glazing)} m²"
                : "Pas de vitrages (SRV) sur ce niveau");
            return string.Join("\n", lines);
        }
    }

    public string LevelTooltip => $"{Building}·{Level} — cliquer pour isoler le niveau dans la 3D";
}

/// <summary>Surface cliquée en 3D, avec les points d'attention qui la citent.</summary>
/// <summary>
/// Fiche de la surface cliquée en 3D. <paramref name="pending"/> : correction acceptée, pas encore appliquée, que la 3D
/// montre déjà (emprise redessinée, surface créée, part découpée) ; la fiche décrit alors la surface telle qu'elle sera,
/// et ses boutons agissent sur cette correction. <paramref name="note"/> : métadonnées modifiées en attente (« qualifier »),
/// déjà montrées par la fiche ; les boutons agissent sur la surface lue.
/// </summary>
public sealed class SurfaceInfo(Surface surface, IReadOnlyList<IssueItem> issues, CorrectionItem? pending = null, string? note = null)
{
    public Surface Surface { get; } = surface;
    public IReadOnlyList<IssueItem> Issues { get; } = issues;
    public CorrectionItem? Pending { get; } = pending;
    public bool HasPending => Pending is not null || note is not null;
    /// <summary>Découper vise une surface lue, avec son maillage : pas une surface encore en attente.</summary>
    public bool CanCut => Pending is null;
    public bool HasNoIssue => Issues.Count == 0;
    public string Title => $"{Surface.DisplayCode} · {Surface.Building}·{Surface.Level}";
    public string Kind => Surface.IsLevelTotal ? "Total de niveau" : "Surface élémentaire";
    public string PendingText => Pending?.Model.Op switch
    {
        "créer" => "Surface créée à la main.",
        "remodeler" => "Emprise redessinée à la main.",
        "découper" => $"Surface découpée de la {Pending.TargetCode} (scission ou découpe).",
        _ => note ?? "",
    };
}

public sealed record ChoiceItem(string Label, string Value);

/// <summary>Une ligne de l'onglet Ratios : valeur du projet et, si un bâtiment est choisi, celle du bâtiment.</summary>
public sealed class RatioRow(Ratio project, Ratio? building)
{
    private static readonly NumberFormatInfo Format = new() { NumberGroupSeparator = " ", NumberDecimalSeparator = "," };

    public Ratio Project { get; } = project;
    public Ratio? Building { get; } = building;
    /// <summary>Le ratio jugé : celui du bâtiment s'il existe, sinon celui du projet.</summary>
    public Ratio Shown => Building ?? Project;

    public string Id => Project.Id;
    public string Label => Project.Label;
    public bool IsArea => Project.Unit == "m2";
    /// <summary>Nombre moyen (logements par cage) : une décimale, numérateur et dénominateur comptés.</summary>
    public bool IsCount => Project.Unit == "nombre";
    public string ProjectText => Text(Project.Value);
    public string BuildingText => Building is null ? "" : Text(Building.Value);
    public string ReferenceText => Project.HasReference ? $"{Text(Project.RefMin)}–{Text(Project.RefMax)}"
        : Project.Status switch { "typologie" => "typologie ?", "sans repère" => "sans repère", _ => "indicatif" };
    public bool IsOutside => Shown.Status is "bas" or "haut";
    public string StatusText => StatusTextOf(Shown.Status);

    public string Tooltip
    {
        get
        {
            var lines = new List<string> { $"{Id} — {Label}" };
            foreach (var r in new[] { Project, Building })
                if (r is not null)
                    lines.Add($"{(r.Building == Ratio.AllBuildings ? "Projet" : r.Building)} : {Text(r.Value)}  "
                              + $"({(IsCount ? Count(r.NumM2, "logements") : Area(r.NumM2))} / "
                              + $"{(r.Unit is "m2" or "nombre" ? Count(r.DenM2, DenUnit) : Area(r.DenM2))}) · {StatusTextOf(r.Status)}");
            lines.Add(Project.HasReference
                ? $"Repère indicatif {ReferenceText}, non normatif : un écart est une question, pas une erreur."
                : Project.Status == "typologie" ? "Repère selon la typologie du projet : renseignez-la dans la fiche projet."
                : Project.Status == "sans repère" ? "Repère établi sur des projets de logement : sans objet pour cette typologie."
                : "Sans repère : valeur informative.");
            if (!string.IsNullOrWhiteSpace(Project.Note)) lines.Add(Project.Note!);
            return string.Join("\n", lines);
        }
    }

    private static string StatusTextOf(string s) => s switch
    {
        "bas" => "sous le repère", "haut" => "au-dessus du repère", "ok" => "dans le repère", "info" => "informatif",
        "typologie" => "typologie à définir", "sans repère" => "sans repère pour cette typologie", _ => "non calculé",
    };

    private string Text(double? v) => v is not double d ? "–" : IsArea ? d.ToString("#,##0.0", Format) + " m²"
        : IsCount ? d.ToString("0.0", Format) : d.ToString("0.000", Format);
    /// <summary>Ce que compte le dénominateur d'un ratio en m² ou en nombre : des cages d'escalier, sinon des lots.</summary>
    private string DenUnit => Project.Id.Contains("cage", StringComparison.OrdinalIgnoreCase) ? "cages" : "lots";
    private static string Area(double? v) => v is double d ? d.ToString("#,##0", Format) + " m²" : "–";
    private static string Count(double? v, string unit) => v is double d ? d.ToString("#,##0", Format) + " " + unit : "–";
}
