using System.Windows;
using System.Windows.Controls;
using Wpf.Ui.Controls;

namespace SiaCheck.Viewer.Controls;

/// <summary>
/// Glyphe contouré d'un verdict (plan §2 : « le remplissage dit la catégorie, le trait dit le verdict »).
/// ERREUR = cercle barré, ALERTE = triangle, INFO = i cerclé, OK = coche. Jamais une pastille pleine.
/// </summary>
public sealed class VerdictGlyph : ContentControl
{
    public static readonly DependencyProperty VerdictProperty = DependencyProperty.Register(
        nameof(Verdict), typeof(string), typeof(VerdictGlyph), new PropertyMetadata(null, (d, _) => ((VerdictGlyph)d).Update()));

    public string? Verdict { get => (string?)GetValue(VerdictProperty); set => SetValue(VerdictProperty, value); }

    private readonly SymbolIcon _icon = new() { Filled = false };

    public VerdictGlyph()
    {
        Content = _icon;
        Focusable = false;
        IsTabStop = false;
        Update();
    }

    private void Update()
    {
        (_icon.Symbol, var brushKey, var label) = Verdict switch
        {
            "ERREUR" => (SymbolRegular.Prohibited20, "BrushVerdictError", "Erreur"),
            "ALERTE" => (SymbolRegular.Warning20, "BrushVerdictWarning", "Alerte"),
            "INFO" => (SymbolRegular.Info20, "BrushVerdictInfo", "Information"),
            "OK" => (SymbolRegular.CheckmarkCircle20, "BrushStatusSeen", "Conforme"),
            _ => (SymbolRegular.Circle20, "BrushTextSecondary", ""),
        };
        _icon.SetResourceReference(SymbolIcon.ForegroundProperty, brushKey);
        System.Windows.Automation.AutomationProperties.SetName(this, label);
        ToolTip = string.IsNullOrEmpty(label) ? null : label;
    }
}
