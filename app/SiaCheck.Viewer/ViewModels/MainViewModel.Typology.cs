using CommunityToolkit.Mvvm.Input;
using SiaCheck.Viewer.Services;

namespace SiaCheck.Viewer.ViewModels;

/// <summary>
/// Typologie du projet et repères des ratios (décision du 28.10.2026) : un repère ne vaut que pour un type de bâtiment.
/// La typologie de la fiche projet part au moteur (<c>--typologie</c>) ; sans elle, les ratios n'ont pas de repère et
/// l'onglet Ratios le dit, avec la typologie que le moteur propose d'après les surfaces.
/// </summary>
public sealed partial class MainViewModel
{
    private readonly HashSet<string> _typologyAsked = new(StringComparer.OrdinalIgnoreCase);

    private static bool IsHousing(string? key) => key is "logement" or "mixte";

    /// <summary>Bandeau de l'onglet Ratios : typologie manquante, ou repères sans objet pour la typologie choisie.</summary>
    public string TypologyBanner => Document?.Typologie switch
    {
        null => "",
        { Chosen: null or "" } t => "Typologie du projet non renseignée : les repères des ratios dépendent du type de bâtiment, ils ne "
                                    + "s'appliquent pas." + (t.Proposed is { } p ? $" Proposée d'après les surfaces : {ProjectIdentity.Short(p)} ({t.Reason})." : ""),
        { Key: var k, Chosen: var c } when !IsHousing(k) => $"Typologie « {ProjectIdentity.Short(c)} » : les repères des ratios sont établis "
                                    + "sur des projets de logement, ils ne s'appliquent pas à ce projet.",
        _ => "",
    };
    public bool HasTypologyBanner => TypologyBanner.Length > 0;
    public bool CanSetTypology => Document?.Typologie is { Chosen: null or "" };

    /// <summary>Renseigner la typologie : la fiche projet, typologie proposée présélectionnée ; puis réanalyse.</summary>
    [RelayCommand]
    private async Task SetTypologyAsync()
    {
        if (ProjectDir is null || Document is null) return;
        var sheet = await EditSheetAsync(ProjectDir, Document.Project, Document.Typologie?.Proposed);
        if (sheet is not null && !string.IsNullOrWhiteSpace(sheet.Identity.Typologie)) await AnalyseAsync();
    }

    /// <summary>
    /// Avant une analyse : une typologie manquante est demandée une fois par projet et par session (fiche projet, typologie
    /// proposée présélectionnée). Annuler laisse analyser sans repères.
    /// </summary>
    private async Task AskTypologyOnceAsync()
    {
        if (ProjectDir is null || Document?.Typologie is not { Chosen: null or "", Proposed: { } proposed }
            || !string.IsNullOrWhiteSpace(_settings.FindMdpProject(ProjectDir)?.Typologie) || !_typologyAsked.Add(ProjectDir))
            return;
        await EditSheetAsync(ProjectDir, Document.Project, proposed);
    }
}
