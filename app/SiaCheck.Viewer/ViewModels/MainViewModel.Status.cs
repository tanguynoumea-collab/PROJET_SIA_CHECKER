using CommunityToolkit.Mvvm.Input;
using SiaCheck.Viewer.Models;
using SiaCheck.Viewer.Services;

namespace SiaCheck.Viewer.ViewModels;

/// <summary>
/// Projet de la liste « Projets » de l'accueil (Minage de données, Évolution 4.5), avec son statut (registre des projets) :
/// un projet Treegram, ou un projet généré depuis un IFC (<paramref name="generated"/>).
/// </summary>
public sealed class RecentItem(RecentProject project, ProjectStatus status, MdpProject? identity = null, bool exists = true,
                               GeneratedInfo? generated = null)
{
    public RecentProject Project { get; } = project;
    public GeneratedInfo? Generated { get; } = generated;
    /// <summary>Généré depuis un IFC : glyphe cube, état des espaces, Régénérer (clic droit), ouverture sur l'onglet Espaces.</summary>
    public bool IsIfc => Generated is not null;
    public string SourceTooltip => IsIfc ? $"Généré depuis un IFC : {Generated!.Source}" : "Projet Treegram";
    /// <summary>Maquette dont le projet est tiré (infobulle de Régénérer).</summary>
    public string Source => Generated?.Source ?? "";
    /// <summary>Tous les espaces tranchés (coche) : projet IFC seulement.</summary>
    public bool IsSettled => Generated?.State.ToDecide == 0;
    /// <summary>Espaces à trancher (pastille accent) : la seule activité qui demande une action.</summary>
    public int ToDecide => Generated?.State.ToDecide ?? 0;
    public bool HasToDecide => ToDecide > 0;
    public bool ShowsPoints => !IsIfc;
    public string ActivityTooltip => Generated is { } g
        ? (g.State.ToDecide == 0 ? "Tous les espaces sont tranchés" : $"{g.State.ToDecide} espace{(g.State.ToDecide > 1 ? "s" : "")} à trancher (onglet Espaces)")
        : $"{Project.IssueCount} point{(Project.IssueCount > 1 ? "s" : "")} d'attention à la dernière analyse";
    /// <summary>Colonne d'activité : les points de l'analyse, ou les espaces à trancher d'un projet généré.</summary>
    public string ActivityText => Generated is { } g
        ? (g.State.ToDecide == 0 ? "tout tranché" : $"{g.State.ToDecide} à trancher")
        : $"{Project.IssueCount} points";
    /// <summary>Nom du dossier (repli du nom de la fiche, nommage des fichiers).</summary>
    public string Name => Project.Name;
    public MdpProject? Identity { get; } = identity;
    /// <summary>Nom de la fiche projet, sinon celui du dossier.</summary>
    public string DisplayName => Identity?.Name is { Length: > 0 } n ? n : Project.Name;
    public string IdText => Identity?.Id is { Length: > 0 } id ? id : "—";
    /// <summary>Liste de l'accueil : l'ID, ou rien (pas de tiret répété sur chaque ligne sans ID).</summary>
    public string IdShort => Identity?.Id is { Length: > 0 } id ? id : "";
    public string TypologieText => ProjectIdentity.Short(Identity?.Typologie);
    public string CantonText => Identity?.Canton is { Length: > 0 } c ? c : "—";
    /// <summary>Liste de l'accueil : typologie et canton connus, sinon rien (le ⚠ du nom dit ce qui manque).</summary>
    public string TypologieShort => Identity?.Typologie is { Length: > 0 } t ? ProjectIdentity.Short(t) : "";
    public string CantonShort => Identity?.Canton ?? "";
    public bool FolderMissing { get; } = !exists;
    /// <summary>Ce qui manque au projet : son dossier, sinon une partie de l'identité nécessaire au benchmark.</summary>
    public string? Warning => FolderMissing ? "Dossier introuvable"
        : Identity is null || ProjectIdentity.Missing(Identity, forBase: true).Count > 0 ? "Infos à compléter" : null;
    public bool HasWarning => Warning is not null;
    /// <summary>Intertitre de la liste de l'accueil (Évolution 4.6) : le statut regroupe, il n'est plus redit sur chaque ligne.</summary>
    public string GroupLabel => IsDone ? "Traités" : "En traitement";
    public string Path => Project.Path;
    public int IssueCount => Project.IssueCount;
    public DateTime LastAnalysis => Project.LastAnalysis;
    /// <summary>Traité, modifié ou non depuis : il a nourri la base (⇥ pour le republier).</summary>
    public bool IsDone { get; } = status is ProjectStatus.Done or ProjectStatus.DoneModified;
    /// <summary>Modifié depuis son passage en traité : son MDP de la base n'est plus à jour.</summary>
    public bool IsModified { get; } = status == ProjectStatus.DoneModified;
    public string StatusLabel { get; } = ProjectRecord.Label(status);
}

/// <summary>
/// Statut du projet ouvert : « en traitement » à la première analyse, « traité » quand la vérification et les
/// corrections sont finies. Écrit dans le registre des projets (projets.json), que lisent les automatisations (n8n).
/// </summary>
public sealed partial class MainViewModel
{
    private ProjectStatus _projectStatus;
    private string _projectStatusChanged = "";

    public bool IsProjectDone => _projectStatus == ProjectStatus.Done;
    public bool IsProjectModified => _projectStatus == ProjectStatus.DoneModified;
    public string ProjectStatusLabel => ProjectRecord.Label(_projectStatus);
    public string ProjectStatusTooltip => _projectStatus switch
    {
        ProjectStatus.Done => "Projet vérifié et corrigé. Cliquer pour le remettre en traitement.",
        ProjectStatus.DoneModified => "Modifié depuis son passage en traité : le MDP de la base n'est plus à jour. " +
                                      "Cliquer pour le republier (le dashboard sera mis à jour).",
        _ => "Vérification en cours. Cliquer pour passer le projet en traité : son MDP est alors exporté dans la base du benchmark.",
    } + _projectStatusChanged;

    /// <summary>
    /// Un projet traité qu'on modifie (décision de correction, fiche projet) passe « Traité · modifié » : on peut
    /// continuer à modifier et enregistrer, la base ne change qu'à la republication.
    /// </summary>
    internal void MarkModifiedIfDone(string? projectDir)
    {
        if (projectDir is null || _registry.StatusOf(projectDir) != ProjectStatus.Done) return;
        try
        {
            var r = _registry.SetStatus(projectDir, ProjectStatus.DoneModified);
            if (ProjectDir is not null && ProjectFolder.Same(ProjectDir, projectDir)) ShowProjectStatus(r);
        }
        catch (Exception ex) when (ex is System.IO.IOException or UnauthorizedAccessException)
        {
            _shell.Notify($"Statut non enregistré : {ex.Message}", isError: true);
        }
    }

    /// <summary>Points ouverts encore « à traiter », hors agrégats.</summary>
    internal int OpenIssuesToReview => Issues.Count(i => !i.IsResolved && !i.IsAggregate && i.Status == ReviewStatus.ToReview);
    internal int UndecidedCorrections => Subjects.Where(s => s.CanDecide).Sum(s => s.ProposedCount);

    private void LoadProjectStatus(string projectDir, string name, int issueCount)
    {
        ShowProjectStatus(_registry.Touch(projectDir, name, DateTime.Now, issueCount));
    }

    private void ShowProjectStatus(ProjectRecord r)
    {
        _projectStatus = r.Status;
        _projectStatusChanged = $"\n{r.StatusLabel} depuis le {r.StatusChanged:dd.MM.yyyy HH:mm}" +
                                (string.IsNullOrEmpty(r.ChangedBy) ? "" : $" ({r.ChangedBy})");
        OnPropertyChanged(nameof(IsProjectDone));
        OnPropertyChanged(nameof(IsProjectModified));
        OnPropertyChanged(nameof(ProjectStatusLabel));
        OnPropertyChanged(nameof(ProjectStatusTooltip));
    }

    [RelayCommand]
    private async Task ToggleProjectStatusAsync()
    {
        if (ProjectDir is null || Document is null) return;
        if (IsProjectModified)
        {
            // Modifié depuis la publication : republier ? Sinon on garde la main pour d'autres modifications.
            if (await _shell.ConfirmAsync($"Republier « {ProjectName} » ?",
                    "Le projet a été modifié depuis son passage en traité. Republier réexporte son MDP dans la base du " +
                    "benchmark, et le dashboard est mis à jour.\n\nVous pouvez aussi continuer à le modifier et republier plus tard.",
                    "Republier", "Plus tard"))
                await AddProjectToBaseAsync(ProjectDir, Document.Project, onValidation: false, republish: true);
            return;
        }
        var next = IsProjectDone ? ProjectStatus.InProgress : ProjectStatus.Done;
        if (next == ProjectStatus.Done)
        {
            var left = new List<string>();
            if (PendingCorrections > 0) left.Add($"{PendingCorrections} décision{S(PendingCorrections)} sur les corrections pas encore appliquée{S(PendingCorrections)} (Analyser)");
            if (UndecidedCorrections is > 0 and var u) left.Add($"{u} correction{S(u)} proposée{S(u)} sans décision");
            if (OpenIssuesToReview is > 0 and var n) left.Add($"{n} point{S(n)} d'attention encore à traiter");
            if (left.Count > 0 && !await _shell.ConfirmAsync("Passer le projet en traité ?",
                    "Il reste :\n• " + string.Join("\n• ", left) + "\n\nLe projet peut être passé en traité quand même.",
                    "Passer en traité", "Annuler"))
                return;
        }
        try
        {
            ShowProjectStatus(_registry.SetStatus(ProjectDir, next));
        }
        catch (Exception ex) when (ex is System.IO.IOException or UnauthorizedAccessException)
        {
            _shell.Notify($"Statut non enregistré : {ex.Message}", isError: true);
            return;
        }
        // Projet validé : son MDP rejoint la base du benchmark (le statut reste « traité » même si l'export n'a pas lieu)
        if (next == ProjectStatus.Done) await AddProjectToBaseAsync(ProjectDir, Document.Project, onValidation: true);
        else _shell.Notify($"« {ProjectName} » remis en traitement.");
    }

    /// <summary>
    /// Projets de l'accueil (Minage de données) : les projets Treegram des récents et les projets générés du dossier des
    /// projets générés, mêlés ; en traitement d'abord, puis traités, le plus récent d'abord.
    /// </summary>
    private void FillRecents()
    {
        Recents.Clear();
        // Projets générés inscrits parmi les récents par les versions 4.0 : retirés, ils sont lus dans leur dossier
        if (_settings.Recents.RemoveAll(r => GenerationReport.Exists(r.Path)) > 0) _settings.Save(_paths);
        // Un dossier introuvable reste listé (signalé) : la fiche projet permet de le repointer
        var items = _settings.Recents
            .Select(r => new RecentItem(r, _registry.StatusOf(r.Path), _settings.FindMdpProject(r.Path), System.IO.Directory.Exists(r.Path)))
            .Concat(GeneratedProjects())
            .Select((r, i) => (r, i))
            .OrderBy(x => x.r.IsDone).ThenByDescending(x => x.r.LastAnalysis).ThenBy(x => x.i)
            .Select(x => x.r);
        foreach (var r in items) Recents.Add(r);
    }

    private static string S(int n) => n > 1 ? "s" : "";
}
