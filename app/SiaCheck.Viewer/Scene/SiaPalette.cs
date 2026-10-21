using System.Windows;
using System.Windows.Media;
using SiaCheck.Viewer.Models;

namespace SiaCheck.Viewer.Scene;

/// <summary>
/// Couleurs de contenu (légende SIA 416). La source est le JSON du moteur (categories[].color),
/// pour qu'une seule table de couleurs existe ; le gris sert aux codes ignorés ou inconnus.
/// </summary>
public sealed class SiaPalette
{
    public static readonly Color Fallback = Color.FromRgb(0x6B, 0x72, 0x80);
    private const double HatchPeriod = 0.6;   // m, période des hachures en plan

    private readonly Dictionary<string, CategoryInfo> _cats;
    private readonly Dictionary<string, Brush> _brushes = [];

    public SiaPalette(IEnumerable<CategoryInfo> categories) =>
        _cats = categories.ToDictionary(c => c.Code, StringComparer.Ordinal);

    public Color ColorOf(string code) =>
        _cats.TryGetValue(code, out var c) && c.Color is { } hex ? (Color)ColorConverter.ConvertFromString(hex) : Fallback;

    public bool IsHatched(string code) =>
        _cats.TryGetValue(code, out var c) ? c.Hatched || c.Status != "checked" : true;

    /// <summary>Pinceau 2D (calques, bilan) : aplat, ou hachures pour les surfaces externes et les codes non contrôlés.</summary>
    public Brush BrushOf(string code)
    {
        if (_brushes.TryGetValue(code, out var b)) return b;
        b = IsHatched(code) ? Hatch(ColorOf(code), 0.25, BrushMappingMode.Absolute, 6) : new SolidColorBrush(ColorOf(code));
        b.Freeze();
        return _brushes[code] = b;
    }

    /// <summary>
    /// Hachures diagonales : fond teinté + traits pleins. En 3D, les coordonnées de texture sont
    /// les coordonnées en plan divisées par la période (SceneController), d'où un motif à l'échelle du bâtiment.
    /// </summary>
    public static DrawingBrush Hatch(Color color, double backgroundAlpha, BrushMappingMode units, double period)
    {
        var bg = Color.FromArgb((byte)(255 * backgroundAlpha), color.R, color.G, color.B);
        var group = new DrawingGroup();
        group.Children.Add(new GeometryDrawing(new SolidColorBrush(bg), null, new RectangleGeometry(new Rect(0, 0, 1, 1))));
        group.Children.Add(new GeometryDrawing(null, new Pen(new SolidColorBrush(color), 0.22),
            new PathGeometry(PathFigureCollection.Parse("M -0.5,0.5 L 0.5,-0.5 M 0,1 L 1,0 M 0.5,1.5 L 1.5,0.5"))));
        return new DrawingBrush(group)
        {
            TileMode = TileMode.Tile,
            Viewport = units == BrushMappingMode.Absolute ? new Rect(0, 0, period, period) : new Rect(0, 0, 1, 1),
            ViewportUnits = units,
            Viewbox = new Rect(0, 0, 1, 1),
            ViewboxUnits = BrushMappingMode.Absolute,
            Stretch = Stretch.Fill,
        };
    }

    public static double HatchTexturePeriod => HatchPeriod;
}
