using System.Windows;
using System.Windows.Media;
using SiaCheck.Viewer.Scene;
using SiaCheck.Viewer.ViewModels;

namespace SiaCheck.Viewer.Controls;

/// <summary>
/// Façade d'un niveau, à côté du bilan (DESIGN_PLAN, Évolution 3.6) : surface verticale, hors des sommes de la SP,
/// donc sur sa propre échelle (la plus grande façade du bâtiment). Vitrages SRV en tête, aux couleurs des calques,
/// puis la partie pleine (façade brute − vitrages). Sans façade, rien n'est dessiné.
/// </summary>
public sealed class FacadeBar : FrameworkElement
{
    public static readonly DependencyProperty RowProperty = DependencyProperty.Register(
        nameof(Row), typeof(BalanceRow), typeof(FacadeBar), new FrameworkPropertyMetadata(null, FrameworkPropertyMetadataOptions.AffectsRender));

    public static readonly DependencyProperty PaletteProperty = DependencyProperty.Register(
        nameof(Palette), typeof(SiaPalette), typeof(FacadeBar), new FrameworkPropertyMetadata(null, FrameworkPropertyMetadataOptions.AffectsRender));

    public BalanceRow? Row { get => (BalanceRow?)GetValue(RowProperty); set => SetValue(RowProperty, value); }
    public SiaPalette? Palette { get => (SiaPalette?)GetValue(PaletteProperty); set => SetValue(PaletteProperty, value); }

    protected override void OnRender(DrawingContext dc)
    {
        if (Row is not { HasFacade: true } row || Palette is not { } pal || ActualWidth <= 0) return;
        dc.DrawRectangle(Brushes.Transparent, null, new Rect(RenderSize));   // zone d'infobulle pleine
        var len = Math.Max(1, row.Facade / row.FacadeScale * ActualWidth);
        var glazing = Math.Min(len, row.Glazing / row.FacadeScale * ActualWidth);
        var top = Math.Round(ActualHeight * 0.2);
        var h = ActualHeight - 2 * top;
        if (glazing > 0) dc.DrawRectangle(new SolidColorBrush(pal.ColorOf("SRV")), null, new Rect(0, top, glazing, h));
        if (len > glazing) dc.DrawRectangle(new SolidColorBrush(pal.ColorOf("SFN")), null, new Rect(glazing, top, len - glazing, h));
    }
}
