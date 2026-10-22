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
    [NotifyPropertyChangedFor(nameof(HasAi), nameof(AiKind), nameof(AiTag), nameof(AiReason))]
    private AiVerdict? _ai;

    public bool HasAi => Ai is not null;
    public AiVerdictKind AiKind => Ai?.Kind ?? AiVerdictKind.Unknown;
    /// <summary>« S1 · vrai sujet », « faux positif ».</summary>
    public string AiTag => Ai is null ? "" : Ai.Subject is { } s ? $"{s} · {AiVerdict.Label(AiKind)}" : AiVerdict.Label(AiKind);
    public string AiReason => Ai?.Reason ?? "";
}

/// <summary>Une ligne du bilan par niveau (élément signature, plan §6).</summary>
public sealed class BalanceRow(LevelBalance level, double scale)
{
    public static readonly string[] FloorParts = ["SUP", "SUS", "SD", "SI"];
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
    public string Alerts => string.Join(" ", Source.Alerts);
    public bool HasFloor => Sp > 0;
    public string LevelTooltip => $"{Building}·{Level} — cliquer pour isoler le niveau dans la 3D";
}

/// <summary>Surface cliquée en 3D, avec les points d'attention qui la citent.</summary>
public sealed class SurfaceInfo(Surface surface, IReadOnlyList<IssueItem> issues)
{
    public Surface Surface { get; } = surface;
    public IReadOnlyList<IssueItem> Issues { get; } = issues;
    public bool HasNoIssue => Issues.Count == 0;
    public string Title => $"{Surface.DisplayCode} · {Surface.Building}·{Surface.Level}";
    public string Kind => Surface.IsLevelTotal ? "Total de niveau" : "Surface élémentaire";
}

public sealed record ChoiceItem(string Label, string Value);
