using System.Windows;
using System.Windows.Controls;
using SiaCheck.Viewer.ViewModels;
using Wpf.Ui.Controls;

namespace SiaCheck.Viewer.Controls;

/// <summary>
/// État d'une correction, en glyphe contouré comme les verdicts (plan, Évolution 2.0) :
/// proposée = cercle vide, acceptée = coche, appliquée = coche dans un cercle, rejetée = croix,
/// inapplicable = triangle. Le libellé est toujours dans l'infobulle et le nom d'automatisation.
/// </summary>
public sealed class CorrectionGlyph : ContentControl
{
    public static readonly DependencyProperty StateProperty = DependencyProperty.Register(
        nameof(State), typeof(CorrectionState), typeof(CorrectionGlyph),
        new PropertyMetadata(CorrectionState.Proposed, (d, _) => ((CorrectionGlyph)d).Update()));

    public static readonly DependencyProperty SizeProperty = DependencyProperty.Register(
        nameof(Size), typeof(double), typeof(CorrectionGlyph), new PropertyMetadata(16.0, (d, _) => ((CorrectionGlyph)d).Update()));

    public CorrectionState State { get => (CorrectionState)GetValue(StateProperty); set => SetValue(StateProperty, value); }
    public double Size { get => (double)GetValue(SizeProperty); set => SetValue(SizeProperty, value); }

    private readonly SymbolIcon _icon = new() { Filled = false };

    public CorrectionGlyph()
    {
        Content = _icon;
        Focusable = false;
        IsTabStop = false;
        Update();
    }

    private void Update()
    {
        (_icon.Symbol, var brush, var label) = State switch
        {
            CorrectionState.Accepted => (SymbolRegular.Checkmark20, "BrushStatusSeen", "Acceptée, à appliquer (Analyser)"),
            CorrectionState.Applied => (SymbolRegular.CheckmarkCircle20, "BrushStatusSeen", "Appliquée"),
            CorrectionState.Rejected => (SymbolRegular.Dismiss20, "BrushTextSecondary", "Rejetée"),
            CorrectionState.Failed => (SymbolRegular.Warning20, "BrushVerdictWarning", "Inapplicable"),
            _ => (SymbolRegular.Circle20, "BrushTextSecondary", "Proposée"),
        };
        _icon.FontSize = Size;
        _icon.SetResourceReference(SymbolIcon.ForegroundProperty, brush);
        System.Windows.Automation.AutomationProperties.SetName(this, label);
        ToolTip = label;
    }
}
