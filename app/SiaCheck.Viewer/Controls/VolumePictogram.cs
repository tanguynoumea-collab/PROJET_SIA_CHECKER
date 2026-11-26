using System.Windows;
using System.Windows.Media;
using SiaCheck.Viewer.Services;

namespace SiaCheck.Viewer.Controls;

/// <summary>
/// Pictogramme du volume d'un projet, en tête de la carte d'identité : les prismes du volume hors-sol (moteur,
/// sia_check.carte._volume) en axonométrie isométrique, volume rouge plein, faces ombrées selon leur orientation, à la
/// manière des pictogrammes de forme de Density (a+t). Dessin propre à SIA Check, tiré de la maquette du projet.
/// </summary>
public sealed class VolumePictogram : FrameworkElement
{
    private static readonly double Cos30 = Math.Cos(Math.PI / 6);
    private const double Sin30 = 0.5;
    private static readonly Color Base = Color.FromRgb(0xDA, 0x2F, 0x27);
    private static readonly Color TopColor = Color.FromRgb(0xEE, 0x55, 0x4B);
    private readonly IReadOnlyList<VolumePrism> _prisms;

    public VolumePictogram(IReadOnlyList<VolumePrism> prisms)
    {
        _prisms = Oriented(prisms);
        SnapsToDevicePixels = true;
    }

    /// <summary>
    /// Le volume tourné en plan pour que sa plus grande dimension (axe principal des sommets) suive l'horizontale de
    /// l'image : en isométrie, c'est la direction (1, −1) du plan. Le pictogramme remplit ainsi son cadre.
    /// </summary>
    internal static IReadOnlyList<VolumePrism> Oriented(IReadOnlyList<VolumePrism> prisms)
    {
        var pts = prisms.SelectMany(p => p.Rings).SelectMany(r => r).Where(v => v.Count >= 2).ToList();
        if (pts.Count < 3) return prisms;
        double mx = pts.Average(v => v[0]), my = pts.Average(v => v[1]);
        double sxx = pts.Sum(v => (v[0] - mx) * (v[0] - mx)), syy = pts.Sum(v => (v[1] - my) * (v[1] - my));
        var sxy = pts.Sum(v => (v[0] - mx) * (v[1] - my));
        var axis = 0.5 * Math.Atan2(2 * sxy, sxx - syy);          // angle de l'axe principal
        var rot = -Math.PI / 4 - axis;
        double c = Math.Cos(rot), s = Math.Sin(rot);
        return prisms.Select(p => new VolumePrism
        {
            Building = p.Building, Bottom = p.Bottom, Top = p.Top,
            Rings = p.Rings.Select(r => r.Select(v => new List<double> { (v[0] - mx) * c - (v[1] - my) * s, (v[0] - mx) * s + (v[1] - my) * c }).ToList()).ToList(),
        }).ToList();
    }

    private static Point Project(double x, double y, double z) => new((x - y) * Cos30, (x + y) * Sin30 - z);

    /// <summary>Les faces visibles, de l'arrière vers l'avant : bâtiments de loin vers près, leurs prismes de bas en
    /// haut ; dans un prisme, ses côtés de loin vers près, puis son dessus.</summary>
    internal static List<(List<Point[]> Rings, Color Fill)> Faces(IReadOnlyList<VolumePrism> prisms)
    {
        var faces = new List<(List<Point[]> Rings, Color Fill)>();
        // bâtiment par bâtiment, du fond vers l'avant ; dans un bâtiment, les étages de bas en haut
        var buildingDepth = prisms.GroupBy(p => p.Building).ToDictionary(g => g.Key, g => g.Average(Depth));
        foreach (var p in prisms.OrderBy(p => buildingDepth[p.Building]).ThenBy(p => p.Bottom).ThenBy(Depth))
        {
            var sides = new List<(double Depth, Point[] Pts, Color Fill)>();
            foreach (var ring in p.Rings)
            {
                for (var k = 0; k < ring.Count; k++)
                {
                    var a = ring[k];
                    var b = ring[(k + 1) % ring.Count];
                    double dx = b[0] - a[0], dy = b[1] - a[1];
                    var len = Math.Sqrt(dx * dx + dy * dy);
                    if (len < 1e-6) continue;
                    double nx = dy / len, ny = -dx / len;       // normale extérieure (anneaux orientés par le moteur)
                    if (nx + ny <= 0) continue;                  // face tournée vers l'arrière : cachée
                    var pts = new[]
                    {
                        Project(a[0], a[1], p.Bottom), Project(b[0], b[1], p.Bottom),
                        Project(b[0], b[1], p.Top), Project(a[0], a[1], p.Top),
                    };
                    // face tournée vers la droite (normale +x) plus claire que celle tournée vers la gauche (+y)
                    var light = 0.62 + 0.22 * (nx - ny + 1) / 2;
                    sides.Add(((a[0] + a[1] + b[0] + b[1]) / 2, pts, Shade(light)));
                }
            }
            faces.AddRange(sides.OrderBy(s => s.Depth).Select(s => (new List<Point[]> { s.Pts }, s.Fill)));
            faces.Add((p.Rings.Where(r => r.Count >= 3).Select(r => r.Select(v => Project(v[0], v[1], p.Top)).ToArray()).ToList(),
                       TopColor));
        }
        return faces;
    }

    protected override void OnRender(DrawingContext dc)
    {
        var w = ActualWidth;
        var h = ActualHeight;
        if (w <= 0 || h <= 0 || _prisms.Count == 0) return;
        var faces = Faces(_prisms);
        var all = faces.SelectMany(f => f.Rings).SelectMany(r => r).ToList();
        if (all.Count == 0) return;
        double minX = all.Min(q => q.X), maxX = all.Max(q => q.X), minY = all.Min(q => q.Y), maxY = all.Max(q => q.Y);
        const double margin = 6;
        var scale = Math.Min((w - 2 * margin) / Math.Max(maxX - minX, 1e-6), (h - 2 * margin) / Math.Max(maxY - minY, 1e-6));
        var ox = (w - (maxX - minX) * scale) / 2 - minX * scale;
        var oy = (h - (maxY - minY) * scale) / 2 - minY * scale;
        Point Fit(Point q) => new(q.X * scale + ox, q.Y * scale + oy);

        var edge = new Pen(new SolidColorBrush(Shade(0.5)), 0.6) { LineJoin = PenLineJoin.Miter, MiterLimit = 2 };
        edge.Freeze();
        foreach (var (rings, fill) in faces)
        {
            var geo = new StreamGeometry { FillRule = FillRule.EvenOdd };
            using (var ctx = geo.Open())
            {
                foreach (var ring in rings)
                {
                    ctx.BeginFigure(Fit(ring[0]), true, true);
                    ctx.PolyLineTo(ring.Skip(1).Select(Fit).ToList(), true, true);
                }
            }
            geo.Freeze();
            var brush = new SolidColorBrush(fill);
            brush.Freeze();
            // contour sombre sur les dessus seulement ; les côtés prennent un trait de leur couleur, pour que deux tranches
            // d'étages sur la même façade se lisent comme une façade continue
            var pen = fill == TopColor ? edge : new Pen(brush, 0.4) { LineJoin = PenLineJoin.Miter, MiterLimit = 2 };
            dc.DrawGeometry(brush, pen, geo);
        }
    }

    private static double Depth(VolumePrism p) => p.Rings.Count == 0 || p.Rings[0].Count == 0 ? 0 : p.Rings[0].Average(v => v[0] + v[1]);

    private static Color Shade(double f) => Color.FromRgb((byte)(Base.R * f), (byte)(Base.G * f), (byte)(Base.B * f));
}
