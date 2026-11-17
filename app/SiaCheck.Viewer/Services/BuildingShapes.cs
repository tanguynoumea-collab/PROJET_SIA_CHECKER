using System.Globalization;
using System.Text;

namespace SiaCheck.Viewer.Services;

/// <summary>
/// Forme des bâtiments d'un projet (docs/V5_PLAN.md, partie 5), comme le moteur (src/sia_check/formes.py) : une forme
/// par bâtiment, écrite dans le champ « Forme » du MDP. Un bâtiment seul : la forme seule (« Rectangle compact ») ;
/// plusieurs : « A : Carré ; B : Rectangle compact ». « Forme (origine) » vaut « saisie » ou « IA ».
/// </summary>
public static class BuildingShapes
{
    /// <summary>Copie de la liste du moteur, utilisée tant que la base n'a pas été lue (benchmark.json, <c>listes.Forme</c>).</summary>
    public static IReadOnlyList<string> Default { get; } =
        ["Carré", "Rectangle compact", "Barre", "En L", "En T", "En U", "Cour fermée / îlot", "À redans / en Z",
         "En peigne / en H", "Rond / ovale", "Courbe / arc", "Plusieurs plots", "Irrégulière"];

    public const string Manual = "saisie", Ai = "IA", Ilot = "Îlot de bâtiments";

    /// <summary>La forme de la liste qui correspond (casse, espaces et accents tolérés), ou null.</summary>
    public static string? Normalize(string? shape, IReadOnlyList<string>? list = null) =>
        string.IsNullOrWhiteSpace(shape) ? null : (list ?? Default).FirstOrDefault(f => Key(f) == Key(shape));

    /// <summary>{bâtiment: forme} ; bâtiment « » pour une forme sans bâtiment nommé.</summary>
    public static Dictionary<string, string> Decode(string? text)
    {
        var shapes = new Dictionary<string, string>(StringComparer.Ordinal);
        foreach (var part in (text ?? "").Split(';', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries))
        {
            var i = part.LastIndexOf(':');
            var building = i < 0 ? "" : part[..i].Trim();
            if (Normalize(i < 0 ? part : part[(i + 1)..]) is { } f) shapes[building] = f;
        }
        return shapes;
    }

    /// <summary>Texte du MDP ; un seul bâtiment : la forme seule.</summary>
    public static string Encode(IReadOnlyDictionary<string, string> shapes)
    {
        var clean = shapes.Where(kv => Normalize(kv.Value) is not null)
                          .ToDictionary(kv => kv.Key.Trim(), kv => Normalize(kv.Value)!, StringComparer.Ordinal);
        return clean.Count switch
        {
            0 => "",
            1 => clean.Values.First(),
            _ => string.Join(" ; ", clean.OrderBy(kv => kv.Key, StringComparer.Ordinal).Select(kv => $"{kv.Key} : {kv.Value}")),
        };
    }

    /// <summary>« Rectangle compact », ou « Îlot de bâtiments : Carré, Rectangle compact ».</summary>
    public static string Label(IReadOnlyDictionary<string, string> shapes)
    {
        if (shapes.Count == 0) return "";
        if (shapes.Count == 1) return shapes.Values.First();
        var order = Default.ToList();
        return $"{Ilot} : {string.Join(", ", shapes.Values.Distinct().OrderBy(order.IndexOf))}";
    }

    /// <summary>Même forme par bâtiment, l'ordre des bâtiments et un bâtiment « » seul mis à part.</summary>
    public static bool Same(string? a, string? b)
    {
        var x = Decode(a);
        var y = Decode(b);
        return x.Count == y.Count && x.All(kv => y.TryGetValue(kv.Key, out var v) && v == kv.Value)
               || x.Count == 1 && y.Count == 1 && x.Values.First() == y.Values.First();
    }

    private static string Key(string s)
    {
        var d = s.Trim().ToLowerInvariant().Normalize(NormalizationForm.FormD);
        var sb = new StringBuilder();
        foreach (var c in d)
            if (CharUnicodeInfo.GetUnicodeCategory(c) != UnicodeCategory.NonSpacingMark) sb.Append(c);
        return string.Join(' ', sb.ToString().Split(' ', StringSplitOptions.RemoveEmptyEntries));
    }
}
