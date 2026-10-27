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
    private const double HatchPeriod = 1.0;   // m, période des hachures en plan (plus fine : moiré en vue rasante)

    private readonly Dictionary<string, CategoryInfo> _cats;
    private readonly Dictionary<string, Brush> _brushes = [];

    public SiaPalette(IEnumerable<CategoryInfo> categories) =>
        _cats = categories.ToDictionary(c => c.Code, StringComparer.Ordinal);

    /// <summary>
    /// Codes que l'analyse ouverte peut ne pas lister (aucune surface encore, ou analyse antérieure) : mêmes couleurs que
    /// report.SIA_COLORS, aplat plein. SA : abords créés par les découpes ; SUT : catégorie Treegram comptée dans la SU.
    /// </summary>
    private static readonly Dictionary<string, (Color Color, string Name, string Ref)> Defaults = new(StringComparer.Ordinal)
    {
        ["SA"] = (Color.FromRgb(0x5B, 0xA8, 0x45), "Surface des abords", "SIA 416 §1.2"),
        ["SUT"] = (Color.FromRgb(0xE8, 0x60, 0x1C), "Surface utile hors logement (catégorie Treegram)", "règle personnalisée P1"),
    };

    public Color ColorOf(string code) =>
        _cats.TryGetValue(code, out var c) && c.Color is { } hex ? (Color)ColorConverter.ConvertFromString(hex)
        : Defaults.TryGetValue(code, out var d) ? d.Color
        : Fallback;

    public bool IsHatched(string code) =>
        _cats.TryGetValue(code, out var c) ? !IsEnvelope(code) && (c.Hatched || c.Status != "checked") : !Defaults.ContainsKey(code);

    /// <summary>Façades et vitrages (SFN, SRV) : surfaces verticales, hors sommes, rendues translucides (Évolution 3.6).</summary>
    public bool IsEnvelope(string code) => _cats.TryGetValue(code, out var c) && c.Family == "enveloppe";

    public CategoryInfo? Info(string code) => _cats.GetValueOrDefault(code);

    /// <summary>« SUP · Surface utile principale (SIA 416 §2.1.1.1) » + définition, pour les infobulles.</summary>
    public (string Title, string? Definition) Describe(string code)
    {
        var c = Info(code);
        var d = Defaults.GetValueOrDefault(code);
        var title = (c?.Name ?? d.Name) is { } n ? $"{code} · {n}" : code;
        if ((c?.Ref ?? d.Ref) is { } r) title += $" ({r})";
        return (title, c?.Definition);
    }

    /// <summary>Pinceau 2D (calques, bilan) : aplat, ou hachures pour les surfaces externes et les codes non contrôlés.</summary>
    public Brush BrushOf(string code)
    {
        if (_brushes.TryGetValue(code, out var b)) return b;
        b = IsHatched(code) ? Hatch(ColorOf(code), Tint(ColorOf(code), 0.25), BrushMappingMode.Absolute, 6) : new SolidColorBrush(ColorOf(code));
        b.Freeze();
        return _brushes[code] = b;
    }

    /// <summary>Teinte assombrie (facteur &lt; 1) : chants des dalles 3D.</summary>
    public static Color Shade(Color c, double factor) =>
        Color.FromRgb((byte)(c.R * factor), (byte)(c.G * factor), (byte)(c.B * factor));

    /// <summary>Teinte éclaircie vers le blanc (part de couleur conservée) : fond opaque des hachures.</summary>
    public static Color Tint(Color c, double keep) =>
        Color.FromRgb((byte)(255 - (255 - c.R) * keep), (byte)(255 - (255 - c.G) * keep), (byte)(255 - (255 - c.B) * keep));

    /// <summary>
    /// Hachures diagonales opaques : fond clair + traits de la couleur. En 3D, les coordonnées de texture
    /// sont les coordonnées en plan divisées par la période (SceneController) : motif à l'échelle du bâtiment,
    /// et pas de transparence qui mélangerait les niveaux superposés.
    /// </summary>
    public static DrawingBrush Hatch(Color stroke, Color background, BrushMappingMode units, double period)
    {
        var group = new DrawingGroup();
        group.Children.Add(new GeometryDrawing(new SolidColorBrush(background), null, new RectangleGeometry(new Rect(0, 0, 1, 1))));
        group.Children.Add(new GeometryDrawing(null, new Pen(new SolidColorBrush(stroke), 0.28),
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
