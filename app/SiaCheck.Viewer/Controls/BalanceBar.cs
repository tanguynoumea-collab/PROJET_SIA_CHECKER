using System.Windows;
using System.Windows.Media;
using SiaCheck.Viewer.Scene;
using SiaCheck.Viewer.ViewModels;

namespace SiaCheck.Viewer.Controls;

/// <summary>
/// Barre de sommation d'un niveau (plan de design §6) :
/// longueur = SP, remplie par SUP, SUS, SD, SI aux couleurs SIA ; ce qui n'est pas couvert
/// reste vide avec un simple contour (le résidu, rendu visible). Dessous, plus fine,
/// la SEP hachurée avec SEU et SED. Si les sous-catégories dépassent la SP (R4), le surplus
/// déborde de la barre, contouré dans la couleur d'erreur.
/// </summary>
public sealed class BalanceBar : FrameworkElement
{
    public static readonly DependencyProperty RowProperty = DependencyProperty.Register(
        nameof(Row), typeof(BalanceRow), typeof(BalanceBar), new FrameworkPropertyMetadata(null, FrameworkPropertyMetadataOptions.AffectsRender));

    public static readonly DependencyProperty PaletteProperty = DependencyProperty.Register(
        nameof(Palette), typeof(SiaPalette), typeof(BalanceBar), new FrameworkPropertyMetadata(null, FrameworkPropertyMetadataOptions.AffectsRender));

    public static readonly DependencyProperty OutlineProperty = DependencyProperty.Register(
        nameof(Outline), typeof(Brush), typeof(BalanceBar), new FrameworkPropertyMetadata(Brushes.Gray, FrameworkPropertyMetadataOptions.AffectsRender));

    public static readonly DependencyProperty ErrorProperty = DependencyProperty.Register(
        nameof(Error), typeof(Brush), typeof(BalanceBar), new FrameworkPropertyMetadata(Brushes.Red, FrameworkPropertyMetadataOptions.AffectsRender));

    public BalanceRow? Row { get => (BalanceRow?)GetValue(RowProperty); set => SetValue(RowProperty, value); }
    public SiaPalette? Palette { get => (SiaPalette?)GetValue(PaletteProperty); set => SetValue(PaletteProperty, value); }
    /// <summary>Contour du résidu (TextSecondary).</summary>
    public Brush Outline { get => (Brush)GetValue(OutlineProperty); set => SetValue(OutlineProperty, value); }
    /// <summary>Contour du dépassement R4 (VerdictError).</summary>
    public Brush Error { get => (Brush)GetValue(ErrorProperty); set => SetValue(ErrorProperty, value); }

    private const double FloorShare = 0.62;   // part de la hauteur pour la barre SP
    private const double Gap = 2;

    protected override void OnRender(DrawingContext dc)
    {
        if (Row is not { } row || Palette is not { } pal || ActualWidth <= 0) return;
        var w = ActualWidth;
        var h = ActualHeight;
        double X(double m2) => Math.Max(0, m2 / row.Scale * w);

        var floorH = row.Sep > 0 ? h * FloorShare : h;
        if (row.HasFloor)
        {
            double x = 0;
            foreach (var code in BalanceRow.FloorParts)
            {
                var len = X(row.Source.Value(code));
                if (len <= 0) continue;
                dc.DrawRectangle(pal.BrushOf(code), null, new Rect(x, 0, len, floorH));
                x += len;
            }
            var sp = X(row.Sp);
            var pen = new Pen(Outline, 1);
            pen.Freeze();
            if (x < sp - 0.5)
                dc.DrawRectangle(null, pen, new Rect(x + 0.5, 0.5, sp - x - 1, floorH - 1));
            else if (x > sp + 0.5)
            {
                var err = new Pen(Error, 1.5);
                err.Freeze();
                dc.DrawRectangle(null, err, new Rect(sp, 0.75, x - sp, floorH - 1.5));
            }
            // Repère de fin de SP, toujours visible : la longueur de référence du niveau.
            dc.DrawLine(pen, new Point(sp - 0.5, 0), new Point(sp - 0.5, floorH));
        }

        if (row.Sep > 0)
        {
            var y = row.HasFloor ? floorH + Gap : 0;
            var sepH = h - y;
            var sep = X(row.Sep);
            dc.DrawRectangle(pal.BrushOf("SEP"), null, new Rect(0, y, sep, sepH));
            double x = 0;
            foreach (var code in BalanceRow.ExternalParts)
            {
                var len = X(row.Source.Value(code));
                if (len <= 0) continue;
                dc.DrawRectangle(new SolidColorBrush(pal.ColorOf(code)), null, new Rect(x, y, len, sepH));
                x += len;
            }
        }
    }
}
