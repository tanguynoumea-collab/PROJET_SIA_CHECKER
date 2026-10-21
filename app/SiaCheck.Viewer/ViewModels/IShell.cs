using System.Windows.Media;
using System.Windows.Media.Media3D;

namespace SiaCheck.Viewer.ViewModels;

/// <summary>Ce que le ViewModel demande à la fenêtre : dialogues, notifications, caméra.</summary>
public interface IShell
{
    string? PickFolder(string title, string? initial);
    void Notify(string message, bool isError = false);
    void OpenFile(string path);
    /// <summary>Cadre la caméra sur ces bornes (null = tout le modèle visible).</summary>
    void Frame(Rect3D? bounds);
    void ApplyTheme(string theme);
    Color GhostColor { get; }
}
