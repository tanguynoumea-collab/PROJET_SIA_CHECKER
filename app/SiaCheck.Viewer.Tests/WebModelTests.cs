using System.IO;
using System.IO.Compression;
using System.Text.Json;
using SiaCheck.Viewer.Services;

namespace SiaCheck.Viewer.Tests;

/// <summary>Maquette 3D web du dashboard (docs/V5_PLAN.md, partie 2).</summary>
public class WebModelTests
{
    private static JsonElement WriteAndRead(TempDir dir)
    {
        var path = Path.Combine(dir.Path, WebModel.FileName("9001"));
        WebModel.Write(Fixture.Synth(), "9001", path);
        Assert.False(File.Exists(path + ".tmp"));
        using var gz = new GZipStream(File.OpenRead(path), CompressionMode.Decompress);
        return JsonDocument.Parse(gz).RootElement.Clone();
    }

    [Fact]
    public void Writes_compressed_model_with_the_viewer_surfaces()
    {
        using var dir = new TempDir();
        var m = WriteAndRead(dir);
        Assert.Equal(WebModel.Format, m.GetProperty("format").GetString());
        Assert.Equal("9001", m.GetProperty("id").GetString());
        var doc = Fixture.Synth();
        var expected = doc.DisplaySurfaces.Where(s => s.Mesh is not null && !s.IsExcluded && s.Building is not null && s.Level is not null)
                          .DistinctBy(s => s.Id).Count();
        Assert.Equal(expected, m.GetProperty("surfaces").GetArrayLength());
        Assert.True(expected > 0);
    }

    [Fact]
    public void Lots_are_consistent_and_in_integer_centimetres()
    {
        using var dir = new TempDir();
        var m = WriteAndRead(dir);
        var nSurfaces = m.GetProperty("surfaces").GetArrayLength();
        var seen = new HashSet<int>();
        foreach (var lot in m.GetProperty("lots").EnumerateArray())
        {
            var v = lot.GetProperty("v").EnumerateArray().Select(x => x.GetInt64()).ToArray();
            var i = lot.GetProperty("i").EnumerateArray().Select(x => x.GetInt32()).ToArray();
            Assert.Equal(0, v.Length % 3);
            Assert.Equal(0, i.Length % 3);
            Assert.All(i, k => Assert.InRange(k, 0, v.Length / 3 - 1));
            Assert.All(v, x => Assert.True(x >= 0));          // origine retirée : coordonnées positives
            var s = lot.GetProperty("s").EnumerateArray().Select(x => x.GetInt32()).ToArray();
            var t = lot.GetProperty("t").EnumerateArray().Select(x => x.GetInt32()).ToArray();
            Assert.Equal(s.Length, t.Length);
            Assert.Equal(0, t[0]);
            Assert.True(t.SequenceEqual(t.Order()));
            Assert.All(t, k => Assert.InRange(k, 0, i.Length / 3 - 1));
            foreach (var k in s) Assert.True(seen.Add(k), "une surface dans un seul lot");
        }
        Assert.Equal(nSurfaces, seen.Count);
    }

    [Fact]
    public void Layers_follow_the_viewer_rules()
    {
        using var dir = new TempDir();
        var m = WriteAndRead(dir);
        var cats = m.GetProperty("categories").EnumerateArray().ToDictionary(c => c.GetProperty("code").GetString()!);
        Assert.NotEmpty(cats);
        foreach (var c in cats.Values)
        {
            Assert.Matches("^#[0-9A-F]{6}$", c.GetProperty("couleur").GetString());
            var group = c.GetProperty("groupe").GetString();
            Assert.Equal(group is "Intérieur" or "Extérieur" || c.GetProperty("code").GetString() == "SPT", c.GetProperty("visible").GetBoolean());
        }
    }

    [Theory]
    [InlineData("MAQ-1778.json.gz", true)]
    [InlineData("MAQ-1778.00.json.gz", true)]
    [InlineData("../MAQ-1.json.gz", false)]
    [InlineData("MDP-1778.xlsx", false)]
    [InlineData("MAQ-1.json.gz.tmp", false)]
    public void Only_model_files_are_served(string name, bool ok) => Assert.Equal(ok, WebModel.IsModelFile(name));
}
