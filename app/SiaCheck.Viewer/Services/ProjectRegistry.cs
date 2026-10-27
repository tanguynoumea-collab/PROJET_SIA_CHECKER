using System.IO;
using System.Text.Json.Serialization;

namespace SiaCheck.Viewer.Services;

/// <summary>Avancement de la vérification d'un projet : en traitement tant qu'il reste à vérifier et corriger.</summary>
[JsonConverter(typeof(JsonStringEnumConverter<ProjectStatus>))]
public enum ProjectStatus
{
    [JsonStringEnumMemberName("en_traitement")] InProgress,
    [JsonStringEnumMemberName("traite")] Done,
}

/// <summary>Changement de statut, pour le suivi (qui a passé quoi en traité, quand).</summary>
public sealed class StatusChange
{
    public ProjectStatus Status { get; set; }
    public DateTime Date { get; set; }
    public string By { get; set; } = "";
}

public sealed class ProjectRecord
{
    public string Path { get; set; } = "";
    public string Name { get; set; } = "";
    public ProjectStatus Status { get; set; } = ProjectStatus.InProgress;
    /// <summary>Libellé affiché, écrit pour les lecteurs du fichier (n8n, Power Automate…).</summary>
    public string StatusLabel => Label(Status);
    public DateTime StatusChanged { get; set; }
    public string ChangedBy { get; set; } = "";
    public DateTime? LastAnalysis { get; set; }
    public int IssueCount { get; set; }
    public List<StatusChange> History { get; set; } = [];

    public static string Label(ProjectStatus s) => s == ProjectStatus.Done ? "Traité" : "En traitement";
}

public sealed class ProjectRegistryData
{
    public int Version { get; set; } = 1;
    public DateTime Updated { get; set; }
    public List<ProjectRecord> Projects { get; set; } = [];
}

/// <summary>
/// Registre des projets ouverts dans SIA Check et de leur statut (en traitement / traité) : un seul fichier JSON
/// (<c>%APPDATA%\SiaCheckViewer\projets.json</c>), relu à chaque accès pour qu'une automatisation (n8n) ou une autre
/// instance de l'application voie toujours le dernier état. Contrairement aux récents, un projet n'en sort que supprimé.
/// </summary>
public sealed class ProjectRegistry(string path)
{
    public string FilePath => path;

    public ProjectRecord? Find(string projectDir)
    {
        var key = Normalize(projectDir);
        return Read().Projects.FirstOrDefault(p => Same(p.Path, key));
    }

    public ProjectStatus StatusOf(string projectDir) => Find(projectDir)?.Status ?? ProjectStatus.InProgress;

    /// <summary>Projet analysé : créé « en traitement » s'il est nouveau, sinon nom et dernière analyse mis à jour.</summary>
    public ProjectRecord Touch(string projectDir, string name, DateTime analysis, int issueCount) =>
        Update(projectDir, r => { r.Name = name; r.LastAnalysis = analysis; r.IssueCount = issueCount; });

    public ProjectRecord SetStatus(string projectDir, ProjectStatus status, string? by = null) =>
        Update(projectDir, r =>
        {
            if (r.Status == status && r.History.Count > 0) return;
            r.Status = status;
            r.StatusChanged = DateTime.Now;
            r.ChangedBy = by ?? Environment.UserName;
            r.History.Add(new StatusChange { Status = status, Date = r.StatusChanged, By = r.ChangedBy });
        });

    public void Forget(string projectDir)
    {
        var data = Read();
        if (data.Projects.RemoveAll(p => Same(p.Path, Normalize(projectDir))) > 0) Write(data);
    }

    /// <summary>Nouveau dossier du projet (fiche projet) : statut et historique le suivent.</summary>
    public void Move(string oldDir, string newDir)
    {
        var data = Read();
        var record = data.Projects.FirstOrDefault(p => Same(p.Path, Normalize(oldDir)));
        if (record is null) return;
        data.Projects.RemoveAll(p => p != record && Same(p.Path, Normalize(newDir)));
        record.Path = Normalize(newDir);
        Write(data);
    }

    private ProjectRecord Update(string projectDir, Action<ProjectRecord> change)
    {
        var data = Read();
        var key = Normalize(projectDir);
        var record = data.Projects.FirstOrDefault(p => Same(p.Path, key));
        if (record is null)
        {
            record = new ProjectRecord { Path = key, Name = System.IO.Path.GetFileName(key), StatusChanged = DateTime.Now,
                                         ChangedBy = Environment.UserName };
            record.History.Add(new StatusChange { Status = record.Status, Date = record.StatusChanged, By = record.ChangedBy });
            data.Projects.Add(record);
        }
        change(record);
        Write(data);
        return record;
    }

    private ProjectRegistryData Read() => JsonFile.ReadOrDefault<ProjectRegistryData>(path);

    private void Write(ProjectRegistryData data)
    {
        data.Updated = DateTime.Now;
        data.Projects.Sort((a, b) => string.Compare(a.Name, b.Name, StringComparison.CurrentCultureIgnoreCase));
        JsonFile.Write(path, data);
    }

    private static bool Same(string a, string b) => string.Equals(Normalize(a), b, StringComparison.OrdinalIgnoreCase);

    private static string Normalize(string p) => System.IO.Path.TrimEndingDirectorySeparator(System.IO.Path.GetFullPath(p));
}
