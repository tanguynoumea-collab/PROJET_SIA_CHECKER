using System.Windows.Media;
using CommunityToolkit.Mvvm.ComponentModel;
using SiaCheck.Viewer.Models;
using SiaCheck.Viewer.Services;

namespace SiaCheck.Viewer.ViewModels;

/// <summary>Un calque = une catégorie SIA (ou un code ignoré/inconnu).</summary>
public sealed partial class LayerItem(string code, string group, Brush swatch, int count, double area,
                                      bool visible, bool hasGeometry) : ObservableObject
{
    public string Code { get; } = code;
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

    public string Tooltip =>
        $"{Building}·{Level}\nSP {Sp:N2} m²\n" +
        string.Join("\n", FloorParts.Select(c => $"{c} {Source.Value(c):N2} m²")) +
        (HasFloor ? $"\nRésidu R1 {R1Diff:N2} m²" : "") +
        (Sep > 0 ? $"\nSEP {Sep:N2} m² (SEU {Source.Value("SEU"):N2}, SED {Source.Value("SED"):N2})" : "");
}

/// <summary>Surface cliquée en 3D, avec les points d'attention qui la citent.</summary>
public sealed class SurfaceInfo(Surface surface, IReadOnlyList<IssueItem> issues)
{
    public Surface Surface { get; } = surface;
    public IReadOnlyList<IssueItem> Issues { get; } = issues;
    public string Title => $"{Surface.DisplayCode} · {Surface.Building}·{Surface.Level}";
    public string Kind => Surface.IsLevelTotal ? "Total de niveau" : "Surface élémentaire";
}

public sealed record ChoiceItem(string Label, string Value);
