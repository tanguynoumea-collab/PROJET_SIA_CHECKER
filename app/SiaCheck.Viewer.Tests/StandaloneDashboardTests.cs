using System.IO;
using System.Text.RegularExpressions;
using SiaCheck.Viewer.Services;

namespace SiaCheck.Viewer.Tests;

/// <summary>Version HTML autonome du benchmark (docs/V6_PLAN.md, partie 2), assemblée depuis la vraie page dashboard/.</summary>
public class StandaloneDashboardTests
{
    /// <summary>dashboard/ du dépôt, trouvé en remontant depuis le dossier des tests.</summary>
    private static string DashboardDir()
    {
        for (var d = new DirectoryInfo(AppContext.BaseDirectory); d is not null; d = d.Parent)
        {
            var candidate = Path.Combine(d.FullName, "dashboard");
            if (File.Exists(Path.Combine(candidate, "index.html")) && File.Exists(Path.Combine(candidate, "app.js"))) return candidate;
        }
        throw new DirectoryNotFoundException("dashboard/ introuvable");
    }

    private const string Base = """{"genere":"2026-11-18T08:00:00","projets":[{"id":"1","nom":"A </script> B","maquette":"MAQ-1.json.gz"},""" +
                                """{"id":"2","maquette":"MAQ-2.json.gz"},{"id":"3","maquette":"../MAQ-3.json.gz"},{"id":"4","maquette":null}]}""";

    [Fact]
    public void Inlines_everything_and_only_the_announced_models_found_in_the_base()
    {
        using var dir = new TempDir();
        File.WriteAllBytes(Path.Combine(dir.Path, "MAQ-1.json.gz"), [0x1f, 0x8b, 1, 2, 3]);
        File.WriteAllBytes(Path.Combine(dir.Path, "MAQ-9.json.gz"), [0x1f, 0x8b, 9]);     // pas annoncée : non intégrée

        var (html, projects, models) = StandaloneDashboard.Build(DashboardDir(), Base, dir.Path);

        Assert.Equal(4, projects);
        Assert.Equal(1, models);
        Assert.Contains("data-fichier=\"benchmark.json\"", html);
        Assert.Contains("data-fichier=\"carte-suisse.json\"", html);
        Assert.Contains($"data-fichier=\"MAQ-1.json.gz\">{Convert.ToBase64String(new byte[] { 0x1f, 0x8b, 1, 2, 3 })}</script>", html);
        Assert.DoesNotContain("MAQ-9", html);
        Assert.DoesNotContain("data-fichier=\"MAQ-2.json.gz\"", html);
        Assert.Contains("A <\\/script> B", html);                       // le JSON ne ferme pas son bloc
        Assert.DoesNotMatch(new Regex("<(script|link)\\b[^>]*(src|href)=\"(?!data:|https?:)"), html);
        Assert.Contains("\"sia/vue3d\":\"data:text/javascript;base64,", html);
        Assert.Contains("a JS library for interactive maps", html);
        Assert.True(html.IndexOf("<meta name=\"sia-autonome\"", StringComparison.Ordinal) < html.IndexOf("mode-garde", StringComparison.Ordinal),
                    "le repère précède le script d'en-tête qui le lit");                            // Leaflet intégré
        Assert.True(html.IndexOf("data-fichier=\"benchmark.json\"", StringComparison.Ordinal) < html.IndexOf("const PARAMS", StringComparison.Ordinal),
                    "les données précèdent app.js");
    }

    [Fact]
    public void Export_replaces_the_file_without_leaving_a_temporary()
    {
        using var dir = new TempDir();
        var bench = Path.Combine(dir.Path, "benchmark.json");
        File.WriteAllText(bench, Base);
        var output = Path.Combine(dir.Path, StandaloneDashboard.DefaultFileName);
        File.WriteAllText(output, "ancienne version");

        var r = StandaloneDashboard.Export(DashboardDir(), bench, dir.Path, output);

        Assert.Equal(new FileInfo(output).Length, r.Bytes);
        Assert.StartsWith("<!doctype html>", File.ReadAllText(output));
        Assert.False(File.Exists(output + ".tmp"));
    }

    [Fact]
    public void Builds_an_empty_version_but_refuses_an_unread_base()
    {
        using var dir = new TempDir();
        var (html, projects, _) = StandaloneDashboard.Build(DashboardDir(), """{"projets":[]}""", dir.Path, "Light");
        Assert.Equal(0, projects);
        Assert.Contains("<meta name=\"sia-version\" content=\"Light\">", html);
        Assert.Throws<InvalidDataException>(() => StandaloneDashboard.Build(DashboardDir(), "{}", dir.Path));
    }

    [Fact]
    public void Same_content_is_not_rewritten_but_a_change_is()
    {
        using var dir = new TempDir();
        var bench = Path.Combine(dir.Path, "benchmark.json");
        var output = Path.Combine(dir.Path, "Benchmark Light", StandaloneDashboard.DefaultFileName);
        File.WriteAllText(bench, Base);
        Assert.True(StandaloneDashboard.Export(DashboardDir(), bench, dir.Path, output, "Light").Written);     // dossier créé
        // relecture de la base : seule l'heure « genere » change, la version en place reste
        File.WriteAllText(bench, Base.Replace("2026-11-18T08:00:00", "2026-11-19T09:30:00"));
        Assert.False(StandaloneDashboard.Export(DashboardDir(), bench, dir.Path, output, "Light").Written);
        // un projet retiré du groupe : la version est réécrite
        File.WriteAllText(bench, Base.Replace("""{"id":"2","maquette":"MAQ-2.json.gz"},""", ""));
        Assert.True(StandaloneDashboard.Export(DashboardDir(), bench, dir.Path, output, "Light").Written);
        Assert.DoesNotContain("MAQ-2.json.gz", File.ReadAllText(output));
        Assert.NotNull(StandaloneDashboard.ReadFingerprint(output));
    }

    [Fact]
    public void Publication_folders_sit_next_to_the_base()
    {
        var folder = ViewModels.MainViewModel.PublicationFolder(@"C:\Sync\DEV DET\Base\", "Light");
        Assert.Equal(@"C:\Sync\DEV DET\Benchmark Light", folder);
    }

    [Theory]
    [InlineData("x = '</script>';", "x = '<\\/script>';")]
    [InlineData("if (a </b) {}", "if (a </b) {}")]      // seule la fin de balise est neutralisée
    [InlineData("'</SCRIPT'", "'<\\/SCRIPT'")]
    public void Neutralises_only_script_end_tags(string code, string expected) => Assert.Equal(expected, StandaloneDashboard.Js(code));
}
