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
    public void Fingerprint_and_detail_page_name_the_missing_data()
    {
        var p = BenchmarkBase.Load(Write(Json))!.Projects;
        var orée = new BenchmarkItem(p[1]);
        Assert.Equal([true, false], orée.Fingerprint);
        Assert.False(orée.IsReliable);
        Assert.Equal("—", orée.Canton);
        Assert.True(new BenchmarkItem(p[0]).IsReliable);

        var page = new MdpDetail(orée);
        Assert.Equal("1778 · L'Orée", page.Title);
        Assert.StartsWith("Écarté des références : part de construction SC / SP = 56%", page.Status);
        // identité d'abord, à remplir en priorité : typologie, canton, intervention manquent (commune, phase facultatives)
        Assert.Equal(3, page.IdentityMissing);
        Assert.Contains("à remplir en priorité (3 champs manquants)", page.IdentityHeader);
        Assert.Equal(("Canton", "à renseigner", "ERREUR"), (page.Identity[3].Label, page.Identity[3].Value, page.Identity[3].Verdict));
        Assert.Equal("ALERTE", page.Identity[5].Verdict);                     // commune facultative
        // puis les données : le contrôle requis manquant, avec son détail et sa conséquence
        var sc = page.Data.Single(d => !d.Ok);
        Assert.Equal(("SC / SP = 56%", "ERREUR"), (sc.Value, sc.Verdict));
        Assert.Contains("écarté des références", sc.Note);
    }

    private static BenchmarkProject Rejected(params (string Id, bool Ok, string Detail)[] checks) => new()
    {
        Id = "1", Checks = checks.Select(c => new BenchmarkCheck
        {
            Id = c.Id, Ok = c.Ok, Detail = c.Detail,
            Label = c.Id == "plausible" ? "Part de construction SC / SP entre 8% et 30%" : c.Id,
        }).ToList(),
    };

    [Fact]
    public void Reject_reason_names_the_real_cause()
    {
        Assert.Contains("pas de surfaces brutes",
            BenchmarkItem.RejectReason(Rejected(("brutes", false, ""), ("nettes", true, ""), ("coherence", false, ""), ("plausible", false, ""))));
        Assert.Contains("SP est inférieure à la SN (SP 900 < SN 950 m²)",
            BenchmarkItem.RejectReason(Rejected(("brutes", true, ""), ("nettes", true, ""), ("coherence", false, "SP 900 < SN 950 m²"))));
        var haut = BenchmarkItem.RejectReason(Rejected(("coherence", true, ""), ("plausible", false, "SC / SP = 56%")));
        Assert.Equal("part de construction SC / SP = 56%, attendue entre 8% et 30% : trop de construction, il manque probablement des surfaces nettes.", haut);
        Assert.Contains("SP est probablement incomplète",
            BenchmarkItem.RejectReason(Rejected(("coherence", true, ""), ("plausible", false, "SC / SP = 5%"))));
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

    [Fact]
    public void Base_list_sorts_on_its_headers_and_opens_a_page()
    {
        using var tmp = new TempDir();
        var paths = new AppPaths(tmp.Path, tmp.Path);
        Directory.CreateDirectory(Path.GetDirectoryName(paths.BenchmarkFile)!);
        File.WriteAllText(paths.BenchmarkFile, Json);
        var vm = new MainViewModel(new FakeShell(), paths, new AppSettings { BenchmarkFolder = tmp.Path }, enginePath: null);
        Assert.Equal(["1714", "1778"], vm.BenchmarkProjects.Select(i => i.Id));      // par défaut : références d'abord
        Assert.Equal("↓", vm.SortArrowData);
        vm.SortBaseCommand.Execute("nom");
        Assert.Equal(["1778", "1714"], vm.BenchmarkProjects.Select(i => i.Id));      // « L'Orée » avant « Le Clos »
        Assert.Equal(("↑", ""), (vm.SortArrowName, vm.SortArrowData));
        vm.SortBaseCommand.Execute("nom");
        Assert.Equal(["1714", "1778"], vm.BenchmarkProjects.Select(i => i.Id));      // même en-tête : sens inversé
        Assert.Equal(("↓", ""), (vm.SortArrowName, vm.SortArrowId));

        vm.OpenBaseDetailCommand.Execute(vm.BenchmarkProjects[0]);
        Assert.True(vm.IsBaseDetail);
        Assert.False(vm.IsHome);
        vm.CloseBaseDetailCommand.Execute(null);
        Assert.True(vm.IsHome);
    }

    private static string Write(string json)
    {
        var path = Path.Combine(Path.GetTempPath(), $"benchmark-{Guid.NewGuid():N}.json");
        File.WriteAllText(path, json);
        return path;
    }
}
