using System.Windows;
using System.Windows.Media;
using SiaCheck.Viewer.Services;

namespace SiaCheck.Viewer.Controls;

/// <summary>
/// Vignette d'implantation de la carte d'identité (V7) : la parcelle (trait fin, nord en haut) et l'emprise hors-sol de
/// la maquette (aplat rouge, comme le volume), à échelle constante pour tous les projets : 1:5000 à 96 ppp, la même que
/// la planche des implantations du benchmark, plus petite seulement si le projet ne tient pas dans le cadre (l'échelle
/// réelle est alors donnée par <see cref="Scale"/>). Moteur : sia_check.carte.implantation.
/// </summary>
public sealed class FootprintPlan : FrameworkElement
{
    /// <summary>Pixels par mètre au 1:5000, à 96 ppp.</summary>
    public const double PixelsPerMetre = 96 / 0.0254 / 5000;
    private static readonly Color Fill = Color.FromRgb(0xDA, 0x2F, 0x27);
    private readonly IdentityCardImplantation _plan;

    public FootprintPlan(IdentityCardImplantation plan)
    {
        _plan = plan;
        SnapsToDevicePixels = true;
    }

    /// <summary>Dénominateur de l'échelle du dernier dessin (5000, ou plus si le projet est grand).</summary>
    public int Scale { get; private set; } = 5000;

    /// <summary>Pixels par mètre pour que l'étendue (m, depuis le centre) tienne dans le cadre : 1:5000, sinon moins.</summary>
    internal static double Fit(IdentityCardImplantation plan, double width, double height)
    {
        var pts = plan.Parcel.Concat(plan.Footprint).SelectMany(p => p).SelectMany(r => r).Where(v => v.Count >= 2).ToList();
        if (pts.Count == 0) return PixelsPerMetre;
        var half = pts.Max(v => Math.Max(Math.Abs(v[0]), Math.Abs(v[1])));
        var room = Math.Min(width, height) / 2 - 8;
        return half <= 0 || room <= 0 ? PixelsPerMetre : Math.Min(PixelsPerMetre, room / half);
    }

    protected override void OnRender(DrawingContext dc)
    {
        double w = ActualWidth, h = ActualHeight;
        if (w <= 0 || h <= 0) return;
        var k = Fit(_plan, w, h);
        Scale = (int)(Math.Round(96 / 0.0254 / k / 500) * 500);
        var c = new Point(w / 2, h / 2);
        var text = (Brush)(TryFindResource("BrushTextSecondary") ?? Brushes.Gray);
        var parcel = new Pen(text, 1);
        parcel.Freeze();
        if (Geometry(_plan.Parcel, k, c) is { } g) dc.DrawGeometry(null, parcel, g);
        if (Geometry(_plan.Footprint, k, c) is { } f)
        {
            var fill = new SolidColorBrush(Fill);
            fill.Freeze();
            dc.DrawGeometry(fill, null, f);
        }
        // barre d'échelle (la plus grande longueur ronde sous 60 px) et nord
        var bar = new[] { 10, 20, 25, 50, 100, 200, 500 }.LastOrDefault(m => m * k <= 60, 10);
        var pen = new Pen(text, 2);
        pen.Freeze();
        dc.DrawLine(pen, new Point(8, h - 8), new Point(8 + bar * k, h - 8));
        var dpi = VisualTreeHelper.GetDpi(this).PixelsPerDip;
        var label = new FormattedText($"{bar} m", System.Globalization.CultureInfo.CurrentCulture, FlowDirection.LeftToRight,
                                      new Typeface("Segoe UI"), 10, text, dpi);
        dc.DrawText(label, new Point(8, h - 22));
        var north = new FormattedText("N", System.Globalization.CultureInfo.CurrentCulture, FlowDirection.LeftToRight,
                                      new Typeface("Segoe UI"), 10, text, dpi);
        dc.DrawText(north, new Point(w - 14, 4));
    }

    /// <summary>Polygones [polygone][anneau][point] en mètres, y vers le haut (nord), centrés sur <paramref name="c"/>.</summary>
    internal static Geometry? Geometry(List<List<List<List<double>>>> polygons, double k, Point c)
    {
        var geo = new StreamGeometry { FillRule = FillRule.EvenOdd };
        var any = false;
        using (var ctx = geo.Open())
        {
            foreach (var ring in polygons.SelectMany(p => p).Where(r => r.Count >= 3))
            {
                var pts = ring.Where(v => v.Count >= 2).Select(v => new Point(c.X + v[0] * k, c.Y - v[1] * k)).ToList();
                ctx.BeginFigure(pts[0], isFilled: true, isClosed: true);
                ctx.PolyLineTo(pts.Skip(1).ToList(), isStroked: true, isSmoothJoin: false);
                any = true;
            }
        }
        if (!any) return null;
        geo.Freeze();
        return geo;
    }
}
