using System.Windows;
using System.Windows.Media;
using SiaCheck.Viewer.ViewModels;

namespace SiaCheck.Viewer.Controls;

/// <summary>
/// Jauge d'un ratio informatif : une ligne fine, le repère indicatif en bande d'accent pâle,
/// la valeur du projet en cercle creux et celle du bâtiment en point plein (couleur d'alerte
/// hors repère). L'échelle couvre le repère et les deux valeurs, avec une marge.
/// Sans repère (ratio « info »), rien n'est dessiné : la valeur suffit.
/// </summary>
public sealed class RatioGauge : FrameworkElement
{
    public static readonly DependencyProperty RowProperty = DependencyProperty.Register(
        nameof(Row), typeof(RatioRow), typeof(RatioGauge), new FrameworkPropertyMetadata(null, FrameworkPropertyMetadataOptions.AffectsRender));

    public static readonly DependencyProperty TrackProperty = DependencyProperty.Register(
        nameof(Track), typeof(Brush), typeof(RatioGauge), new FrameworkPropertyMetadata(Brushes.Gray, FrameworkPropertyMetadataOptions.AffectsRender));

    public static readonly DependencyProperty AccentProperty = DependencyProperty.Register(
        nameof(Accent), typeof(Brush), typeof(RatioGauge), new FrameworkPropertyMetadata(Brushes.SteelBlue, FrameworkPropertyMetadataOptions.AffectsRender));

    public static readonly DependencyProperty WarningProperty = DependencyProperty.Register(
        nameof(Warning), typeof(Brush), typeof(RatioGauge), new FrameworkPropertyMetadata(Brushes.Orange, FrameworkPropertyMetadataOptions.AffectsRender));

    public RatioRow? Row { get => (RatioRow?)GetValue(RowProperty); set => SetValue(RowProperty, value); }
    /// <summary>Ligne et cercle du projet (TextSecondary).</summary>
    public Brush Track { get => (Brush)GetValue(TrackProperty); set => SetValue(TrackProperty, value); }
    /// <summary>Bande du repère et valeur dans le repère (Accent).</summary>
    public Brush Accent { get => (Brush)GetValue(AccentProperty); set => SetValue(AccentProperty, value); }
    /// <summary>Valeur hors repère (VerdictWarning).</summary>
    public Brush Warning { get => (Brush)GetValue(WarningProperty); set => SetValue(WarningProperty, value); }

    private const double Radius = 4;

    /// <summary>Bornes de l'échelle : repère et valeurs, élargis d'un tiers de la largeur du repère.</summary>
    public static (double Min, double Max)? Domain(RatioRow row)
    {
        var p = row.Project;
        if (p.RefMin is not double lo || p.RefMax is not double hi) return null;
        var values = new[] { lo, hi, p.Value, row.Building?.Value }.OfType<double>().ToList();
        var pad = Math.Max(hi - lo, 0.01) / 3;
        return (values.Min() - pad, values.Max() + pad);
    }

    protected override void OnRender(DrawingContext dc)
    {
        if (Row is not { } row || Domain(row) is not var (min, max)) return;
        var w = ActualWidth - 2 * Radius;
        var mid = Math.Round(ActualHeight / 2) + 0.5;
        double X(double v) => Radius + (v - min) / (max - min) * w;

        dc.DrawRectangle(Brushes.Transparent, null, new Rect(RenderSize));   // zone d'infobulle pleine
        dc.DrawLine(new Pen(Track, 1) { DashStyle = DashStyles.Dot }, new Point(Radius, mid), new Point(Radius + w, mid));

        var band = Accent.Clone();
        band.Opacity = 0.25;
        var (x0, x1) = (X(row.Project.RefMin!.Value), X(row.Project.RefMax!.Value));
        dc.DrawRectangle(band, null, new Rect(x0, mid - 5, Math.Max(x1 - x0, 1), 10));
        var edge = new Pen(Accent, 1);
        dc.DrawLine(edge, new Point(x0, mid - 5), new Point(x0, mid + 5));
        dc.DrawLine(edge, new Point(x1, mid - 5), new Point(x1, mid + 5));

        if (row.Project.Value is double pv)
            dc.DrawEllipse(null, new Pen(row.Building is null ? Fill(row.Project.Status) : Track, 1.5), new Point(X(pv), mid), Radius, Radius);
        if (row.Building?.Value is double bv)
            dc.DrawEllipse(Fill(row.Building.Status), null, new Point(X(bv), mid), Radius, Radius);
    }

    private Brush Fill(string status) => status is "bas" or "haut" ? Warning : Accent;
}
