using System.IO;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace SiaCheck.Viewer.Services;

/// <summary>
/// Version HTML autonome du benchmark (docs/V6_PLAN.md, partie 2) : la page du dashboard, ses scripts, ses bibliothèques,
/// le fond de carte, benchmark.json et les maquettes 3D réunis dans un seul fichier, à déposer dans SharePoint. Ouvert en
/// local (file://), le navigateur n'y permet ni fetch ni module chargé depuis un fichier : tout est intégré.
///
/// Les fichiers de données vont dans des blocs <c>&lt;script type="application/…" data-fichier="nom"&gt;</c> que la page
/// lit (app.js, fichierIntegre) ; les modules de l'import map (three, three/orbit, sia/vue3d) deviennent des URL data:.
/// Seules les maquettes annoncées par benchmark.json sont intégrées, avec le filtre de nom de <see cref="WebModel"/>.
/// </summary>
public static partial class StandaloneDashboard
{
    public const string DefaultFileName = "SIA Check - Benchmark.html";

    /// <summary><c>Written</c> : false si la version en place était déjà celle-ci (même empreinte).</summary>
    public sealed record Result(int Projects, int Models, long Bytes, bool Written = true);

    /// <summary>
    /// Assemble la page et l'écrit dans <paramref name="output"/> (fichier temporaire puis remplacement : OneDrive ne
    /// synchronise jamais une version à moitié écrite). Une version en place de même empreinte (mêmes données, mêmes
    /// maquettes, même page) n'est pas réécrite : chaque utilisateur de l'app peut republier sans faire tourner la synchro.
    /// <paramref name="version"/> : groupe d'utilisateurs de la version (V6), affiché par la page ; null hors publication.
    /// </summary>
    public static Result Export(string dashboardDir, string benchmarkFile, string modelsDir, string output, string? version = null)
    {
        var (html, projects, models) = Build(dashboardDir, File.ReadAllText(benchmarkFile, Encoding.UTF8), modelsDir, version);
        if (File.Exists(output) && ReadFingerprint(output) is { } old && old == Fingerprint().Match(html).Groups[1].Value)
            return new Result(projects, models, new FileInfo(output).Length, Written: false);
        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(output))!);
        var tmp = output + ".tmp";
        File.WriteAllText(tmp, html, new UTF8Encoding(false));
        File.Move(tmp, output, overwrite: true);
        return new Result(projects, models, new FileInfo(output).Length);
    }

    /// <summary>Empreinte d'une version en place (balise sia-empreinte de l'en-tête), ou null.</summary>
    internal static string? ReadFingerprint(string path)
    {
        try
        {
            using var reader = new StreamReader(path, Encoding.UTF8);
            var head = new char[4096];
            var n = reader.ReadBlock(head, 0, head.Length);
            var m = Fingerprint().Match(new string(head, 0, n));
            return m.Success ? m.Groups[1].Value : null;
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            return null;
        }
    }

    /// <summary>
    /// Une version vide (aucun projet dans le groupe) est assemblée aussi : la page le dit, et la version précédente ne
    /// garde pas des projets retirés du groupe.
    /// </summary>
    internal static (string Html, int Projects, int Models) Build(string dashboardDir, string benchmarkJson, string modelsDir,
                                                                 string? version = null)
    {
        string Read(string relative) => File.ReadAllText(Path.Combine(dashboardDir, relative), Encoding.UTF8);
        string DataUrl(string relative) =>
            "data:text/javascript;base64," + Convert.ToBase64String(File.ReadAllBytes(Path.Combine(dashboardDir, relative)));

        var (projects, modelNames) = Inventory(benchmarkJson);
        var blocks = new StringBuilder();
        blocks.Append(JsonBlock("benchmark.json", benchmarkJson));
        blocks.Append(JsonBlock("carte-suisse.json", Read("carte-suisse.json")));
        var models = 0;
        foreach (var name in modelNames)
        {
            var path = Path.Combine(modelsDir, name);
            if (!File.Exists(path)) continue;     // la page retire l'icône cube d'une maquette absente
            blocks.Append($"  <script type=\"application/octet-stream\" data-fichier=\"{name}\">")
                  .Append(Convert.ToBase64String(File.ReadAllBytes(path))).Append("</script>\n");
            models++;
        }

        var html = Read("index.html");
        // repère de la version autonome, lu par le script d'en-tête d'index.html : page de garde et thème du poste ;
        // version (groupe d'utilisateurs) affichée par l'accueil
        var meta = "\n  <meta name=\"sia-autonome\" content=\"1\">" + (string.IsNullOrWhiteSpace(version) ? ""
            : $"\n  <meta name=\"sia-version\" content=\"{System.Net.WebUtility.HtmlEncode(version.Trim())}\">");
        html = Replace(html, MetaCharset(), m => m.Value + meta);
        html = Replace(html, StyleLink(), _ => $"<style>{Css(Read("style.css"))}</style>\n  <style>{Css(Read("vendor/leaflet/leaflet.css"))}</style>");
        var imports = new Dictionary<string, string>
        {
            ["three"] = DataUrl("vendor/three.module.min.js"),
            ["three/orbit"] = DataUrl("vendor/OrbitControls.js"),
            ["sia/vue3d"] = DataUrl("vue3d.js"),
        };
        html = Replace(html, ImportMap(), _ => $"<script type=\"importmap\">{JsonSerializer.Serialize(new { imports })}</script>");
        // xlsx.js était différé (defer) : il passe après carte.js ; Leaflet est déjà là quand la carte s'ouvre
        html = Replace(html, XlsxScript(), _ => "");
        html = Replace(html, AppScript(), _ =>
            blocks + $"  <script>{Js(Read("vendor/leaflet/leaflet.js"))}</script>\n  <script>{Js(Read("app.js"))}</script>");
        html = Replace(html, CarteScript(), _ => $"<script>{Js(Read("carte.js"))}</script>\n  <script>{Js(Read("xlsx.js"))}</script>");

        var local = LocalReference().Match(html);
        if (local.Success) throw new InvalidDataException($"page du dashboard : référence locale non intégrée ({local.Value}).");
        // empreinte : tout le contenu, sauf l'heure de lecture de la base (« genere »), qui change à chaque relecture
        var hash = Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(Encoding.UTF8.GetBytes(Generated().Replace(html, ""))))
                          .ToLowerInvariant();
        html = Replace(html, MetaCharset(), m => m.Value + $"\n  <meta name=\"sia-empreinte\" content=\"{hash}\">");
        return (html, projects, models);
    }

    /// <summary>Nombre de projets et maquettes annoncées (champ « maquette » de chaque projet).</summary>
    private static (int Projects, List<string> Models) Inventory(string benchmarkJson)
    {
        using var doc = JsonDocument.Parse(benchmarkJson);
        if (!doc.RootElement.TryGetProperty("projets", out var list) || list.ValueKind != JsonValueKind.Array)
            throw new InvalidDataException("la base n'a pas été lue correctement : relisez-la avant de publier.");
        var models = list.EnumerateArray()
            .Select(p => p.TryGetProperty("maquette", out var m) && m.ValueKind == JsonValueKind.String ? m.GetString()! : null)
            .OfType<string>().Where(WebModel.IsModelFile).Distinct(StringComparer.OrdinalIgnoreCase).ToList();
        return (list.GetArrayLength(), models);
    }

    private static string JsonBlock(string name, string json) =>
        $"  <script type=\"application/json\" data-fichier=\"{name}\">{json.Replace("</", "<\\/")}</script>\n";

    /// <summary>Script en ligne : seule la fin de balise est neutralisée (remplacer « &lt;/ » partout casserait le code).</summary>
    internal static string Js(string code) => ScriptEnd().Replace(code, "<\\/$1");

    private static string Css(string css) => css.Replace("</style", "<\\/style", StringComparison.OrdinalIgnoreCase);

    /// <summary>Un seul remplacement attendu : une page du dashboard différente arrête l'export plutôt que de produire une page cassée.</summary>
    private static string Replace(string html, Regex pattern, MatchEvaluator by)
    {
        if (pattern.Count(html) != 1) throw new InvalidDataException($"page du dashboard inattendue ({pattern}) : réinstallez l'application.");
        return pattern.Replace(html, by, 1);
    }

    [GeneratedRegex(@"<meta charset=""utf-8"">")] private static partial Regex MetaCharset();
    [GeneratedRegex(@"<meta name=""sia-empreinte"" content=""([0-9a-f]+)"">")] private static partial Regex Fingerprint();
    [GeneratedRegex(@"""genere"":\s*""[^""]*""")] private static partial Regex Generated();
    [GeneratedRegex(@"<link rel=""stylesheet"" href=""style\.css[^""]*"">")] private static partial Regex StyleLink();
    [GeneratedRegex(@"<script type=""importmap"">.*?</script>", RegexOptions.Singleline)] private static partial Regex ImportMap();
    [GeneratedRegex(@"[ \t]*<script src=""xlsx\.js[^""]*"" defer></script>\r?\n")] private static partial Regex XlsxScript();
    [GeneratedRegex(@"<script src=""app\.js[^""]*""></script>")] private static partial Regex AppScript();
    [GeneratedRegex(@"<script src=""carte\.js[^""]*""></script>")] private static partial Regex CarteScript();
    [GeneratedRegex(@"</(script)", RegexOptions.IgnoreCase)] private static partial Regex ScriptEnd();
    [GeneratedRegex(@"<(?:script|link|img)\b[^>]*\b(?:src|href)=""(?!data:|https?:)[^""]*""", RegexOptions.IgnoreCase)] private static partial Regex LocalReference();
}
