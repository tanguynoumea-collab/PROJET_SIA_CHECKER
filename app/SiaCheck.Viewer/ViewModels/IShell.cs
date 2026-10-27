using System.Windows.Media;
using SiaCheck.Viewer.Services;
using System.Windows.Media.Media3D;

namespace SiaCheck.Viewer.ViewModels;

/// <summary>Ce que le ViewModel demande à la fenêtre : dialogues, notifications, caméra.</summary>
public interface IShell
{
    string? PickFolder(string title, string? initial);
    /// <summary>Dialogue d'enregistrement ; filtre au format WPF (« Classeur Excel|*.xlsx »).</summary>
    string? PickSaveFile(string title, string fileName, string filter);
    string? PickOpenFile(string title, string filter);
    void Notify(string message, bool isError = false);
    /// <summary>Question à deux réponses ; true = <paramref name="yes"/>.</summary>
    Task<bool> ConfirmAsync(string title, string message, string yes, string no);
    /// <summary>Petit formulaire : un champ texte par libellé, prérempli ; null si l'utilisateur annule.</summary>
    Task<string[]?> AskAsync(string title, string message, IReadOnlyList<(string Label, string Value)> fields, string ok);
    /// <summary>Fiche « Identité du projet » (docs/DESIGN_PLAN.md, Évolution 3.4) ; null si annulée.</summary>
    Task<MdpProject?> AskIdentityAsync(MdpProject initial, IdentityLists lists, IdentityMode mode, string ok);
    /// <summary>
    /// Fiche projet (Évolution 3.8) : dossier Treegram et identité ; <paramref name="check"/> contrôle la saisie à chaque
    /// changement (dossier valide, déjà pris, ID en double). null si annulée.
    /// </summary>
    Task<ProjectSheet?> AskProjectSheetAsync(ProjectSheet initial, IdentityLists lists, bool creating, Func<ProjectSheet, SheetCheck> check);
    void OpenFile(string path);
    /// <summary>Cadre la caméra sur ces bornes (null = tout le modèle visible).</summary>
    void Frame(Rect3D? bounds);
    void ApplyTheme(string theme);
    Color GhostColor { get; }
    /// <summary>Accent (sélection 3D) : tracé de la correction sélectionnée.</summary>
    Color AccentColor { get; }
}
