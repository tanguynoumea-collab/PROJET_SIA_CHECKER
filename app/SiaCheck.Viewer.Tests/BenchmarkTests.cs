using System.IO;
using SiaCheck.Viewer.Services;
using SiaCheck.Viewer.ViewModels;

namespace SiaCheck.Viewer.Tests;

/// <summary>Section Benchmark de l'accueil : benchmark.json du moteur, fraîcheur de la base, empreinte de fiabilité.</summary>
public class BenchmarkTests
{
    private const string Json = """
        {"version": 1, "genere": "2026-10-27T10:32:00",
         "projets": [
          {"id": "1714", "nom": "Le Clos des Hetres", "fichier": "MDP-1714.00_ Le_Clos_des_Hetres.xlsx",
           "infos": {"canton": "VD", "logements": null}, "score": 1.0, "fiable": true,
           "controles": [{"id": "brutes", "label": "Surfaces brutes (SP)", "ok": true, "detail": ""},
                         {"id": "uspi", "label": "Surfaces USPI (SVN)", "ok": true, "detail": ""}]},
          {"id": "1778", "nom": "L'Orée", "fichier": "MDP-1778-Loree.xlsx", "infos": {"canton": null}, "score": 0.4,
           "fiable": false,
           "controles": [{"id": "brutes", "label": "Surfaces brutes (SP)", "ok": true, "detail": ""},
                         {"id": "plausible", "label": "Part de construction", "ok": false, "detail": "SC / SP = 56%"}]}],
         "erreurs": ["MDP-3.xlsx : illisible"], "kpis": [], "base": {}}
        """;

    [Fact]
    public void Reads_the_engine_file()
    {
        using var tmp = new TempDir();
        var path = Path.Combine(tmp.Path, "benchmark.json");
        File.WriteAllText(path, Json);
        var data = BenchmarkBase.Load(path);
        Assert.NotNull(data);
        Assert.Equal(2, data.Projects.Count);
        Assert.Equal(new DateTime(2026, 10, 27, 10, 32, 0), data.Generated);
        Assert.Single(data.Errors);
        Assert.Equal("VD", data.Projects[0].Info("canton"));
        Assert.Null(data.Projects[1].Info("canton"));
    }

    [Fact]
    public void Corrupt_or_missing_file_reads_as_null()
    {
        using var tmp = new TempDir();
        var path = Path.Combine(tmp.Path, "benchmark.json");
        Assert.Null(BenchmarkBase.Load(path));
        File.WriteAllText(path, "{ pas du json");
        Assert.Null(BenchmarkBase.Load(path));
    }

    [Fact]
    public void Fingerprint_and_tooltip_name_the_missing_data()
    {
        var p = BenchmarkBase.Load(Write(Json))!.Projects;
        var orée = new BenchmarkItem(p[1]);
        Assert.Equal([true, false], orée.Fingerprint);
        Assert.Equal("ALERTE", orée.Verdict);
        Assert.Equal("—", orée.Canton);
        Assert.Contains("Part de construction (SC / SP = 56%)", orée.Tooltip);
        Assert.Equal("OK", new BenchmarkItem(p[0]).Verdict);
    }

    [Fact]
    public void Base_is_stale_when_an_mdp_is_newer_than_the_json()
    {
        using var tmp = new TempDir();
        var json = Path.Combine(tmp.Path, "out", "benchmark.json");
        var mdp = Path.Combine(tmp.Path, "MDP-1778-Loree.xlsx");
        File.WriteAllText(mdp, "x");
        Assert.True(BenchmarkBase.IsStale(tmp.Path, json));      // jamais lue
        Directory.CreateDirectory(Path.GetDirectoryName(json)!);
        File.WriteAllText(json, Json);
        File.SetLastWriteTime(mdp, DateTime.Now.AddMinutes(-5));
        Directory.SetLastWriteTime(tmp.Path, DateTime.Now.AddMinutes(-5));
        Assert.False(BenchmarkBase.IsStale(tmp.Path, json));
        File.SetLastWriteTime(mdp, DateTime.Now.AddMinutes(5));
        Assert.True(BenchmarkBase.IsStale(tmp.Path, json));
    }

    [Fact]
    public void Finds_the_mdp_of_a_project_id()
    {
        using var tmp = new TempDir();
        File.WriteAllText(Path.Combine(tmp.Path, "MDP-1778-Loree.xlsx"), "x");
        File.WriteAllText(Path.Combine(tmp.Path, "MDP-1467.00_Batie.xlsx"), "x");
        File.WriteAllText(Path.Combine(tmp.Path, "~$MDP-1714.xlsx"), "x");
        Assert.EndsWith("MDP-1778-Loree.xlsx", BenchmarkBase.FindById(tmp.Path, "1778"));
        Assert.EndsWith("MDP-1467.00_Batie.xlsx", BenchmarkBase.FindById(tmp.Path, "1467"));
        Assert.Null(BenchmarkBase.FindById(tmp.Path, "177"));
        Assert.Equal(2, BenchmarkBase.MdpFiles(tmp.Path).Count());
    }

    private static string Write(string json)
    {
        var path = Path.Combine(Path.GetTempPath(), $"benchmark-{Guid.NewGuid():N}.json");
        File.WriteAllText(path, json);
        return path;
    }
}
