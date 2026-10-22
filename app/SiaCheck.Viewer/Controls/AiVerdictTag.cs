using System.Windows;
using System.Windows.Controls;
using SiaCheck.Viewer.Services;

namespace SiaCheck.Viewer.Controls;

/// <summary>
/// Étiquette contourée du verdict IA (« S1 · vrai sujet »). Comme <see cref="VerdictGlyph"/> : le trait dit le
/// verdict, le libellé est toujours écrit (plan, Évolution 1.1). Vrai sujet = trait erreur, à confirmer = trait
/// alerte, faux positif et agrégat = trait secondaire.
/// </summary>
public sealed class AiVerdictTag : Border
{
    public static readonly DependencyProperty KindProperty = DependencyProperty.Register(
        nameof(Kind), typeof(AiVerdictKind), typeof(AiVerdictTag),
        new PropertyMetadata(AiVerdictKind.Unknown, (d, _) => ((AiVerdictTag)d).Update()));

    public static readonly DependencyProperty TextProperty = DependencyProperty.Register(
        nameof(Text), typeof(string), typeof(AiVerdictTag), new PropertyMetadata("", (d, _) => ((AiVerdictTag)d).Update()));

    public AiVerdictKind Kind { get => (AiVerdictKind)GetValue(KindProperty); set => SetValue(KindProperty, value); }
    public string Text { get => (string)GetValue(TextProperty); set => SetValue(TextProperty, value); }

    private readonly TextBlock _text = new() { VerticalAlignment = VerticalAlignment.Center };

    public AiVerdictTag()
    {
        Child = _text;
        BorderThickness = new Thickness(1);
        Padding = new Thickness(6, 0, 6, 1);
        VerticalAlignment = VerticalAlignment.Center;
        SetResourceReference(CornerRadiusProperty, "RadiusControl");
        _text.SetResourceReference(TextBlock.FontFamilyProperty, "FontMono");
        _text.SetResourceReference(TextBlock.FontSizeProperty, "FontSizeCaption");
        Update();
    }

    private void Update()
    {
        var (border, text) = Kind switch
        {
            AiVerdictKind.TrueIssue => ("BrushVerdictError", "BrushTextPrimary"),
            AiVerdictKind.ToConfirm => ("BrushVerdictWarning", "BrushTextPrimary"),
            _ => ("BrushTextSecondary", "BrushTextSecondary"),
        };
        SetResourceReference(BorderBrushProperty, border);
        _text.SetResourceReference(TextBlock.ForegroundProperty, text);
        _text.Text = Text;
        Visibility = string.IsNullOrEmpty(Text) ? Visibility.Collapsed : Visibility.Visible;
        System.Windows.Automation.AutomationProperties.SetName(this, $"Verdict IA : {Text}");
    }
}
