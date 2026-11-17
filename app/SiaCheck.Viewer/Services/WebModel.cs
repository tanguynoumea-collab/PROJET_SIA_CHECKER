using System.IO;
using System.IO.Compression;
using System.Text.Json;
using System.Text.RegularExpressions;
using SiaCheck.Viewer.Models;
using SiaCheck.Viewer.Scene;

namespace SiaCheck.Viewer.Services;

/// <summary>
/// Maquette 3D web d'un projet (docs/V5_PLAN.md, partie 2) : les surfaces de la dernière analyse, allégées pour le
/// dashboard. Un fichier <c>MAQ-&lt;id&gt;.json.gz</c> à côté du MDP, dans le dossier de la base.
///
/// Format (version 1), JSON compressé en gzip :
/// <code>
/// { "format": "sia-check-maquette", "version": 1, "id", "projet", "date", "unite": 0.01,
///   "origine": [x, y, z],                      // m, retirée de toutes les coordonnées
///   "categories": [{ "code", "titre", "definition", "couleur", "groupe", "visible", "hachure", "enveloppe", "n", "m2" }],
///   "niveaux":    [{ "b", "l", "rang" }],
///   "surfaces":   [{ "code", "b", "l", "m2", "nom", "lot" }],
///   "lots":       [{ "b", "l", "code", "v": [x, y, z, …] en cm entiers, "i": [a, b, c, …],
///                    "s": [indice de surface, …], "t": [premier triangle de chaque surface, …] }] }
/// </code>
/// Mêmes surfaces que la visionneuse : sans les totaux doublés par leurs pièces, chaque surface à îlots remplacée par
/// ses îlots, sans les surfaces exclues par une correction. Un lot regroupe une catégorie d'un niveau.
/// </summary>
public static partial class WebModel
{
    public const string Format = "sia-check-maquette";
    public const int Version = 1;
    private const double Unit = 0.01;   // m : coordonnées en centimètres entiers

    public static string FileName(string id) => $"MAQ-{id.Trim()}.json.gz";

    /// <summary>Nom de fichier accepté par le dashboard (rien d'autre n'est servi depuis le dossier de la base).</summary>
    public static bool IsModelFile(string name) => ModelName().IsMatch(name);

    [GeneratedRegex(@"^MAQ-[\w.-]+\.json\.gz$")]
    private static partial Regex ModelName();

    /// <summary>Écrit la maquette (fichier temporaire puis remplacement : un lecteur ne voit jamais un fichier à moitié écrit).</summary>
    public static void Write(ViewerDocument doc, string id, string path)
    {
        var tmp = path + ".tmp";
        try
        {
            using (var file = File.Create(tmp))
            using (var gz = new GZipStream(file, CompressionLevel.SmallestSize))
            using (var w = new Utf8JsonWriter(gz))
                WriteJson(doc, id, w);
            File.Move(tmp, path, overwrite: true);
        }
        finally
        {
            if (File.Exists(tmp)) File.Delete(tmp);
        }
    }

    public static void WriteJson(ViewerDocument doc, string id, Utf8JsonWriter w)
    {
        var palette = new SiaPalette(doc.Categories);
        var surfaces = doc.DisplaySurfaces
            .Where(s => s is { Mesh.Vertices.Length: >= 9, Mesh.Indices.Length: >= 3, Building: not null, Level: not null } && !s.IsExcluded)
            .DistinctBy(s => s.Id)      // comme la scène 3D : une surface par identifiant
            .ToList();
        double minX = double.MaxValue, minY = double.MaxValue, minZ = double.MaxValue;
        foreach (var s in surfaces)
            for (var k = 0; k + 2 < s.Mesh!.Vertices.Length; k += 3)
            {
                minX = Math.Min(minX, s.Mesh.Vertices[k]);
                minY = Math.Min(minY, s.Mesh.Vertices[k + 1]);
                minZ = Math.Min(minZ, s.Mesh.Vertices[k + 2]);
            }
        if (surfaces.Count == 0) minX = minY = minZ = 0;

        w.WriteStartObject();
        w.WriteString("format", Format);
        w.WriteNumber("version", Version);
        w.WriteString("id", id.Trim());
        w.WriteString("projet", doc.Project);
        w.WriteString("date", doc.Date);
        w.WriteNumber("unite", Unit);
        w.WriteStartArray("origine");
        w.WriteNumberValue(Math.Round(minX, 3)); w.WriteNumberValue(Math.Round(minY, 3)); w.WriteNumberValue(Math.Round(minZ, 3));
        w.WriteEndArray();

        // Calques : même règle que l'onglet Calques (groupe, visibilité d'emblée, surfaces comptées)
        var codes = surfaces.Select(s => s.DisplayCode).ToHashSet(StringComparer.Ordinal);
        w.WriteStartArray("categories");
        foreach (var cat in doc.Categories.Where(c => codes.Contains(c.Code)))
        {
            var counted = LayerRules.Counted(doc, cat.Code);
            var group = LayerRules.Group(cat);
            var (title, definition) = palette.Describe(cat.Code);
            var c = palette.ColorOf(cat.Code);
            w.WriteStartObject();
            w.WriteString("code", cat.Code);
            w.WriteString("titre", title);
            if (definition is not null) w.WriteString("definition", definition);
            w.WriteString("couleur", $"#{c.R:X2}{c.G:X2}{c.B:X2}");
            w.WriteString("groupe", group);
            w.WriteBoolean("visible", LayerRules.VisibleByDefault(group, cat.Code));
            w.WriteBoolean("hachure", palette.IsHatched(cat.Code));
            w.WriteBoolean("enveloppe", palette.IsEnvelope(cat.Code));
            w.WriteNumber("n", counted.Count);
            w.WriteNumber("m2", Math.Round(counted.Sum(s => s.Area ?? 0), 1));
            w.WriteEndObject();
        }
        w.WriteEndArray();

        w.WriteStartArray("niveaux");
        foreach (var l in doc.Levels.Where(l => surfaces.Any(s => s.Building == l.Building && s.Level == l.Level))
                                    .OrderBy(l => l.Building, StringComparer.Ordinal).ThenBy(l => l.Rank ?? 0))
        {
            w.WriteStartObject();
            w.WriteString("b", l.Building);
            w.WriteString("l", l.Level);
            w.WriteNumber("rang", l.Rank ?? 0);
            w.WriteEndObject();
        }
        w.WriteEndArray();

        w.WriteStartArray("surfaces");
        foreach (var s in surfaces)
        {
            w.WriteStartObject();
            w.WriteString("code", s.DisplayCode);
            w.WriteString("b", s.Building);
            w.WriteString("l", s.Level);
            if (s.Area is double a) w.WriteNumber("m2", Math.Round(a, 1));
            if (!string.IsNullOrWhiteSpace(s.RoomType)) w.WriteString("nom", s.RoomType);
            if (!string.IsNullOrWhiteSpace(s.Lot)) w.WriteString("lot", s.Lot);
            w.WriteEndObject();
        }
        w.WriteEndArray();

        // Lots : une catégorie d'un niveau, sommets en cm depuis l'origine, table triangle → surface pour la sélection
        // par position dans « surfaces » : une même surface peut y figurer deux fois (doublon de la source)
        w.WriteStartArray("lots");
        foreach (var groupe in surfaces.Select((s, k) => (s, k)).GroupBy(x => (x.s.Building!, x.s.Level!, x.s.DisplayCode)).OrderBy(g => g.Key))
        {
            var lot = groupe.Select(x => x.s).ToList();
            var indices = groupe.Select(x => x.k).ToList();
            w.WriteStartObject();
            w.WriteString("b", groupe.Key.Item1);
            w.WriteString("l", groupe.Key.Item2);
            w.WriteString("code", groupe.Key.Item3);
            w.WriteStartArray("v");
            foreach (var s in lot)
                for (var k = 0; k + 2 < s.Mesh!.Vertices.Length; k += 3)
                {
                    w.WriteNumberValue((long)Math.Round((s.Mesh.Vertices[k] - minX) / Unit));
                    w.WriteNumberValue((long)Math.Round((s.Mesh.Vertices[k + 1] - minY) / Unit));
                    w.WriteNumberValue((long)Math.Round((s.Mesh.Vertices[k + 2] - minZ) / Unit));
                }
            w.WriteEndArray();
            w.WriteStartArray("i");
            var offset = 0;
            foreach (var s in lot)
            {
                foreach (var i in s.Mesh!.Indices) w.WriteNumberValue(i + offset);
                offset += s.Mesh.Vertices.Length / 3;
            }
            w.WriteEndArray();
            w.WriteStartArray("s");
            foreach (var k in indices) w.WriteNumberValue(k);
            w.WriteEndArray();
            w.WriteStartArray("t");
            var triangle = 0;
            foreach (var s in lot)
            {
                w.WriteNumberValue(triangle);
                triangle += s.Mesh!.Indices.Length / 3;
            }
            w.WriteEndArray();
            w.WriteEndObject();
        }
        w.WriteEndArray();
        w.WriteEndObject();
    }
}
