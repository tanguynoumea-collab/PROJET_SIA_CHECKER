using System.Windows.Media;
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
    void OpenFile(string path);
    /// <summary>Cadre la caméra sur ces bornes (null = tout le modèle visible).</summary>
    void Frame(Rect3D? bounds);
    void ApplyTheme(string theme);
    Color GhostColor { get; }
    /// <summary>Accent (sélection 3D) : tracé de la correction sélectionnée.</summary>
    Color AccentColor { get; }
}
