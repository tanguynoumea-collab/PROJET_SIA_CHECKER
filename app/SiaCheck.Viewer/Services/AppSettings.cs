namespace SiaCheck.Viewer.Services;

public sealed class RecentProject
{
    public string Path { get; set; } = "";
    public string Name { get; set; } = "";
    public DateTime LastAnalysis { get; set; }
    public int IssueCount { get; set; }
}

/// <summary>Identité HRS d'un projet, écrite dans InfosProjet du MDP (clé de jointure du benchmark Power BI).</summary>
public sealed class MdpProject
{
    public string Id { get; set; } = "";
    public string Name { get; set; } = "";
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
    /// <summary>Zone bilan sur l'onglet Ratios.</summary>
    public bool ShowRatios { get; set; }
    public double IssuesPanelWidth { get; set; } = 380;
    public WindowPlacement Window { get; set; } = new();
    public List<RecentProject> Recents { get; set; } = [];
    /// <summary>ID et nom HRS de chaque projet (clé : dossier normalisé), demandés à l'export MDP.</summary>
    public Dictionary<string, MdpProject> MdpProjects { get; set; } = new(StringComparer.OrdinalIgnoreCase);

    public MdpProject? FindMdpProject(string path) => MdpProjects.GetValueOrDefault(Normalize(path));
    public void SetMdpProject(string path, MdpProject project) => MdpProjects[Normalize(path)] = project;

    public void Touch(string path, string name, DateTime analysis, int issueCount)
    {
        // « C:/…/L OREE » et « C:\…\L OREE\ » sont le même projet (ligne de commande ou dialogue d'ouverture)
        path = Normalize(path);
        Recents.RemoveAll(r => string.Equals(Normalize(r.Path), path, StringComparison.OrdinalIgnoreCase));
        Recents.Insert(0, new RecentProject { Path = path, Name = name, LastAnalysis = analysis, IssueCount = issueCount });
        if (Recents.Count > MaxRecents) Recents.RemoveRange(MaxRecents, Recents.Count - MaxRecents);
    }

    /// <summary>Retire le projet des récents et oublie son identité MDP.</summary>
    public void Forget(string path)
    {
        path = Normalize(path);
        Recents.RemoveAll(r => string.Equals(Normalize(r.Path), path, StringComparison.OrdinalIgnoreCase));
        MdpProjects.Remove(path);
    }

    private static string Normalize(string path) =>
        System.IO.Path.TrimEndingDirectorySeparator(System.IO.Path.GetFullPath(path));

    public static AppSettings Load(AppPaths paths) => JsonFile.ReadOrDefault<AppSettings>(paths.SettingsFile);
    public void Save(AppPaths paths) => JsonFile.Write(paths.SettingsFile, this);
}
