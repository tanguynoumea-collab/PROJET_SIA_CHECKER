namespace SiaCheck.Viewer.Services;

public sealed class RecentProject
{
    public string Path { get; set; } = "";
    public string Name { get; set; } = "";
    public DateTime LastAnalysis { get; set; }
    public int IssueCount { get; set; }
}

public sealed class WindowPlacement
{
    /// <summary>null = jamais positionnée (fenêtre centrée). NaN ne se sérialise pas en JSON.</summary>
    public double? Left { get; set; }
    public double? Top { get; set; }
    public double Width { get; set; } = 1600;
    public double Height { get; set; } = 960;
    public bool Maximized { get; set; } = true;
}

public sealed class AppSettings
{
    public const int MaxRecents = 8;

    public string Theme { get; set; } = "Dark";
    public bool BalanceCollapsed { get; set; }
    public double IssuesPanelWidth { get; set; } = 380;
    public WindowPlacement Window { get; set; } = new();
    public List<RecentProject> Recents { get; set; } = [];

    public void Touch(string path, string name, DateTime analysis, int issueCount)
    {
        Recents.RemoveAll(r => string.Equals(r.Path, path, StringComparison.OrdinalIgnoreCase));
        Recents.Insert(0, new RecentProject { Path = path, Name = name, LastAnalysis = analysis, IssueCount = issueCount });
        if (Recents.Count > MaxRecents) Recents.RemoveRange(MaxRecents, Recents.Count - MaxRecents);
    }

    public static AppSettings Load(AppPaths paths) => JsonFile.ReadOrDefault<AppSettings>(paths.SettingsFile);
    public void Save(AppPaths paths) => JsonFile.Write(paths.SettingsFile, this);
}
