using SiaCheck.Viewer.Models;

namespace SiaCheck.Viewer.Services;

public enum ReviewStatus { ToReview, Seen, FalsePositive }

public sealed class ReviewEntry
{
    public ReviewStatus Status { get; set; } = ReviewStatus.ToReview;
    public string Comment { get; set; } = "";
    public DateTime Updated { get; set; }
    /// <summary>Dernière forme connue du point, pour l'afficher une fois résolu (absent de l'analyse).</summary>
    public IssueSnapshot? LastSeen { get; set; }
}

public sealed record IssueSnapshot(string Rule, string Verdict, string Building, string Level, string? Lot,
                                   string Category, string Message, double? DiffM2, string AnalysisDate);

public sealed class ReviewData
{
    public string ProjectDir { get; set; } = "";
    public Dictionary<string, ReviewEntry> Entries { get; set; } = [];
}

/// <summary>
/// Statuts et commentaires des points d'attention, persistés par projet et accrochés à la clé
/// stable du point (règle|bâtiment|niveau|lot|catégorie). Un point suivi qui n'apparaît plus
/// dans la dernière analyse est « résolu ».
/// </summary>
public sealed class ReviewStore
{
    private readonly string _path;
    private readonly ReviewData _data;

    private ReviewStore(string path, ReviewData data) => (_path, _data) = (path, data);

    public static ReviewStore Open(string path, string projectDir)
    {
        var data = JsonFile.ReadOrDefault<ReviewData>(path);
        data.ProjectDir = projectDir;
        return new ReviewStore(path, data);
    }

    public ReviewEntry Get(string key) =>
        _data.Entries.TryGetValue(key, out var e) ? e : new ReviewEntry();

    public void Set(string key, ReviewStatus status, string comment, Issue? issue, string analysisDate)
    {
        var e = _data.Entries.TryGetValue(key, out var cur) ? cur : _data.Entries[key] = new ReviewEntry();
        e.Status = status;
        e.Comment = comment;
        e.Updated = DateTime.Now;
        if (issue is not null) e.LastSeen = Snapshot(issue, analysisDate);
        Save();
    }

    /// <summary>
    /// Met à jour la photo des points suivis présents dans l'analyse et renvoie les points
    /// suivis qui n'y sont plus (résolus). Seuls les points déjà touchés par l'utilisateur sont suivis.
    /// </summary>
    public IReadOnlyList<KeyValuePair<string, ReviewEntry>> Reconcile(IEnumerable<Issue> issues, string analysisDate)
    {
        var present = new HashSet<string>();
        foreach (var i in issues)
        {
            present.Add(i.Key);
            if (_data.Entries.TryGetValue(i.Key, out var e)) e.LastSeen = Snapshot(i, analysisDate);
        }
        Save();
        return _data.Entries.Where(kv => !present.Contains(kv.Key) && kv.Value.LastSeen is not null).ToList();
    }

    private static IssueSnapshot Snapshot(Issue i, string date) =>
        new(i.Rule, i.Verdict, i.Building, i.Level, i.Lot, i.Category, i.Message, i.DiffM2, date);

    private void Save() => JsonFile.Write(_path, _data);
}
