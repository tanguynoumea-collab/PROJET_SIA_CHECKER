using System.Globalization;
using System.Windows;
using System.Windows.Media;
using SiaCheck.Viewer.Services;

namespace SiaCheck.Viewer.Controls;

/// <summary>
/// Jauge circulaire de remplissage de la carte d'identité : le remplissage empilé depuis le haut, un arc par rôle
/// (identification, contraintes, réponse, performance) à la suite, chacun à proportion de ses champs remplis sur le
/// total de la carte ; le reste en gris. Le pourcentage global au centre.
/// </summary>
public sealed class CompletionRing : FrameworkElement
{
    public static readonly (string Role, Color Color)[] Roles =
    [
        ("Identification", Color.FromRgb(0x5B, 0x7F, 0xD0)),
        ("Contraintes", Color.FromRgb(0x2F, 0x9F, 0xAE)),
        ("Réponse", Color.FromRgb(0xDA, 0x2F, 0x27)),
        ("Performance", Color.FromRgb(0x3E, 0x9C, 0x7A)),
    ];

    private readonly List<(Color Color, int Filled, int Total)> _parts;
    private readonly int _filled;
    private readonly int _total;

    public CompletionRing(IdentityCard card)
    {
        _parts = Roles.Select(r =>
        {
            var fields = card.Blocks.Where(b => b.Role == r.Role).SelectMany(b => b.Fields).ToList();
            return (r.Color, fields.Count(f => f.IsFilled), fields.Count);
        }).Where(p => p.Item3 > 0).ToList();
        _filled = _parts.Sum(p => p.Filled);
        _total = _parts.Sum(p => p.Total);
        Width = Height = 120;
        ToolTip = string.Join("\n", Roles.Zip(_parts).Select(x => $"{x.First.Role} : {x.Second.Filled} / {x.Second.Total}"));
    }

    public double Percent => _total == 0 ? 0 : 100.0 * _filled / _total;

    protected override void OnRender(DrawingContext dc)
    {
        var size = Math.Min(ActualWidth, ActualHeight);
        if (size <= 0 || _total == 0) return;
        const double thickness = 12;
        var center = new Point(ActualWidth / 2, ActualHeight / 2);
        var radius = size / 2 - thickness / 2 - 1;
        // Fond gris complet, puis le remplissage empilé depuis le haut, dans le sens horaire : un arc par rôle, à la suite,
        // chacun à proportion de ses champs remplis sur le total de la carte (un léger blanc entre deux couleurs)
        var grey = (Brush)(TryFindResource("BrushDivider") ?? Brushes.LightGray);
        Arc(dc, center, radius, -90, 359.99, grey, thickness);
        const double gap = 1.5;                         // degrés entre deux couleurs
        var start = -90.0;
        foreach (var (color, filled, _) in _parts.Where(p => p.Filled > 0))
        {
            var sweep = 360.0 * filled / _total;
            Arc(dc, center, radius, start, Math.Max(sweep - gap, 0.5), new SolidColorBrush(color), thickness);
            start += sweep;
        }
        var fg = (Brush)(TryFindResource("BrushTextPrimary") ?? Brushes.Black);
        var sub = (Brush)(TryFindResource("BrushTextSecondary") ?? Brushes.Gray);
        var dpi = VisualTreeHelper.GetDpi(this).PixelsPerDip;
        var face = new Typeface(new FontFamily("Segoe UI"), FontStyles.Normal, FontWeights.SemiBold, FontStretches.Normal);
        var pct = new FormattedText($"{Percent:0} %", CultureInfo.GetCultureInfo("fr-CH"), FlowDirection.LeftToRight, face, 24, fg, dpi);
        var cap = new FormattedText("remplie", CultureInfo.GetCultureInfo("fr-CH"), FlowDirection.LeftToRight,
                                    new Typeface("Segoe UI"), 11, sub, dpi);
        dc.DrawText(pct, new Point(center.X - pct.Width / 2, center.Y - pct.Height / 2 - 6));
        dc.DrawText(cap, new Point(center.X - cap.Width / 2, center.Y + pct.Height / 2 - 8));
    }

    private static void Arc(DrawingContext dc, Point c, double r, double startDeg, double sweepDeg, Brush brush, double thickness)
    {
        Point At(double deg) => new(c.X + r * Math.Cos(deg * Math.PI / 180), c.Y + r * Math.Sin(deg * Math.PI / 180));
        var geo = new StreamGeometry();
        using (var ctx = geo.Open())
        {
            ctx.BeginFigure(At(startDeg), false, false);
            ctx.ArcTo(At(startDeg + sweepDeg), new Size(r, r), 0, sweepDeg > 180, SweepDirection.Clockwise, true, false);
        }
        geo.Freeze();
        var pen = new Pen(brush, thickness) { StartLineCap = PenLineCap.Flat, EndLineCap = PenLineCap.Flat };
        dc.DrawGeometry(null, pen, geo);
    }
}
